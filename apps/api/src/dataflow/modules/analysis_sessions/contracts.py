"""Sesión de análisis con fuente única (Fase 11A).

Una sesión por proyecto mantiene **una** tabla activa. Cada selección es una revisión inmutable;
la sesión guarda la referencia a la vigente con control de concurrencia (`expected_revision`).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionInput(SessionModel):
    """Una selección de fuente: versión de datos y su tabla publicada exacta."""

    revision: int
    version_id: UUID
    version_number: int
    version_kind: Literal["imported", "derived"]
    file_name: str
    table_artifact_id: UUID
    table_sha256: str
    selected_by: UUID
    selected_at: datetime


class AnalysisSessionView(SessionModel):
    id: UUID
    project_id: UUID
    revision: int
    status: Literal["empty", "ready"]
    active: SessionInput | None
    created_at: datetime


class SessionInputPage(SessionModel):
    items: list[SessionInput]
    total: int


class SelectInputRequest(SessionModel):
    version_id: UUID
    expected_revision: int = Field(ge=0, strict=True)


@dataclass(frozen=True)
class ReadyInput:
    """Versión validada para ser la fuente activa: procesada y con tabla publicada."""

    version_id: UUID
    version_number: int
    version_kind: Literal["imported", "derived"]
    file_name: str
    table_artifact_id: UUID
    table_sha256: str


class SessionInputs(Protocol):
    """Puerto sobre proyectos, versiones y ejecuciones (bootstrap lo implementa)."""

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None: ...

    def ready_input(self, owner: UUID, project: UUID, version: UUID) -> ReadyInput:
        """La versión del proyecto, si está lista; si no, `INPUT_NOT_READY` (en proceso) o
        `INPUT_INVALID` (falló o se canceló). La fuente activa no cambia en ningún caso."""
        ...


@dataclass(frozen=True)
class SessionState:
    id: UUID
    project_id: UUID
    owner_id: UUID
    revision: int
    created_at: datetime


class SessionRepository(Protocol):
    def by_project(self, owner: UUID, project: UUID) -> SessionState | None: ...
    def create(self, owner: UUID, project: UUID) -> SessionState: ...
    def get(self, owner: UUID, session: UUID, lock: bool = False) -> SessionState: ...
    def head(self, session: SessionState) -> SessionInput | None: ...
    def append(
        self, session: SessionState, ready: ReadyInput, actor: UUID, correlation: str
    ) -> SessionInput: ...
    def history(
        self, session: SessionState, limit: int, offset: int
    ) -> tuple[list[SessionInput], int]: ...
