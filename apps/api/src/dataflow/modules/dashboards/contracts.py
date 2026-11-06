"""Contratos de dashboards (Fase 8): tarjetas que apuntan a un análisis y a su ejecución exacta.

Un dashboard no calcula nada propio. Cada tarjeta referencia una revisión de un plan de
`analytics.query@2` y la ejecución que muestra, más su forma de verse. Las revisiones son
inmutables; «Actualizar» es una acción explícita que vuelve a ejecutar las tarjetas sobre la
versión elegida y crea una revisión nueva. Los filtros globales sólo ocultan filas de resultados
ya calculados.
"""

from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CardView = Literal["kpi", "table", "bar", "line"]
CardSize = Literal["small", "medium", "large"]
CardStatus = Literal[
    "ready",
    "pending",
    "failed",
    "not_executed",
    "insufficient_data",
    "semantic_requirement_missing",
    "invalid_plan",
]
RevisionCause = Literal["create", "edit", "refresh"]
CARD_OPERATION = "analytics.query@2"
MAX_CARDS = 24
MAX_FILTERS = 5


class DashboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Card(DashboardModel):
    """Una tarjeta: el análisis (revisión exacta del plan), la ejecución que muestra y su forma.

    `id` es estable entre revisiones (lo genera el cliente). `execution_id` es nulo cuando el plan
    no se pudo ejecutar (p. ej. requisito semántico pendiente tras «Actualizar»)."""

    id: UUID
    title: str = Field(min_length=1, max_length=120)
    plan_revision_id: UUID
    execution_id: UUID | None
    view: CardView
    size: CardSize = "medium"
    metric: str = Field(default="m0", pattern=r"^m[0-9]$")  # métrica de la consulta que se dibuja


class GlobalFilter(DashboardModel):
    """Muestra sólo las filas cuya dimensión `column_id` tiene uno de los `values` (cadenas
    canónicas de la Fase 6). No recalcula: las cifras y su evidencia no cambian."""

    column_id: UUID
    values: list[str] = Field(min_length=1, max_length=50)

    @field_validator("values")
    @classmethod
    def short_values(cls, value: list[str]) -> list[str]:
        if any(len(item) > 200 for item in value):
            raise ValueError("Valores de hasta 200 caracteres.")
        return value


class DashboardDraft(DashboardModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    cards: list[Card] = Field(default_factory=list, max_length=MAX_CARDS)
    filters: list[GlobalFilter] = Field(default_factory=list, max_length=MAX_FILTERS)

    @model_validator(mode="after")
    def unique(self) -> "DashboardDraft":
        if len({c.id for c in self.cards}) != len(self.cards):
            raise ValueError("Cada tarjeta sólo puede aparecer una vez.")
        if len({f.column_id for f in self.filters}) != len(self.filters):
            raise ValueError("Cada filtro global sólo puede aparecer una vez.")
        return self


class DashboardContent(DashboardDraft):
    """Contenido sometido a hash (dominio `dashboard`)."""

    schema_version: Literal[1] = 1
    project_id: UUID


class DashboardRevision(DashboardModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    previous_revision_id: UUID | None
    cause: RevisionCause
    refreshed_version_id: UUID | None  # versión elegida en «Actualizar»
    content: DashboardContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class DashboardSummary(DashboardModel):
    family_id: UUID
    head: DashboardRevision
    revision_count: int


class CreateDashboardRequest(DashboardModel):
    draft: DashboardDraft


class ReviseDashboardRequest(DashboardModel):
    expected_revision: int = Field(ge=1)
    draft: DashboardDraft


class RefreshDashboardRequest(DashboardModel):
    expected_revision: int = Field(ge=1)
    version_id: UUID


class SaveDashboardResponse(DashboardModel):
    revision: DashboardRevision
    changed: bool


class CardRefresh(DashboardModel):
    card_id: UUID
    plan_revision_id: UUID
    plan_created: bool  # plan nuevo para la versión elegida (los planes no cambian de tabla)
    execution_id: UUID | None
    problems: list[str]


class RefreshDashboardResponse(DashboardModel):
    revision: DashboardRevision
    cards: list[CardRefresh]


class FilterApplicability(DashboardModel):
    column_id: UUID
    applicable: bool  # la consulta de la tarjeta agrupa por esa dimensión


class CardState(DashboardModel):
    card_id: UUID
    status: CardStatus
    message: str | None
    version_id: UUID
    version_number: int
    dimensions: list[UUID]
    time_grain: str | None
    execution_state: str | None
    executed_at: datetime | None
    result_rows: int | None
    filters: list[FilterApplicability]


class DashboardView(DashboardModel):
    family_id: UUID
    head: DashboardRevision
    revision_count: int
    cards: list[CardState]


# --- Puertos -------------------------------------------------------------------------------


class PlanFacts(DashboardModel):
    """Lo que un dashboard necesita de una revisión de plan (sin importar planning)."""

    revision_id: UUID
    project_id: UUID
    version_id: UUID
    artifact_id: UUID
    operations: list[str]  # «analytics.query@2» por paso
    parameters: dict[str, Any]  # del primer paso
    steps: list[dict[str, Any]]
    semantic_ref: dict[str, Any] | None
    valid: bool
    problems: list[tuple[str, str]]  # (código, mensaje)


class ExecutionFacts(DashboardModel):
    id: UUID
    project_id: UUID
    plan_revision_id: UUID | None
    version_id: UUID
    state: str
    finished_at: datetime | None
    error_message: str | None
    result_rows: int | None


class TargetTable(DashboardModel):
    """Tabla publicada de la versión elegida en «Actualizar» y su revisión semántica vigente."""

    project_id: UUID
    version_id: UUID
    artifact_id: UUID
    artifact_sha256: str
    semantic_ref: dict[str, Any] | None


class DashboardSources(Protocol):
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def plan(self, owner: UUID, revision: UUID) -> PlanFacts: ...
    def execution(self, owner: UUID, execution: UUID) -> ExecutionFacts: ...
    def version_number(self, owner: UUID, version: UUID) -> int: ...
    def target(self, owner: UUID, version: UUID) -> TargetTable: ...
    def create_plan(
        self,
        owner: UUID,
        table: TargetTable,
        steps: list[dict[str, Any]],
        key: UUID,
        correlation: str,
    ) -> PlanFacts: ...
    def execute(self, owner: UUID, plan_revision: UUID, key: UUID, correlation: str) -> UUID: ...


class DashboardRepository(Protocol):
    def lock_scope(self, scope: UUID) -> None: ...
    def create_family(self, owner: UUID, project: UUID) -> UUID: ...
    def lock_family(self, owner: UUID, family: UUID) -> tuple[UUID, int]: ...
    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> DashboardRevision | None: ...
    def append(
        self, family: UUID, expected: int, revision: DashboardRevision, correlation: str
    ) -> None: ...
    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None: ...
    def head(self, owner: UUID, family: UUID) -> tuple[DashboardRevision, int]: ...
    def families(self, owner: UUID, project: UUID) -> list[UUID]: ...
    def revision(self, owner: UUID, revision: UUID) -> DashboardRevision: ...
