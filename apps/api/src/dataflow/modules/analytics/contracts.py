"""Contratos de analytics (Fase 7A): métricas definidas por el usuario, consultas estructuradas
y resultados con evidencia direccionable.

Nada de expresiones ni SQL del usuario: una consulta es un documento estructurado (métricas,
dimensiones, filtros, granularidad y periodo) y el sistema genera el cálculo. El nombre de
negocio («Ingresos») es una etiqueta sobre una métrica definida explícitamente.
"""

from datetime import date, datetime
from typing import Annotated, Any, Final, Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dataflow.modules.analytics.periods import (
    GRAIN_NAMES,
    ComparisonKind,
    TimeGrain,
    ends_period,
    starts_period,
)
from dataflow.modules.planning.public import COLUMN_REF, AnalysisPlan
from dataflow.platform.data_types import ALL_TYPES, NUMERIC, DataType

Aggregation = Literal["sum", "count", "count_distinct", "avg", "min", "max", "sum_product"]
SemiAdditive = Literal["last_snapshot"]
FilterOperator = Literal[
    "eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "between", "is_null", "is_not_null"
]
NullPolicy = Literal["exclude"]
MAX_FILTERS = 20
MAX_METRICS = 10
MAX_DIMENSIONS = 4
MAX_RESULT_ROWS = 10_000
QUERY_VERSION: Final = 1

# Agregaciones que miden importes/cantidades: columna numérica confirmada como «measure» y con
# unidad o moneda comparable. Los conteos aceptan cualquier tipo y no tienen unidad (D4, D5).
MEASURED: frozenset[str] = frozenset({"sum", "avg", "min", "max", "sum_product"})
# Agregaciones que admiten la medida semi-aditiva «último corte» (11E).
SNAPSHOT_AGGREGATIONS: frozenset[str] = frozenset({"sum", "sum_product"})
# Campos de métrica añadidos en 11E: fuera del hash cuando no se usan, para que las métricas
# guardadas antes conserven su `content_sha256`.
OPTIONAL_METRIC_FIELDS: tuple[str, ...] = ("second_measure_column_id", "semi_additive")


def measure_types(aggregation: str) -> frozenset[DataType]:
    return NUMERIC if aggregation in MEASURED else ALL_TYPES


Units = tuple[str | None, str | None]  # (unidad, moneda) confirmadas de una columna


def product_unit(first: Units, second: Units) -> Units | None:
    """Unidad de Σ(medida × segunda medida): una cantidad por un costo unitario da la moneda;
    dos unidades, su producto («kg×m»); dos monedas no se multiplican (None). Misma regla que
    `planning.domain.product_unit`, que la valida antes de ejecutar."""
    currencies = [currency for _, currency in (first, second) if currency]
    if len(currencies) == 2:
        return None
    if currencies:
        return None, currencies[0]
    units = [unit for unit, _ in (first, second) if unit]
    return ("×".join(units) if units else None), None


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Filter(AnalyticsModel):
    """Filtro estructurado. Los valores se escriben como cadenas canónicas del tipo de la
    columna (decimal con punto, fecha ISO, `true`/`false`); el motor los interpreta."""

    column_id: UUID
    operator: FilterOperator
    values: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def arity(self) -> "Filter":
        count = len(self.values)
        expected = {
            "is_null": count == 0,
            "is_not_null": count == 0,
            "between": count == 2,
            "in": count >= 1,
            "not_in": count >= 1,
        }.get(self.operator, count == 1)
        if not expected:
            raise ValueError(f"Número de valores no válido para «{self.operator}».")
        if any(len(value) > 200 for value in self.values):
            raise ValueError("Valores de hasta 200 caracteres.")
        return self


class MetricDraft(AnalyticsModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    measure_column_id: UUID
    aggregation: Aggregation
    filters: list[Filter] = Field(default_factory=list, max_length=MAX_FILTERS)
    time_column_id: UUID | None = None
    null_policy: NullPolicy = "exclude"
    # 11E · analytics.query@3: segunda medida de `sum_product` (Σ medida × segunda medida) y
    # medida semi-aditiva (`last_snapshot`: último corte de cada periodo, nunca entre fechas).
    second_measure_column_id: UUID | None = None
    semi_additive: SemiAdditive | None = None

    @model_validator(mode="after")
    def query_v3_fields(self) -> "MetricDraft":
        if (self.aggregation == "sum_product") != (self.second_measure_column_id is not None):
            raise ValueError(
                "«sum_product» necesita una segunda medida, y sólo «sum_product» la admite."
            )
        if self.semi_additive is not None:
            if self.aggregation not in SNAPSHOT_AGGREGATIONS:
                raise ValueError("El último corte sólo se aplica a «sum» y «sum_product».")
            if self.time_column_id is None:
                raise ValueError("El último corte necesita la columna temporal (fecha de corte).")
        return self

    @property
    def requires_query_v3(self) -> bool:
        """Sólo analytics.query@3 calcula `sum_product` y el último corte."""
        return self.aggregation == "sum_product" or self.semi_additive is not None

    def hashed(self) -> dict[str, Any]:
        """Volcado para hashes: los campos de 11E sólo cuentan si se usan."""
        data = self.model_dump(mode="json")
        for name in OPTIONAL_METRIC_FIELDS:
            if data.get(name) is None:
                data.pop(name, None)
        return data


class BaseTable(AnalyticsModel):
    version_id: UUID
    artifact_id: UUID
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MetricContent(MetricDraft):
    """Contenido sometido a hash (dominio `analytics_metric`)."""

    schema_version: Literal[1] = 1
    base_table: BaseTable


class MetricRevision(AnalyticsModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    previous_revision_id: UUID | None
    content: MetricContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class MetricReference(AnalyticsModel):
    revision_id: UUID
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TimeRange(AnalyticsModel):
    """Rango inclusivo de fechas de negocio (ISO)."""

    start: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    end: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

    @model_validator(mode="after")
    def ordered(self) -> "TimeRange":
        if self.start is None and self.end is None:
            raise ValueError("Indica el inicio, el fin o ambos.")
        if self.start and self.end and self.start > self.end:
            raise ValueError("El inicio debe ser anterior o igual al fin.")
        return self


class QueryParameters(AnalyticsModel):
    """analytics.query@1: consulta estructurada y de sólo lectura (plan normal)."""

    metrics: list[MetricReference] = Field(min_length=1, max_length=MAX_METRICS)
    dimensions: list[UUID] = Field(
        default_factory=list, max_length=MAX_DIMENSIONS, json_schema_extra={COLUMN_REF: True}
    )
    filters: list[Filter] = Field(default_factory=list, max_length=MAX_FILTERS)
    time_grain: TimeGrain | None = None
    time_range: TimeRange | None = None
    avg_scale: int = Field(default=4, ge=0, le=12)
    max_result_rows: int = Field(default=1000, ge=1, le=MAX_RESULT_ROWS)

    @field_validator("dimensions")
    @classmethod
    def unique_dimensions(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Cada dimensión sólo puede aparecer una vez.")
        return value

    @field_validator("metrics")
    @classmethod
    def unique_metrics(cls, value: list[MetricReference]) -> list[MetricReference]:
        if len({m.revision_id for m in value}) != len(value):
            raise ValueError("Cada métrica sólo puede aparecer una vez.")
        return value

    @property
    def filter_column_ids(self) -> list[UUID]:
        return [f.column_id for f in self.filters]


MAX_TOP_N = 1000
SHAREABLE: frozenset[str] = frozenset({"sum", "count"})  # se pueden sumar (7B-2)


class Ranking(AnalyticsModel):
    """Top N por una métrica de la consulta, dentro de cada periodo (o de todo el resultado si
    no se agrupa por tiempo). Posiciones 1, 2, 3 sin empates compartidos: dos valores iguales se
    ordenan por las dimensiones (desempate estable) y la fila lo declara con
    `tied_with_previous`. Los grupos sin valor en esa métrica no tienen posición."""

    metric_revision_id: UUID
    direction: Literal["desc", "asc"] = "desc"
    top_n: int = Field(ge=1, le=MAX_TOP_N)


class QueryParametersV2(QueryParameters):
    """analytics.query@2: los parámetros de @1 más comparaciones por periodo, ranking y
    participación sobre el total (7B).

    @1 no cambia y sus planes guardados se siguen ejecutando igual. Sin opciones nuevas, @2
    calcula las mismas cifras, conteos y `evidence_id` de `value` que @1."""

    comparisons: list[ComparisonKind] = Field(default_factory=list, max_length=2)
    change_scale: int = Field(default=2, ge=0, le=12)
    ranking: Ranking | None = None
    share_of_total: list[UUID] = Field(default_factory=list, max_length=MAX_METRICS)
    share_scale: int = Field(default=2, ge=0, le=12)

    @field_validator("comparisons")
    @classmethod
    def unique_comparisons(cls, value: list[ComparisonKind]) -> list[ComparisonKind]:
        if len(set(value)) != len(value):
            raise ValueError("Cada comparación sólo puede aparecer una vez.")
        return value

    @model_validator(mode="after")
    def known_metrics(self) -> "QueryParametersV2":
        revisions = {m.revision_id for m in self.metrics}
        if self.ranking is not None:
            if not self.dimensions:
                raise ValueError("Para ordenar un top N, agrupa por al menos una dimensión.")
            if self.ranking.metric_revision_id not in revisions:
                raise ValueError("El ranking debe usar una de las métricas de la consulta.")
        if len(set(self.share_of_total)) != len(self.share_of_total):
            raise ValueError("Cada participación sólo puede aparecer una vez.")
        if any(revision not in revisions for revision in self.share_of_total):
            raise ValueError("La participación debe usar métricas de la consulta.")
        return self

    @model_validator(mode="after")
    def comparable_periods(self) -> "QueryParametersV2":
        if not self.comparisons:
            return self
        if self.time_grain is None:
            raise ValueError("Para comparar periodos, agrupa por tiempo (día, semana, mes…).")
        grain, bounds = self.time_grain, self.time_range
        name = GRAIN_NAMES[grain]

        def day(text: str) -> date:
            try:
                return date.fromisoformat(text)
            except ValueError:
                raise ValueError(f"«{text}» no es una fecha válida.") from None

        # Decisión 7B-1: con comparaciones el periodo está alineado; nunca se compara medio
        # mes con un mes completo.
        if bounds is not None and bounds.start and not starts_period(day(bounds.start), grain):
            raise ValueError(
                f"Para comparar, el periodo debe empezar el primer día de {name}; "
                f"«{bounds.start}» no lo es."
            )
        if bounds is not None and bounds.end and not ends_period(day(bounds.end), grain):
            raise ValueError(
                f"Para comparar, el periodo debe terminar el último día de {name}; "
                f"«{bounds.end}» no lo es."
            )
        return self


# --- Resultado ---------------------------------------------------------------------------

MISSING: dict[str, bool] = {"missing": True}  # marca explícita del grupo «(sin valor)»


class MetricCounts(AnalyticsModel):
    """Filas de la tabla de entrada y su destino para una métrica."""

    input_rows: int
    excluded_by_filters: int
    excluded_by_nulls: int
    included_rows: int


class MetricDefinition(AnalyticsModel):
    """Definición usada en el cálculo (copiada de la revisión exacta)."""

    key: str  # m0, m1… (orden de la consulta)
    revision_id: UUID
    revision: int
    content_sha256: str
    label: str
    aggregation: Aggregation
    measure_column_id: UUID
    measure_column: str
    time_column_id: UUID | None
    filters: list[Filter]
    null_policy: NullPolicy
    unit: str | None
    currency: str | None
    scale: int | None  # escala del resultado (decimal); None para enteros y conteos
    counts: MetricCounts


class ResultColumn(AnalyticsModel):
    key: str  # d0, d1… o «period»
    column_id: UUID | None
    name: str
    technical_type: str | None
    time_grain: TimeGrain | None = None


class ResultRow(AnalyticsModel):
    key: dict[str, Any]  # clave canónica: valores de celda (§6) o {"missing": true}
    labels: dict[str, str | None]  # texto para mostrar
    values: dict[str, str | None]  # métrica → cadena canónica (None: sin filas en el grupo)
    evidence: dict[str, str]  # métrica → evidence_id


class EvidenceScope(AnalyticsModel):
    """Partes comunes de toda referencia de evidencia de un resultado."""

    execution_id: UUID
    step_id: str
    slot: Literal["analysis_result"] = "analysis_result"
    input: BaseTable
    semantic_ref: dict[str, Any] | None
    query_filters: list[Filter]
    time_grain: TimeGrain | None
    time_range: TimeRange | None


class AnalysisResult(AnalyticsModel):
    schema_version: Literal[1] = 1
    operation: Literal["analytics.query@1"] = "analytics.query@1"
    scope: EvidenceScope
    avg_scale: int
    dimensions: list[ResultColumn]
    metrics: list[MetricDefinition]
    rows: list[ResultRow]
    row_count: int


BaseStatus = Literal["available", "no_base_data", "no_counterpart", "missing_period"]
ChangeStatus = Literal["available", "base_zero", "base_missing", "current_missing"]


class BaseCounts(AnalyticsModel):
    """Filas de la tabla y su destino en la base de una comparación (una métrica, un tipo).

    `excluded_by_filters`: filtros de la consulta que no son de periodo y filtros de la
    métrica. `outside_base_periods`: filas sin fecha o fuera de los periodos base necesarios
    (el periodo consultado no se aplica a la base). Suma: `input_rows`."""

    input_rows: int
    excluded_by_filters: int
    outside_base_periods: int
    excluded_by_nulls: int
    included_rows: int


class MetricDefinitionV2(MetricDefinition):
    """`counts` es el periodo consultado, igual que en @1; `base_counts`, la base de cada
    comparación."""

    base_counts: dict[ComparisonKind, BaseCounts] = Field(default_factory=dict)


class ComparisonCell(AnalyticsModel):
    """Comparación de una cifra con su periodo base. Nunca se usa 0 en lugar de un nulo.

    `base_status`: `no_base_data` (el periodo base no tiene filas para la métrica),
    `no_counterpart` (29 de febrero, semana 53 o fuera del calendario), `missing_period` (la
    fila es el grupo sin fecha). `change_status`: `base_zero` deja `change` y anula
    `change_pct`; `base_missing` y `current_missing` anulan ambos."""

    base_period: dict[str, str] | None  # {"grain", "start"}
    base_label: str | None
    base: str | None
    base_status: BaseStatus
    change: str | None
    change_pct: str | None
    change_status: ChangeStatus
    evidence: dict[str, str]  # base · change · change_pct → evidence_id


class ShareCell(AnalyticsModel):
    """Porcentaje del grupo sobre el total de su periodo (o del resultado), redondeado por
    separado con `share_scale` y HALF_EVEN. `total_zero`/`value_missing`: nulo, nunca 0."""

    value: str | None
    status: Literal["available", "total_zero", "value_missing"]
    evidence: str


class ShareTotal(AnalyticsModel):
    """Total de una partición, calculado ANTES del top N y del presupuesto: los porcentajes
    de las filas visibles pueden sumar menos de 100. Cada porcentaje se redondea por separado,
    así que la suma de todos los grupos puede desviarse de 100 hasta `tolerance` puntos
    (n × media unidad de `share_scale`)."""

    metric: str  # m0, m1…
    period: dict[str, Any] | None  # partición: clave de periodo o None (todo el resultado)
    total: str
    groups: int
    tolerance: str
    mixed_signs: bool  # hay valores negativos: un porcentaje puede ser negativo o > 100


class RankCell(AnalyticsModel):
    position: int
    tied_with_previous: bool  # mismo valor que la posición anterior: la diferencia es el desempate
    evidence: str


class RankingPartition(AnalyticsModel):
    period: dict[str, Any] | None
    groups: int
    ranked: int  # con valor en la métrica del ranking
    shown: int
    hidden: int  # fuera del top N o sin valor


class RankingSummary(AnalyticsModel):
    metric: str  # m0, m1…
    direction: Literal["desc", "asc"]
    top_n: int
    partitions: list[RankingPartition]
    hidden_groups: int


class ResultRowV2(ResultRow):
    comparisons: dict[str, dict[ComparisonKind, ComparisonCell]] = Field(default_factory=dict)
    share: dict[str, ShareCell] = Field(default_factory=dict)
    rank: RankCell | None = None


class AnalysisResultV2(AnalyticsModel):
    schema_version: Literal[2] = 2
    operation: Literal["analytics.query@2"] = "analytics.query@2"
    scope: EvidenceScope
    avg_scale: int
    comparisons: list[ComparisonKind]
    change_scale: int
    share_scale: int
    shares: list[ShareTotal]
    ranking: RankingSummary | None
    dimensions: list[ResultColumn]
    metrics: list[MetricDefinitionV2]
    rows: list[ResultRowV2]
    row_count: int


class QueryParametersV3(QueryParametersV2):
    """analytics.query@3 (11E): los parámetros de @2 sin cambios. Lo nuevo está en las
    métricas que admite: `sum_product` (Σ medida × segunda medida) y la medida semi-aditiva
    `last_snapshot`. @1 y @2 rechazan esas métricas y no cambian."""


class SnapshotCounts(AnalyticsModel):
    """Último corte de una métrica semi-aditiva. `superseded_rows`: filas incluidas (pasan
    filtros y nulos) de fechas anteriores al corte de su periodo; no entran en el valor. Las
    filas que forman el valor son `included_rows - superseded_rows`."""

    superseded_rows: int
    base_superseded_rows: dict[ComparisonKind, int] = Field(default_factory=dict)


class MetricDefinitionV3(MetricDefinitionV2):
    second_measure_column_id: UUID | None = None
    second_measure_column: str | None = None
    semi_additive: SemiAdditive | None = None
    snapshot: SnapshotCounts | None = None


class ResultRowV3(ResultRowV2):
    # Métrica semi-aditiva → fecha ISO del corte usado en el periodo de la fila.
    snapshots: dict[str, str] = Field(default_factory=dict)


class AnalysisResultV3(AnalyticsModel):
    schema_version: Literal[3] = 3
    operation: Literal["analytics.query@3"] = "analytics.query@3"
    scope: EvidenceScope
    avg_scale: int
    comparisons: list[ComparisonKind]
    change_scale: int
    share_scale: int
    shares: list[ShareTotal]
    ranking: RankingSummary | None
    dimensions: list[ResultColumn]
    metrics: list[MetricDefinitionV3]
    rows: list[ResultRowV3]
    row_count: int


ExtendedResult = AnalysisResultV2 | AnalysisResultV3


EvidenceCell = Literal[
    "value",
    "previous_period",
    "same_period_last_year",
    "change",
    "change_pct",
    "share_of_total",
    "rank",
]


class EvidenceReference(AnalyticsModel):
    """Dirección estable de una cifra: el mismo cálculo produce el mismo `evidence_id`.

    `value` conserva la dirección de @1 (sin `detail`). Las cifras derivadas de @2 añaden
    `cell` y su `detail`: comparación y periodo base, escala de la variación o de la
    participación, o dirección, top N e indicador de empate de la posición."""

    evidence_id: str
    execution_id: UUID
    step_id: str
    slot: str
    input: BaseTable
    semantic_ref: dict[str, Any] | None
    metric: MetricReference
    metric_filters: list[Filter]
    query_filters: list[Filter]
    time_grain: TimeGrain | None
    time_range: TimeRange | None
    row_key: dict[str, Any]
    cell: EvidenceCell = "value"
    detail: dict[str, Any] | None = None


class EvidenceView(AnalyticsModel):
    """Una cifra con su dirección completa y su contexto. `value` es la cifra de la celda
    direccionada (la posición, en `rank`); `metric_value`, la cifra del grupo en su métrica."""

    reference: EvidenceReference
    value: str | None
    definition: MetricDefinitionV3 | MetricDefinitionV2 | MetricDefinition
    labels: dict[str, str | None]
    operation: Literal["analytics.query@1", "analytics.query@2", "analytics.query@3"] = (
        "analytics.query@1"
    )
    metric_value: str | None = None
    snapshot: str | None = None  # @3: fecha del corte de una métrica semi-aditiva
    comparison: ComparisonCell | None = None
    share: ShareCell | None = None
    share_total: ShareTotal | None = None
    rank: RankCell | None = None
    ranking: RankingSummary | None = None


AnalysisResultView = Annotated[
    AnalysisResult | AnalysisResultV2 | AnalysisResultV3, Field(discriminator="operation")
]
AnyAnalysisResult = AnalysisResult | AnalysisResultV2 | AnalysisResultV3


# --- Persistencia y API ------------------------------------------------------------------


class MetricProblem(AnalyticsModel):
    code: Literal["UNKNOWN_COLUMN", "COLUMN_TYPE_MISMATCH", "INVALID_FILTER_VALUE"]
    message: str


class MetricSummary(AnalyticsModel):
    family_id: UUID
    head: MetricRevision
    revision_count: int
    anchored_here: bool
    applicable: bool
    problems: list[MetricProblem]


class MetricContext(AnalyticsModel):
    artifact_id: UUID
    metrics: list[MetricSummary]


class SaveMetricRequest(AnalyticsModel):
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    family_id: UUID | None = None  # None: métrica nueva
    expected_revision: int = Field(ge=0)
    draft: MetricDraft


class SaveMetricResponse(AnalyticsModel):
    revision: MetricRevision
    changed: bool


class MetricFacts(AnalyticsModel):
    """Lo que la validación de planes necesita de una revisión de métrica."""

    content_sha256: str
    aggregation: Aggregation
    measure_column_id: UUID
    measure_types: list[DataType]
    time_column_id: UUID | None
    filter_column_ids: list[UUID]
    second_measure_column_id: UUID | None = None
    semi_additive: SemiAdditive | None = None
    requires_query_v3: bool = False


class MetricRepository(Protocol):
    def lock_scope(self, scope: UUID) -> None: ...
    def create_family(self, owner: UUID, project: UUID, base: BaseTable) -> UUID: ...
    def lock_family(self, owner: UUID, family: UUID) -> tuple[BaseTable, int]: ...
    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> MetricRevision | None: ...
    def append(
        self, family: UUID, expected: int, revision: MetricRevision, correlation: str
    ) -> None: ...
    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None: ...
    def head(self, family: UUID) -> tuple[MetricRevision, int] | None: ...
    def families(self, owner: UUID, project: UUID) -> list[UUID]: ...
    def revision(self, owner: UUID, revision: UUID) -> MetricRevision: ...


# --- Análisis automático (Fase 15, analytics.automatic@1) ---------------------------------

AutomaticUnit = Literal["number", "percent", "count", "index"]


class AutomaticAnalysisParameters(AnalyticsModel):
    """analytics.automatic@1: ejecuta el plan automatic-plan-v1 con automatic-analysis-v1."""

    rules: Literal["automatic-analysis-v1"] = "automatic-analysis-v1"
    plan_rules: Literal["automatic-plan-v1"] = "automatic-plan-v1"


class AutomaticScope(AnalyticsModel):
    """La tabla de entrada la produce la propia carga: se identifica por su hash."""

    execution_id: UUID
    step_id: str
    version_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def input(self) -> BaseTable:
        return BaseTable(
            version_id=self.version_id,
            artifact_id=uuid5(NAMESPACE_URL, f"automatic-table:{self.execution_id}"),
            artifact_sha256=self.table_sha256,
        )


class InsightFigure(AnalyticsModel):
    label: str
    value: str | None
    unit: AutomaticUnit
    evidence_id: str


class InsightPoint(AnalyticsModel):
    label: str
    value: str | None
    evidence_id: str | None


class InsightChart(AnalyticsModel):
    type: Literal["bar", "line"]
    title: str
    unit: AutomaticUnit
    points: list[InsightPoint]


class AutomaticInsight(AnalyticsModel):
    """Hallazgo verificable: texto determinista, cifras con evidencia y su cobertura."""

    id: str
    analysis_id: str
    kind: str
    title: str
    statement: str
    importance: int = Field(ge=0, le=100)
    figures: list[InsightFigure]
    chart: InsightChart | None = None
    coverage: str
    notes: list[str] = Field(default_factory=list)


class AutomaticEvidence(AnalyticsModel):
    """Procedencia de una cifra: método y entradas exactas (otras evidencias o filas)."""

    evidence_id: str
    analysis_id: str
    label: str
    value: str | None
    unit: AutomaticUnit
    method: str
    inputs: dict[str, Any]


class AutomaticAnalysis(AnalyticsModel):
    schema_version: Literal[1] = 1
    operation: Literal["analytics.automatic@1"] = "analytics.automatic@1"
    rules_version: Literal["automatic-analysis-v1"] = "automatic-analysis-v1"
    scope: AutomaticScope
    plan: AnalysisPlan
    insights: list[AutomaticInsight]
    evidence: list[AutomaticEvidence]
    queries: dict[str, AnalysisResultV2]
    limitations: list[str]
