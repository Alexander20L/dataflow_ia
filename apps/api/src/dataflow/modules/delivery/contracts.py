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
from dataflow.modules.curation.contracts import DashboardCustomization, FindingFeedback
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
# Fase 26 (`dashboard-design-v2`, ADR-044): histograma y dispersión.
DESIGN_RULES_V2 = "dashboard-design-v2"
WidgetType = Literal["kpi", "bar", "line", "heatmap", "pie", "table", "histogram", "scatter"]
MAX_SECTIONS = 6
MAX_WIDGETS = 24
MAX_PIE_SLICES = 6
MAX_BARS = 12  # barras que se dibujan; con más grupos se muestran los mayores y la tabla
MAX_FILTER_VALUES = 50  # valores que se ofrecen para filtrar una dimensión


class Trace(DeliveryModel):
    """Origen reproducible de un gráfico (Fase 26): la investigación o el cálculo que lo produce
    y sus parámetros."""

    source: Literal["investigation", "analysis", "dashboard"]
    investigation: str | None = None  # id del nodo («1.2»)
    question: str | None = None
    operation: str  # tipo de cálculo, en palabras
    columns: list[str] = Field(default_factory=list)
    measure: str | None = None
    grouping: list[str] = Field(default_factory=list)  # dimensiones o «mes»
    aggregation: str | None = None
    period_columns: list[str] = Field(default_factory=list)
    rows: int | None = None  # registros utilizados
    total_rows: int | None = None
    filters: list[str] = Field(default_factory=list)
    method: str


class DashboardItem(DeliveryModel):
    """Elemento publicado que el dashboard puede mostrar (sin cifras: sólo su forma).
    Fase 26: también indicadores, distribuciones y relaciones que calcula el dashboard."""

    id: str  # "insight:<id>", "exploration:<clave>" o "computed:<clave>"
    origin: Literal["insight", "exploration", "computed"]
    title: str
    kind: str
    widgets: list[WidgetType]  # gráficos compatibles con su forma
    figures: list[str]  # evidencias que pueden ir en un indicador
    classification: str | None = None  # clase de la investigación (relevance-v1)
    groups: int | None = None  # grupos del resultado (legibilidad)
    filterable: bool = False  # se recalcula al filtrar
    trace: Trace | None = None


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


class IndicatorComparison(DeliveryModel):
    """Último mes con datos frente al anterior: sólo cuando hay una base válida (al menos dos
    meses con datos); las cifras salen del motor."""

    label: str  # «2024-08 frente a 2024-07»
    previous: str | None
    current: str | None
    change: str | None
    change_percent: str | None
    evidence_id: str


class Indicator(DeliveryModel):
    """Indicador del resumen ejecutivo (Fase 26): nombre, valor, unidad declarada, periodo de
    referencia, comparación y procedencia. Nunca inventa monedas ni unidades."""

    id: str  # "computed:<clave>#<n>"
    item: str  # elemento del que sale la cifra
    name: str
    value: str | None
    highlight: str | None = None  # grupo o periodo destacado («Norte», «2024-08»)
    unit: str | None = None
    reference: str  # periodo de referencia o «todo el dataset»
    comparison: IndicatorComparison | None = None
    evidence_id: str
    trace: Trace


class DimensionFilter(DeliveryModel):
    column: str
    values: list[str]
    more: int = 0  # valores que no se ofrecen (sólo los primeros por registros)


class FilterOptions(DeliveryModel):
    months: list[str] = Field(default_factory=list)  # «AAAA-MM», en orden
    period_columns: list[str] = Field(default_factory=list)
    dimensions: list[DimensionFilter] = Field(default_factory=list)


class DashboardScope(DeliveryModel):
    execution_id: UUID
    version_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exploration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Dashboard(DeliveryModel):
    schema_version: Literal[1] = 1
    operation: Literal["delivery.dashboard@1", "delivery.dashboard@2"] = "delivery.dashboard@1"
    rules_version: Literal["dashboard-design-v1", "dashboard-design-v2"] = "dashboard-design-v1"
    scope: DashboardScope
    designed_by: Literal["ai", "rules"]
    ai_state: Literal["ready", "failed", "unavailable"]
    ai_reason: str | None = None
    title: str
    sections: list[DashboardSection]
    decisions: list[DesignDecision] = Field(default_factory=list)
    calls: list[dict[str, object]] = Field(default_factory=list)
    # Fase 26 (`dashboard-design-v2`): los elementos con su origen, los indicadores y lo que
    # calcula el dashboard (con evidencias), las opciones de filtro y los avisos.
    items: list[DashboardItem] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    computed: list[ExploreResult] = Field(default_factory=list)
    filters: FilterOptions | None = None
    total_rows: int | None = None
    partial: str | None = None  # la investigación se detuvo antes de terminar
    notice: str | None = None  # no hay hallazgos suficientes


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
    # Fase 26: la versión personalizada vigente (la automática no cambia nunca) y cuántos de sus
    # gráficos ya no están en el dashboard actual.
    custom: DashboardCustomization | None = None
    custom_dropped: int = 0


class CategoryFilter(DeliveryModel):
    column: str = Field(min_length=1, max_length=300)
    values: list[str] = Field(min_length=1, max_length=MAX_FILTER_VALUES)


class DashboardFilterRequest(DeliveryModel):
    """Filtros del dashboard (Fase 26): un rango de meses («AAAA-MM», ambos incluidos) y valores
    de hasta tres dimensiones."""

    period_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    period_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    categories: list[CategoryFilter] = Field(default_factory=list, max_length=3)


class FilteredItem(DeliveryModel):
    item: str
    result: ExploreResult | None = None
    reason: str | None = None  # por qué no se recalcula (o no hay datos)


class DashboardFilterResult(DeliveryModel):
    """Los elementos recalculados con los filtros sobre todas las filas que los cumplen. No se
    guarda: las evidencias se derivan de los filtros y se pueden reproducir."""

    filters: list[str]
    rows: int
    total_rows: int
    items: list[FilteredItem]
    indicators: list[Indicator]
