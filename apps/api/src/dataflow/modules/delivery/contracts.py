"""Contratos de la entrega (Fase 17, ADR-034): informe automático y progreso por etapas.

El informe (`delivery.report@1`, reglas `automatic-report-v1`) sólo reordena lo ya publicado
(hallazgos, investigación, explicación verificada, calidad y limitaciones); no calcula ninguna
cifra y cada cifra conserva su `evidence_id`. El progreso se deriva de los trabajos de la cola.
"""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.analytics.contracts import AutomaticInsight
from dataflow.modules.curation.contracts import FindingFeedback
from dataflow.modules.exploration.contracts import ExploreResult

OPERATION = "delivery.report@1"
RULES = "automatic-report-v1"


class DeliveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportTable(DeliveryModel):
    headers: list[str]
    rows: list[list[str]]


class ReportChart(DeliveryModel):
    """Ilustración vectorial de una serie ya calculada; la trazabilidad está en la tabla."""

    type: Literal["bar", "line"]
    title: str
    labels: list[str]
    values: list[str]  # cifras canónicas (Decimal en texto)


class ReportBlock(DeliveryModel):
    title: str | None = None
    badge: str | None = None
    paragraphs: list[str] = Field(default_factory=list)
    table: ReportTable | None = None
    chart: ReportChart | None = None


class ReportSection(DeliveryModel):
    id: str
    title: str
    intro: str | None = None
    blocks: list[ReportBlock]


class ReportSource(DeliveryModel):
    """De dónde sale cada parte del informe (ids y hashes de lo publicado)."""

    project_id: UUID
    version_id: UUID
    version_number: int
    file_name: str
    analysis_execution_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_execution_id: UUID
    investigation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Fase 20: exploración guiada incluida (la terminada cuando se generó el informe).
    exploration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Fase 21: dashboard que fija el orden y valoraciones del usuario aplicadas (hash canónico).
    dashboard_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    feedback_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Fase 24B: significados del usuario aplicados al describir las columnas (hash canónico).
    meanings_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ReportDocument(DeliveryModel):
    schema_version: Literal[1] = 1
    operation: Literal["delivery.report@1"] = "delivery.report@1"
    rules_version: Literal["automatic-report-v1"] = "automatic-report-v1"
    title: str
    source: ReportSource
    generated_at: datetime
    sections: list[ReportSection]
    evidence_ids: list[str]


class ReportView(BaseModel):
    """Estado del informe de una versión (sólo lectura)."""

    state: Literal["queued", "running", "ready", "failed"]
    reason: str | None = None
    execution_id: UUID
    file_name: str | None = None
    byte_size: int | None = None
    sha256: str | None = None
    generated_at: datetime | None = None
    evidence_count: int | None = None
    # Fase 21: hay una versión nueva del informe en cola (tras una valoración); mientras tanto
    # se sirve la última terminada.
    updating: bool = False


StageId = Literal[
    "analysis", "comprehension", "exploration", "dashboard", "investigation", "report"
]
StageState = Literal["pending", "queued", "running", "done", "failed", "skipped"]


class Stage(BaseModel):
    id: StageId
    title: str
    state: StageState
    detail: str
    execution_id: UUID | None = None
    finished_at: datetime | None = None


class Progress(BaseModel):
    """Etapas de una carga en orden; `complete` cuando ninguna queda pendiente."""

    version_id: UUID
    complete: bool
    stages: list[Stage]


class RunSummary(DeliveryModel):
    """Lo que el progreso necesita de un trabajo de la cola (sin depender de executions)."""

    id: UUID
    kind: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None = None
    finished_at: datetime | None = None


class DeliveryAccess(Protocol):
    def report(self, owner: UUID, version: UUID) -> ReportView: ...
    def pdf(self, owner: UUID, version: UUID) -> tuple[bytes, str]: ...
    def progress(self, owner: UUID, version: UUID) -> Progress: ...


# --- Fase 21: dashboard adaptado a los datos (`dashboard-design-v1`, ADR-038) -------------------

DESIGN_RULES = "dashboard-design-v1"
WidgetType = Literal["kpi", "bar", "line", "heatmap", "pie", "table"]
MAX_SECTIONS = 6
MAX_WIDGETS = 24
MAX_PIE_SLICES = 6


class DashboardItem(DeliveryModel):
    """Elemento publicado que el dashboard puede mostrar (sin cifras: sólo su forma)."""

    id: str  # "insight:<id>" o "exploration:<clave>"
    origin: Literal["insight", "exploration"]
    title: str
    kind: str
    widgets: list[WidgetType]  # gráficos compatibles con su forma
    figures: list[str]  # evidencias que pueden ir en un indicador


class DashboardWidget(DeliveryModel):
    type: WidgetType
    item: str
    title: str
    evidence_id: str | None = None  # sólo en indicadores


class DashboardSection(DeliveryModel):
    title: str
    intro: str | None = None
    widgets: list[DashboardWidget]


class DesignDecision(DeliveryModel):
    """Qué pasó con cada elemento que propuso la IA (aceptado o rechazado con motivo)."""

    item: str
    type: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None


class DashboardScope(DeliveryModel):
    execution_id: UUID
    version_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exploration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Dashboard(DeliveryModel):
    schema_version: Literal[1] = 1
    operation: Literal["delivery.dashboard@1"] = "delivery.dashboard@1"
    rules_version: Literal["dashboard-design-v1"] = "dashboard-design-v1"
    scope: DashboardScope
    designed_by: Literal["ai", "rules"]
    ai_state: Literal["ready", "failed", "unavailable"]
    ai_reason: str | None = None
    title: str
    sections: list[DashboardSection]
    decisions: list[DesignDecision] = Field(default_factory=list)
    calls: list[dict[str, object]] = Field(default_factory=list)


class Arrangement(DeliveryModel):
    """El dashboard con las valoraciones aplicadas: fijados arriba y descartados aparte."""

    sections: list[DashboardSection]
    pinned: list[str]
    hidden: list[str]


class DashboardView(BaseModel):
    """Estado del dashboard de una versión, con las marcas aplicadas y los datos publicados que
    cita (hallazgos y resultados de la exploración); nunca recalcula."""

    state: Literal["queued", "running", "ready", "failed"]
    # Sin trabajo todavía (la comprensión o la exploración de la carga siguen en marcha): None.
    execution_id: UUID | None = None
    reason: str | None = None
    dashboard: Dashboard | None = None
    arrangement: Arrangement | None = None
    insights: list[AutomaticInsight] = Field(default_factory=list)
    results: list[ExploreResult] = Field(default_factory=list)
    feedback: list[FindingFeedback] = Field(default_factory=list)
