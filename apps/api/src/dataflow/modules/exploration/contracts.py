"""Contratos de la exploración guiada (Fase 20, ADR-037).

La exploración usa un lenguaje de consultas cerrado (`explore-v1`). Las consultas las proponen las
reglas (a partir de las relaciones confirmadas de la comprensión) y la IA (a partir de la estructura
y de las preguntas de negocio). Python valida cada propuesta y el motor la calcula sobre **todas**
las filas. A la IA sólo le llegan hasta 100 filas de cada resultado para juzgar su relevancia; las
cifras publicadas son las del motor, cada una con su `evidence_id`.
"""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Fase 25 (`explore-v2`): evolución por periodo, comparación de periodos y valores atípicos.
QueryKind = Literal[
    "aggregate",
    "crosstab",
    "ratio",
    "top",
    "correlation_by_group",
    "evolution",
    "period_change",
    "outliers",
    "distribution",
    "scatter",
]
TEMPORAL_KINDS = frozenset({"evolution", "period_change"})
# Fase 26 (`dashboard-design-v2`): sólo los calcula el dashboard (histograma y dispersión); la
# investigación no los propone ni los acepta.
DASHBOARD_KINDS = frozenset({"distribution", "scatter"})
MAX_POINTS = 300  # puntos de un gráfico de dispersión
MAX_BINS = 20  # intervalos de un histograma
Aggregation = Literal["sum", "mean", "median", "count"]

RULES = "explore-v1"
OPERATION = "exploration.explore@1"
# Fase 25 (ADR-043): investigación con plan, árbol, evidencias, clasificación y control.
RULES_V2 = "investigation-v2"
OPERATION_V2 = "exploration.explore@2"
MAX_GROUPS = 500  # filas de resultado que se guardan
AI_ROWS = 100  # filas de cada resultado que ve la IA


class ExplorationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExploreQuery(ExplorationModel):
    """Una consulta del lenguaje cerrado. Columnas por nombre exacto de la tabla publicada."""

    kind: QueryKind
    measure: str | None = None
    measure_b: str | None = None  # ratio: numerador/denominador; correlación: segunda medida
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    aggregation: Aggregation | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    # top: primeros grupos (hasta 20); period_change: meses de cada ventana (hasta 12).
    limit: int | None = Field(default=None, ge=1, le=20)

    @property
    def key(self) -> str:
        parts = [
            self.kind,
            self.aggregation or "",
            self.measure or "",
            self.measure_b or "",
            ",".join(self.dimensions),
            f"{self.filter_column}={self.filter_value}" if self.filter_column else "",
            str(self.limit or ""),
        ]
        return "|".join(parts)


class ExploreFigure(ExplorationModel):
    label: str
    value: str | None  # canónico (Decimal en texto); None si no se puede calcular
    evidence_id: str


class ExploreRow(ExplorationModel):
    groups: list[str]
    rows: int
    figures: list[ExploreFigure]


class ExploreResult(ExplorationModel):
    key: str
    query: ExploreQuery
    title: str
    method: str
    columns: list[str]  # cabeceras: grupos y cifras
    rows: list[ExploreRow]
    total_groups: int
    truncated: bool
    covered_rows: int
    relevant: bool | None = None  # juicio (IA o reglas)
    judged_by: Literal["ai", "rules"] | None = None
    reason: str | None = None


class ExploreProposal(ExplorationModel):
    origin: Literal["rule", "ai"]
    query: dict[str, object]
    motive: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None
    key: str | None = None


class ExplorationLimits(ExplorationModel):
    max_queries: int = Field(default=20, ge=1, le=40)
    max_ai_proposals: int = Field(default=12, ge=0, le=20)
    max_ai_calls: int = Field(default=2, ge=0, le=4)
    ai_rows: int = Field(default=AI_ROWS, ge=1, le=AI_ROWS)
    # Fase 25: límites del árbol de investigación (`investigation-v2`).
    max_depth: int = Field(default=2, ge=0, le=3)
    max_nodes: int = Field(default=20, ge=1, le=40)
    max_children: int = Field(default=3, ge=0, le=5)
    max_seconds: int = Field(default=60, ge=5, le=600)
    max_cost_usd: str = "0.05"


class ExplorationScope(ExplorationModel):
    execution_id: UUID
    version_id: UUID
    comprehension_sha256: str
    table_sha256: str


Classification = Literal["relevant", "secondary", "descriptive", "inconclusive", "discarded"]
NodeStatus = Literal["pending", "rejected", "computed", "failed"]
StopReason = Literal["completed", "max_nodes", "max_seconds", "paused", "cancelled"]
ControlAction = Literal["pause", "cancel"]
Trigger = Literal["load", "feedback", "restart", "resume"]


class Criterion(ExplorationModel):
    """Un criterio de la evaluación (`relevance-v1`); las cifras salen del motor."""

    name: Literal["magnitude", "business", "quality", "consistency", "evidence", "limitations"]
    assessment: str


class InvestigationNode(ExplorationModel):
    """Una investigación del plan o del árbol (Fase 25): pregunta, hipótesis, operación del
    catálogo, evidencia, clasificación y decisión de profundizar o terminar."""

    id: str  # «1», «1.2», «1.2.1»: la posición en el árbol
    parent: str | None = None
    depth: int = 0
    origin: Literal["rule", "ai"]
    question: str
    motive: str
    hypothesis: str
    expected: str
    columns: list[str]
    method: str  # tipo de operación del catálogo, en palabras
    priority: Literal[1, 2, 3]
    depends_on: list[str] = Field(default_factory=list)
    query: dict[str, object]
    key: str | None = None  # clave de la consulta validada (resultado en `results`)
    status: NodeStatus
    reason: str | None = None  # rechazo, fallo o por qué no se calculó
    execution_id: UUID | None = None  # ejecución que produjo el resultado
    filters: list[str] = Field(default_factory=list)
    rows_considered: int | None = None
    total_rows: int | None = None
    classification: Classification | None = None
    criteria: list[Criterion] = Field(default_factory=list)
    judged: bool = False  # ya pasó por el juicio de la IA (o no había IA)
    interpretation: str | None = None  # de la IA, sin cifras propias
    decision: Literal["deepen", "finish"] | None = None
    decision_reason: str | None = None
    limitations: list[str] = Field(default_factory=list)


class InvestigationConsumption(ExplorationModel):
    nodes: int
    ai_calls: int
    cost_usd: str
    elapsed_ms: int


class Exploration(ExplorationModel):
    rules_version: Literal["explore-v1", "investigation-v2"] = "explore-v1"
    operation: Literal["exploration.explore@1", "exploration.explore@2"] = "exploration.explore@1"
    scope: ExplorationScope
    limits: ExplorationLimits
    ai_state: Literal["ready", "unavailable", "failed"]
    ai_reason: str | None = None
    proposals: list[ExploreProposal]
    results: list[ExploreResult]
    excluded: list[str] = Field(default_factory=list)  # relaciones marcadas «No relevante»
    calls: list[dict[str, object]] = Field(default_factory=list)
    limitations: list[str]
    # Fase 25 (`investigation-v2`): plan y árbol, por qué se detuvo y de qué ejecución sigue.
    nodes: list[InvestigationNode] = Field(default_factory=list)
    stopped: StopReason | None = None
    resumed_from: UUID | None = None
    trigger: Trigger | None = None
    consumption: InvestigationConsumption | None = None

    @property
    def resumable(self) -> bool:
        return self.stopped in {"paused", "max_seconds"} and any(
            n.status == "pending" for n in self.nodes
        )


class ExplorationView(ExplorationModel):
    state: Literal["queued", "running", "ready", "failed"]
    # Fase 21: sin trabajo todavía (la comprensión de la carga sigue en marcha): None.
    execution_id: UUID | None = None
    reason: str | None = None
    exploration: Exploration | None = None
    # Fase 25: petición de pausa o cancelación pendiente y si se puede reanudar.
    control: ControlAction | None = None
    resumable: bool = False


class InvestigationRun(ExplorationModel):
    """Una ejecución del historial de investigaciones de la versión (Fase 25)."""

    execution_id: UUID
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None
    trigger: Trigger | None = None
    stopped: StopReason | None = None
    resumed_from: UUID | None = None
    nodes: int | None = None
    computed: int | None = None
    relevant: int | None = None


class InvestigationHistory(ExplorationModel):
    items: list[InvestigationRun]


class InvestigationCommand(ExplorationModel):
    """Control del usuario: pausar o cancelar la investigación en marcha, reanudar la pausada o
    volver a investigar la versión (Fase 25)."""

    action: Literal["pause", "cancel", "resume", "restart"]


class ControlSource(Protocol):
    """Puerto: la petición de control pendiente de una ejecución (o None)."""

    def requested(self, execution: UUID) -> ControlAction | None: ...


# --- IA ------------------------------------------------------------------------------------------


class RawQuery(ExplorationModel):
    """Propuesta de la IA traducida del esquema de salida; todavía sin validar."""

    kind: str
    measure: str | None = None
    measure_b: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    aggregation: str | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    limit: int | None = None
    motive: str = ""
    # Fase 25: la propuesta como investigación del plan.
    question: str = ""
    hypothesis: str = ""
    expected: str = ""
    priority: int | None = None
    depends_on: list[int] = Field(default_factory=list)


class Judgment(ExplorationModel):
    key: str
    relevant: bool
    reason: str
