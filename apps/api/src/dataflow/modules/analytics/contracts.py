"""Contratos de analytics (Fase 7A): métricas definidas por el usuario, consultas estructuradas
y resultados con evidencia direccionable.

Nada de expresiones ni SQL del usuario: una consulta es un documento estructurado (métricas,
dimensiones, filtros, granularidad y periodo) y el sistema genera el cálculo. El nombre de
negocio («Ingresos») es una etiqueta sobre una métrica definida explícitamente.
"""

from datetime import datetime
from typing import Any, Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dataflow.modules.planning.public import COLUMN_REF
from dataflow.platform.data_types import ALL_TYPES, NUMERIC, DataType

Aggregation = Literal["sum", "count", "count_distinct", "avg", "min", "max"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]
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
MEASURED: frozenset[str] = frozenset({"sum", "avg", "min", "max"})


def measure_types(aggregation: str) -> frozenset[DataType]:
    return NUMERIC if aggregation in MEASURED else ALL_TYPES


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


class EvidenceReference(AnalyticsModel):
    """Dirección estable de una cifra: el mismo cálculo produce el mismo `evidence_id`."""

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
    cell: Literal["value"] = "value"


class EvidenceView(AnalyticsModel):
    reference: EvidenceReference
    value: str | None
    definition: MetricDefinition
    labels: dict[str, str | None]


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
