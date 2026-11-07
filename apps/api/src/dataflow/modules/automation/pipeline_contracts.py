"""Pipeline automático (Fase 11C): contratos, estados y puertos.

Un pipeline por versión importada cuando el proyecto tiene una política activa. La revisión de la
política queda fijada al iniciar. Cada paso es idempotente (claves derivadas del pipeline) y el
reconciliador del worker lo hace avanzar; si un paso falla o la política no autoriza, el pipeline
se detiene en `needs_review` con motivos y no reintenta solo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RunState = Literal["running", "needs_review", "completed", "failed", "cancelled"]
Step = Literal[
    "propose",
    "preview",
    "approve",
    "apply",
    "diagnose",
    "quality_rules",
    "select",
    "interpret",
    "analyze",
    "publish",
    "done",
]
TERMINAL: set[str] = {"needs_review", "completed", "failed", "cancelled"}


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PipelineReason(PipelineModel):
    code: str
    message: str
    step_id: str | None = None
    column: str | None = None
    measured: str | None = None
    limit: str | None = None


class StepAttempt(PipelineModel):
    sequence: int
    step: str
    outcome: Literal["started", "succeeded", "skipped", "blocked", "failed", "cancelled"]
    detail: dict[str, Any]
    created_at: datetime


class AutomationRunView(PipelineModel):
    id: UUID
    project_id: UUID
    version_id: UUID
    policy_revision_id: UUID
    state: RunState
    step: Step
    reasons: list[PipelineReason]
    plan_revision_id: UUID | None
    preview_execution_id: UUID | None
    approval_id: UUID | None
    apply_execution_id: UUID | None
    derived_version_id: UUID | None
    rules_execution_id: UUID | None
    result_version_id: UUID | None
    mapping_revision_id: UUID | None = None
    semantic_revision_id: UUID | None = None
    pass_number: int = 1
    dashboard_family_id: UUID | None = None
    dashboard_revision_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    attempts: list[StepAttempt] = []


class AutomationRunPage(PipelineModel):
    items: list[AutomationRunView]
    total: int


@dataclass
class PipelineRun:
    """Estado mutable del pipeline mientras avanza (el repositorio lo persiste)."""

    id: UUID
    owner_id: UUID
    project_id: UUID
    version_id: UUID
    policy_revision_id: UUID
    state: str
    step: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    plan_revision_id: UUID | None = None
    preview_execution_id: UUID | None = None
    approval_id: UUID | None = None
    apply_execution_id: UUID | None = None
    derived_version_id: UUID | None = None
    rules_execution_id: UUID | None = None
    result_version_id: UUID | None = None
    mapping_revision_id: UUID | None = None
    semantic_revision_id: UUID | None = None
    pass_number: int = 1


@dataclass(frozen=True)
class MatchResult:
    status: str  # none | compatible | incompatible
    revision_id: UUID | None
    problems: list[str]
    casts: list[dict[str, Any]]  # {column_id, type, scale}


@dataclass(frozen=True)
class PlanResult:
    revision_id: UUID
    valid: bool
    problems: list[str]


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    approval_id: UUID | None
    reasons: list[dict[str, Any]]


class PipelinePort(Protocol):
    """Casos de uso existentes que el pipeline encadena (bootstrap los implementa)."""

    def table_of(self, owner: UUID, version: UUID) -> tuple[UUID, str] | None: ...
    def proposal(
        self, owner: UUID, artifact: UUID, casts: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]: ...
    def mapping_match(self, owner: UUID, project: UUID, artifact: UUID) -> MatchResult: ...
    def apply_mapping(self, owner: UUID, mapping_revision: UUID, artifact: UUID) -> UUID: ...
    def start_analysis(
        self, owner: UUID, project: UUID, mapping_revision: UUID, artifact: UUID, key: UUID
    ) -> dict[str, Any] | None:
        """Métricas y planes del dashboard del molde, sin ejecutar (None: molde genérico)."""
        ...

    def start_query(self, owner: UUID, plan_revision: UUID, key: UUID) -> UUID | None:
        """Ejecuta una consulta; None si no hay capacidad todavía."""
        ...

    def publish_dashboard(
        self,
        owner: UUID,
        project: UUID,
        family: UUID | None,
        analysis: dict[str, Any],
        key: UUID,
    ) -> tuple[UUID, UUID]:
        """Crea el dashboard del molde o una revisión nueva; devuelve (familia, revisión)."""
        ...

    def dashboard_head_revision(self, owner: UUID, family: UUID) -> int: ...

    def create_plan(
        self,
        owner: UUID,
        project: UUID,
        artifact: UUID,
        sha256: str,
        steps: list[dict[str, Any]],
        semantic_ref: dict[str, Any] | None,
        key: UUID,
    ) -> PlanResult: ...
    def start_preview(self, owner: UUID, plan_revision: UUID, key: UUID) -> UUID: ...
    def execution_state(self, owner: UUID, execution: UUID) -> tuple[str, str | None]: ...
    def approve(
        self, owner: UUID, preview: UUID, policy_revision: UUID, run: UUID
    ) -> ApprovalResult: ...
    def start_apply(self, owner: UUID, approval: UUID) -> UUID: ...
    def derived_version(self, apply_execution: UUID) -> UUID: ...
    def version_state(self, owner: UUID, version: UUID) -> str | None: ...
    def applicable_ruleset(self, owner: UUID, artifact: UUID) -> tuple[UUID, str] | None: ...
    def start_rules(
        self,
        owner: UUID,
        project: UUID,
        artifact: UUID,
        sha256: str,
        ruleset: tuple[UUID, str],
        key: UUID,
    ) -> UUID: ...
    def evaluate_rules(self, owner: UUID, policy_revision: UUID) -> bool: ...
    def select_source(self, owner: UUID, project: UUID, version: UUID) -> None: ...
    def cancel_execution(self, owner: UUID, execution: UUID) -> None: ...


class RunRepository(Protocol):
    def try_lock(self, run: UUID) -> bool: ...
    def unlock(self, run: UUID) -> None: ...
    def load(self, run: UUID) -> PipelineRun | None: ...
    def save(self, run: PipelineRun) -> None: ...
    def log(self, run: UUID, step: str, outcome: str, detail: dict[str, Any]) -> None: ...
    def running_ids(self, limit: int) -> list[UUID]: ...
    def view(self, owner: UUID, run: UUID) -> AutomationRunView: ...
    def page(self, owner: UUID, project: UUID, limit: int, offset: int) -> AutomationRunPage: ...
    def for_version(self, owner: UUID, version: UUID) -> AutomationRunView | None: ...
    def attention(self, owner: UUID, limit: int) -> list[AutomationRunView]: ...
    def analysis(self, run: UUID) -> dict[str, Any] | None: ...
    def save_analysis(self, run: UUID, project: UUID, data: dict[str, Any]) -> None: ...
    def dashboard_family(self, project: UUID, template: str) -> UUID | None: ...
