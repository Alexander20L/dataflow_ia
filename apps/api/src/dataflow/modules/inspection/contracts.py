"""Pestaña Dataset (Fase 22, ADR-039): inspección estructural, estadística y de calidad de una
versión, calculada una vez por el motor sobre la tabla completa (`dataset-inspection-v1`), y
correcciones manuales opcionales del diccionario, guardadas como metadatos.

Nada aquí modifica el archivo, la tabla leída ni los resultados de otras pestañas: la
inspección diagnostica y comunica; las correcciones sólo cambian cómo se describe una columna.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.ingestion.contracts import ConvertedColumn, KeptColumn, SheetFacts

INSPECTION_RULES = "dataset-inspection-v1"

# Tipo técnico: cómo están escritos los valores (lo que el motor puede leer sin perder nada).
TechnicalType = Literal["string", "integer", "decimal", "boolean", "date", "datetime", "empty"]
# Naturaleza estadística: qué representa la variable (no es lo mismo que el tipo técnico).
Nature = Literal["nominal", "ordinal", "discrete", "continuous", "temporal", "unknown"]
# Rol analítico sugerido.
Role = Literal["identifier", "dimension", "measure", "time", "category", "text", "unknown"]
Group = Literal["numeric", "categorical", "temporal", "identifier", "other"]
QualityDimension = Literal[
    "completeness", "uniqueness", "validity", "consistency", "format", "integrity"
]
Severity = Literal["high", "medium", "low", "info"]
TimeFormat = Literal[
    "day_month_year", "month_day_year", "year_month_day", "year", "month", "year_month"
]
EntryStatus = Literal["automatic", "corrected", "confirmed"]


class TokenCount(BaseModel):
    token: str
    count: int = Field(ge=0)


class Missing(BaseModel):
    """Faltantes por clase: nunca se suman entre sí ni se convierten en nulos."""

    nulls: int = Field(ge=0)
    empty_strings: int = Field(ge=0)
    whitespace: int = Field(ge=0)
    tokens: list[TokenCount]


class Frequency(BaseModel):
    value: str
    count: int = Field(ge=0)
    # Porcentaje sobre todos los registros (también los nulos), con dos decimales.
    percent: str


class Bin(BaseModel):
    label: str
    lower: str | None = None
    upper: str | None = None
    count: int = Field(ge=0)


class NumericStats(BaseModel):
    count: int
    minimum: str
    maximum: str
    mean: str
    median: str
    std: str | None
    q1: str
    q3: str
    histogram: list[Bin]
    method: str


class TemporalStats(BaseModel):
    minimum: str
    maximum: str
    span_days: int | None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly", "irregular"] | None
    distinct_periods: int
    missing_periods: int | None
    missing_sample: list[str]
    method: str


class CategoricalStats(BaseModel):
    distinct: int
    top: list[Frequency]
    others: int = Field(ge=0)


class MixedTypes(BaseModel):
    numeric: int = Field(ge=0)
    text: int = Field(ge=0)
    examples: list[str]


class ColumnInspection(BaseModel):
    id: UUID
    ordinal: int
    name: str
    technical_type: TechnicalType
    nature: Nature
    nature_reason: str
    role: Role
    role_evidence: list[str]
    group: Group
    count: int
    nulls: int
    null_percent: str
    distinct: int
    distinct_percent: str
    examples: list[str]
    missing: Missing
    leading_zeros: int = 0
    mixed: MixedTypes | None = None
    numeric: NumericStats | None = None
    temporal: TemporalStats | None = None
    categorical: CategoricalStats | None = None
    reading: str | None = None


class Finding(BaseModel):
    id: str
    dimension: QualityDimension
    kind: str
    title: str
    columns: list[str]
    affected_rows: int = Field(ge=0)
    percent: str
    examples: list[str]
    sample_rows: list[int]
    description: str
    severity: Severity
    source: Literal["dataset-inspection-v1", "automatic-quality-v1"]


class PeriodCandidate(BaseModel):
    """Año + Mes que podrían formar un periodo: se informa, nunca se crea una fecha."""

    columns: list[str]
    periods: int
    first: str | None
    last: str | None
    unparsed_rows: int
    note: str


class Summary(BaseModel):
    rows: int
    columns: int
    cells: int
    missing_cells: int
    completeness_percent: str
    duplicate_rows: int
    memory_bytes: int | None
    groups: dict[Group, int]


class FileInspection(BaseModel):
    file_name: str
    format: Literal["csv", "xlsx", "pdf", "sqlserver", "other"]
    uploaded_at: datetime
    size_bytes: int | None
    sha256: str
    encoding: str | None
    separator: str | None
    decimal_convention: str | None
    date_convention: str | None
    header: str
    blank_lines: int | None = None
    sheets: list[SheetFacts] = Field(default_factory=list)
    sheet: str | None = None
    table: str | None = None
    used_range: str | None = None
    empty_rows: int | None = None
    empty_columns: list[str] = Field(default_factory=list)
    formula_cells: int | None = None
    date_cells: int | None = None
    inexact_numbers: int | None = None
    selection_rule: str | None = None
    converted: list[ConvertedColumn] = Field(default_factory=list)
    kept_as_text: list[KeptColumn] = Field(default_factory=list)
    rules: list[str]
    problems: list[str] = Field(default_factory=list)


class InspectionScope(BaseModel):
    execution_id: UUID
    version_id: UUID
    table_sha256: str
    profile_sha256: str
    rules: Literal["dataset-inspection-v1"] = "dataset-inspection-v1"
    computed_at: datetime


class Inspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: InspectionScope
    summary: Summary
    columns: list[ColumnInspection]
    findings: list[Finding]
    periods: list[PeriodCandidate]
    file: FileInspection
    limitations: list[str]


class ColumnAnnotation(BaseModel):
    """Corrección manual guardada (última de la columna en la misma fuente)."""

    column: str
    role: Role | None
    nature: Nature | None
    time_format: TimeFormat | None
    notes: str | None
    confirmed: bool
    version_id: UUID
    created_at: datetime


class DictionaryEntry(BaseModel):
    column_id: UUID
    name: str
    technical_type: TechnicalType
    nature: Nature
    role: Role
    group: Group
    description: str
    distinct: int
    nulls: int
    status: EntryStatus
    origin: str
    automatic_nature: Nature
    automatic_role: Role
    time_format: TimeFormat | None = None
    notes: str | None = None
    inherited: bool = False
    updated_at: datetime | None = None


class AnnotationRequest(BaseModel):
    """Corrección de una columna. Sustituye a la anterior; todo vacío y sin confirmar vuelve a
    la clasificación automática. Nunca cambia el archivo ni los cálculos."""

    model_config = ConfigDict(extra="forbid")
    column_id: UUID
    role: Role | None = None
    nature: Nature | None = None
    time_format: TimeFormat | None = None
    notes: str | None = Field(default=None, max_length=500)
    confirmed: bool = False


class InspectionView(BaseModel):
    state: Literal["queued", "running", "ready", "failed", "unavailable"]
    execution_id: UUID | None = None
    reason: str | None = None
    inspection: Inspection | None = None
    dictionary: list[DictionaryEntry] = Field(default_factory=list)
    # Distribución por clasificación vigente (con las correcciones del usuario).
    groups: dict[Group, int] = Field(default_factory=dict)
