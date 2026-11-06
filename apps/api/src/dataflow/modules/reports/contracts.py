"""Contratos de informes (Fase 9): bloques de texto y bloques de datos con procedencia.

Un informe es una lista de bloques. Los de datos apuntan a una ejecución exacta de
`analytics.query` o a una tarjeta exacta de una revisión de dashboard; nunca se recalculan solos.
«Actualizar bloques» es explícito y crea una revisión nueva. El PDF se genera en el worker a
partir de una revisión exacta y se guarda como artefacto con su hash.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dataflow.modules.dashboards.contracts import ExecutionFacts, PlanFacts, TargetTable

MAX_BLOCKS = 50
RENDER_OPERATION = ("reports.render_pdf", 1)  # operación interna: no está en el catálogo
BlockStatus = Literal[
    "ready",
    "pending",
    "failed",
    "not_executed",
    "insufficient_data",
    "semantic_requirement_missing",
    "invalid_plan",
]
RevisionCause = Literal["create", "edit", "refresh"]


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextBlock(ReportModel):
    id: UUID
    kind: Literal["text", "conclusion", "limitations"]
    text: str = Field(min_length=1, max_length=5000)


class AnalysisBlock(ReportModel):
    """Resultado exacto de una ejecución de `analytics.query`. `execution_id` es nulo si el plan
    no se pudo ejecutar tras «Actualizar bloques»."""

    id: UUID
    kind: Literal["analysis"] = "analysis"
    title: str = Field(min_length=1, max_length=120)
    plan_revision_id: UUID
    execution_id: UUID | None


class DashboardCardBlock(ReportModel):
    """Tarjeta exacta de una revisión de dashboard (muestra su ejecución y su forma)."""

    id: UUID
    kind: Literal["dashboard_card"] = "dashboard_card"
    title: str = Field(min_length=1, max_length=120)
    dashboard_revision_id: UUID
    card_id: UUID


Block = Annotated[TextBlock | AnalysisBlock | DashboardCardBlock, Field(discriminator="kind")]


class ReportDraft(ReportModel):
    title: str = Field(min_length=1, max_length=160)
    blocks: list[Block] = Field(default_factory=list, max_length=MAX_BLOCKS)

    @model_validator(mode="after")
    def unique(self) -> "ReportDraft":
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Cada bloque sólo puede aparecer una vez.")
        return self


class ReportContent(ReportDraft):
    """Contenido sometido a hash (dominio `report`): el informe es de una versión de dataset."""

    schema_version: Literal[1] = 1
    project_id: UUID
    version_id: UUID


class ReportRevision(ReportModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    previous_revision_id: UUID | None
    cause: RevisionCause
    refreshed_version_id: UUID | None
    content: ReportContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class ReportSummary(ReportModel):
    family_id: UUID
    head: ReportRevision
    revision_count: int


class Provenance(ReportModel):
    """Procedencia de un bloque de datos: dataset, versión, ejecución, filtros y fecha."""

    block_id: UUID
    status: BlockStatus
    message: str | None
    dataset: str
    version_id: UUID
    version_number: int
    plan_revision_id: UUID
    execution_id: UUID | None
    execution_state: str | None
    executed_at: datetime | None
    filters: list[dict[str, Any]]
    time_range: dict[str, Any] | None
    dimensions: list[UUID]
    time_grain: str | None
    result_rows: int | None
    view: str  # forma: «table» para bloques de análisis; la de la tarjeta en los de dashboard
    metric: str | None  # métrica que dibuja la tarjeta (m0…), None en bloques de análisis
    dashboard_revision_id: UUID | None = None


class ReportView(ReportModel):
    family_id: UUID
    head: ReportRevision
    revision_count: int
    provenance: list[Provenance]


class RevisionItem(ReportModel):
    id: UUID
    revision: int
    cause: RevisionCause
    created_at: datetime
    content_sha256: str


class CreateReportRequest(ReportModel):
    version_id: UUID
    draft: ReportDraft


class ReviseReportRequest(ReportModel):
    expected_revision: int = Field(ge=1)
    draft: ReportDraft


class RefreshReportRequest(ReportModel):
    expected_revision: int = Field(ge=1)
    version_id: UUID


class SaveReportResponse(ReportModel):
    revision: ReportRevision
    changed: bool


class RenderResponse(ReportModel):
    execution_id: UUID
    state: str
    report_revision_id: UUID


class PdfRender(ReportModel):
    execution_id: UUID
    report_revision_id: UUID
    state: str
    created_at: datetime
    finished_at: datetime | None
    sha256: str | None
    error_message: str | None


# --- Instantánea que recibe el worker (sin base de datos) ----------------------------------


class SnapshotBlock(ReportModel):
    kind: str
    title: str | None = None
    text: str | None = None
    provenance: Provenance | None = None
    result: dict[str, Any] | None = None  # analysis_result de la ejecución, si está lista


class ReportSnapshot(ReportModel):
    report_title: str
    family_id: UUID
    revision_id: UUID
    revision: int
    content_sha256: str
    dataset: str
    version_number: int
    generated_at: datetime
    blocks: list[SnapshotBlock]


# --- Puertos -------------------------------------------------------------------------------


class CardFacts(ReportModel):
    dashboard_revision_id: UUID
    family_id: UUID
    project_id: UUID
    card_id: UUID
    plan_revision_id: UUID
    execution_id: UUID | None
    view: str
    metric: str


class VersionFacts(ReportModel):
    project_id: UUID
    number: int
    dataset: str


class ReportSources(Protocol):
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def version(self, owner: UUID, version: UUID) -> VersionFacts: ...
    def plan(self, owner: UUID, revision: UUID) -> PlanFacts: ...
    def execution(self, owner: UUID, execution: UUID) -> ExecutionFacts: ...
    def card(self, owner: UUID, dashboard_revision: UUID, card: UUID) -> CardFacts: ...
    def latest_card(self, owner: UUID, family: UUID, card: UUID) -> CardFacts | None: ...
    def analysis_result(self, owner: UUID, execution: UUID) -> dict[str, Any] | None: ...
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
    def enqueue_render(
        self, owner: UUID, revision: "ReportRevision", key: UUID, correlation: str
    ) -> ExecutionFacts: ...
    def render(self, owner: UUID, execution: UUID, revision: UUID) -> PdfRender: ...
    def pdf(self, owner: UUID, execution: UUID) -> tuple[bytes, str]: ...


class ReportRepository(Protocol):
    def lock_scope(self, scope: UUID) -> None: ...
    def create_family(self, owner: UUID, project: UUID) -> UUID: ...
    def lock_family(self, owner: UUID, family: UUID) -> tuple[UUID, int]: ...
    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> ReportRevision | None: ...
    def append(
        self, family: UUID, expected: int, revision: ReportRevision, correlation: str
    ) -> None: ...
    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None: ...
    def head(self, owner: UUID, family: UUID) -> tuple[ReportRevision, int]: ...
    def families(self, owner: UUID, project: UUID) -> list[UUID]: ...
    def revision(self, owner: UUID, revision: UUID) -> ReportRevision: ...
    def revisions(self, owner: UUID, family: UUID) -> list[ReportRevision]: ...
    def add_render(self, owner: UUID, family: UUID, revision: UUID, execution: UUID) -> None: ...
    def renders(self, owner: UUID, family: UUID) -> list[tuple[UUID, UUID]]: ...
    def render_owner(self, owner: UUID, execution: UUID) -> tuple[UUID, UUID] | None: ...
