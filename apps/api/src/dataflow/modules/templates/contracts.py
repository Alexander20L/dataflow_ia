"""Moldes e interpretación reutilizable (Fase 11D).

Un molde versionado (`sales@1`, `inventory@1`, `generic@1`) describe los roles de negocio que
necesita. La detección produce **candidatos**, nunca confirmaciones. Una persona confirma un
**mapeo** (qué columna cumple cada rol, por nombre; tipo destino; moneda o unidad; grano) y se
reutiliza sólo si una carga nueva cumple el contrato de compatibilidad.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TemplateId = Literal["sales@1", "inventory@1", "generic@1"]
TargetType = Literal["string", "integer", "decimal", "date"]
SemanticRoleName = Literal["dimension", "identifier", "measure", "business_date"]


class TemplateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class RoleSpec:
    role: str  # nombre del rol en el molde (p. ej. «amount»)
    label: str
    semantic_role: SemanticRoleName
    types: tuple[str, ...]  # tipos destino admitidos
    required: bool
    money: bool = False  # exige moneda
    quantity: bool = False  # exige unidad
    patterns: tuple[str, ...] = ()
    # Sin coincidencia de nombre, ¿vale el rol sugerido por el perfil? Sólo donde no es ambiguo.
    fallback: bool = False


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    label: str
    roles: tuple[RoleSpec, ...]
    grains: tuple[str, ...] | None  # valores admitidos; None = texto libre
    grain_required: bool


class MappingRole(TemplateModel):
    role: str = Field(min_length=1, max_length=40)
    column: str = Field(min_length=1, max_length=200)
    target_type: TargetType
    scale: int | None = Field(default=None, ge=0, le=12)

    @model_validator(mode="after")
    def scale_only_for_decimal(self) -> "MappingRole":
        if (self.target_type == "decimal") != (self.scale is not None):
            raise ValueError("La escala se indica sólo (y siempre) para decimales.")
        return self


class MappingContent(TemplateModel):
    schema_version: Literal["template-mapping@1"] = "template-mapping@1"
    template: TemplateId
    roles: list[MappingRole] = Field(default_factory=list, max_length=16)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    grain: str | None = Field(default=None, min_length=1, max_length=200)


class MappingRevision(TemplateModel):
    id: UUID
    family_id: UUID
    project_id: UUID
    template: TemplateId
    revision: int
    previous_revision_id: UUID | None
    content: MappingContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class SaveMappingRequest(TemplateModel):
    expected_revision: int = Field(ge=0, strict=True)
    content: MappingContent


class MappingList(TemplateModel):
    items: list[MappingRevision]


class CandidateRole(TemplateModel):
    role: str
    label: str
    required: bool
    column: str | None
    target_type: TargetType | None
    scale: int | None = None


class TemplateCandidate(TemplateModel):
    """Propuesta de interpretación: nunca se confirma sola."""

    template: TemplateId
    label: str
    complete: bool
    roles: list[CandidateRole]
    missing_required: list[str]
    grains: list[str] | None
    mapping_revision_id: UUID | None = None  # mapeo confirmado del proyecto para este molde
    compatible: bool | None = None  # si ese mapeo es compatible con esta tabla
    problems: list[str] = Field(default_factory=list)


class CandidateList(TemplateModel):
    representation_id: UUID
    candidates: list[TemplateCandidate]


@dataclass(frozen=True)
class TableColumn:
    id: UUID
    name: str
    technical_type: str
    scale: int | None
    suggested_role: str | None = None
    suggested_type: str | None = None


@dataclass(frozen=True)
class CastRequest:
    """Conversión confirmada por la persona en el mapeo (la limpieza la propone)."""

    column: str
    type: str
    scale: int | None


@dataclass(frozen=True)
class Compatibility:
    compatible: bool
    problems: list[str]
    casts: list[CastRequest]


@dataclass(frozen=True)
class MappingMatch:
    status: Literal["none", "compatible", "incompatible"]
    revision: MappingRevision | None
    problems: list[str]
    casts: list[CastRequest]


class TemplateTables(Protocol):
    """Puerto sobre understanding y proyectos (bootstrap lo implementa)."""

    def columns(self, owner: UUID, artifact: UUID) -> tuple[UUID, list[TableColumn]]:
        """Proyecto y columnas de la tabla (con la sugerencia heurística de rol y tipo)."""
        ...

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None: ...


class MappingRepository(Protocol):
    def lock(self, project: UUID, template: str) -> None: ...
    def head(self, owner: UUID, project: UUID, template: str) -> MappingRevision | None: ...
    def heads(self, owner: UUID, project: UUID) -> list[MappingRevision]: ...
    def get(self, owner: UUID, revision: UUID) -> MappingRevision: ...
    def replay(
        self, owner: UUID, project: UUID, key: UUID, fingerprint: str
    ) -> MappingRevision | None: ...
    def append(
        self,
        owner: UUID,
        project: UUID,
        content: MappingContent,
        content_sha256: str,
        key: UUID,
        fingerprint: str,
        correlation: str,
    ) -> MappingRevision: ...
