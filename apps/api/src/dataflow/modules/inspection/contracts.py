"""Pestaña Dataset (Fases 22 y 23, ADR-039 y ADR-040): inspección estructural, estadística y de
calidad de una versión, calculada una vez por el motor sobre la tabla completa
(`dataset-inspection-v2`), y correcciones del diccionario guardadas como metadatos.

La inspección nunca modifica el archivo ni la tabla leída. Desde la Fase 23 (ADR-040) las
correcciones del diccionario sí cuentan en las etapas siguientes: la comprensión las usa como
clasificación de partida, las columnas con datos personales no se envían a la IA y los textos
declarados como nulos crean una versión derivada (el original no cambia).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.ingestion.contracts import ConvertedColumn, KeptColumn, SheetFacts

INSPECTION_RULES = "dataset-inspection-v3"
RulesVersion = Literal["dataset-inspection-v1", "dataset-inspection-v2", "dataset-inspection-v3"]

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


PersonalKind = Literal["name", "document", "email", "phone", "address"]


class TokenCount(BaseModel):
    token: str
    count: int = Field(ge=0)
    # Fase 23: escrituras exactas del original (p. ej. «N/A» y «n/a»), para poder declararlas
    # como nulos con una coincidencia exacta de la celda completa.
    variants: list[str] = Field(default_factory=list)


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


class Outliers(BaseModel):
    """Valores atípicos por las vallas de Tukey (Fase 23). Es un aviso: no se elimina nada."""

    mild_lower: str
    mild_upper: str
    extreme_lower: str
    extreme_upper: str
    # Fuera de [Q1 − 1,5·IQR, Q3 + 1,5·IQR]; los extremos (fuera de 3·IQR) están incluidos.
    count: int = Field(ge=0)
    extreme: int = Field(ge=0)
    method: str


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
    outliers: Outliers | None = None


class ValueDomain(BaseModel):
    """Dominio evidente de una columna numérica (Fase 23) y cuántos valores lo incumplen."""

    # Fase 28: «rating» = escala de valoración (1–5, 0–5, 1–10 o 0–10) por nombre y valores.
    kind: Literal["percent", "non_negative", "rating"]
    lower: str
    upper: str | None
    outside: int = Field(ge=0)
    reason: str


class OrdinalHint(BaseModel):
    """Enteros con pocos valores que parecen una escala ordenada. Es una candidata: sólo cambia la
    clasificación si el usuario la confirma en el Diccionario."""

    order: list[str]
    reason: str


class PersonalHint(BaseModel):
    """Columna que parece contener datos personales (Fase 23)."""

    kind: PersonalKind
    reason: str


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
    # Fase 23 (`dataset-inspection-v2`).
    dichotomous: bool = False
    domain: ValueDomain | None = None
    ordinal_candidate: OrdinalHint | None = None
    personal: PersonalHint | None = None
    # Fase 28 (`date-role-v1`): una fecha registra eventos o describe al registro.
    date_role: Literal["events", "attribute"] | None = None
    date_role_reason: str | None = None


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
    source: Literal[
        "dataset-inspection-v1",
        "dataset-inspection-v2",
        "dataset-inspection-v3",
        "automatic-quality-v1",
    ]


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
    # Fase 23: filas repetidas sin contar los identificadores (None si no hay identificadores
    # o si no queda ninguna otra columna) y columnas excluidas para ese recuento.
    duplicate_rows_without_ids: int | None = None
    identifier_columns: list[str] = Field(default_factory=list)
    personal_columns: list[str] = Field(default_factory=list)


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
    rules: RulesVersion = "dataset-inspection-v3"
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
    # Fase 23 (migración 0023): textos que el usuario declara como «sin dato» y su decisión sobre
    # el aviso de datos personales (None: sin decidir; vale la detección automática).
    null_tokens: list[str] = Field(default_factory=list)
    personal: bool | None = None


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
    # Fase 23.
    dichotomous: bool = False
    ordinal_candidate: OrdinalHint | None = None
    personal: bool = False
    personal_kind: PersonalKind | None = None
    personal_status: Literal["automatic", "confirmed", "rejected", "marked"] | None = None
    null_tokens: list[str] = Field(default_factory=list)


class AnnotationRequest(BaseModel):
    """Corrección de una columna. Sustituye a la anterior; todo vacío y sin confirmar vuelve a
    la clasificación automática. Nunca cambia el archivo: desde la Fase 23 la clasificación
    corregida se usa en la comprensión (que se recalcula) y los textos declarados como nulos
    crean una versión derivada."""

    model_config = ConfigDict(extra="forbid")
    column_id: UUID
    role: Role | None = None
    nature: Nature | None = None
    time_format: TimeFormat | None = None
    notes: str | None = Field(default=None, max_length=500)
    confirmed: bool = False
    null_tokens: list[str] = Field(default_factory=list, max_length=20)
    personal: bool | None = None


class Recalculation(BaseModel):
    """Trabajo en marcha o terminado que provocó la última corrección (Fase 23)."""

    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    kind: Literal["comprehension", "null_cleaning"]
    execution_id: UUID
    # Sólo para `null_cleaning`: la versión derivada (existe cuando termina bien).
    derived_version_id: UUID | None = None
    reason: str | None = None


class InspectionView(BaseModel):
    state: Literal["queued", "running", "ready", "failed", "unavailable"]
    execution_id: UUID | None = None
    reason: str | None = None
    inspection: Inspection | None = None
    dictionary: list[DictionaryEntry] = Field(default_factory=list)
    # Distribución por clasificación vigente (con las correcciones del usuario).
    groups: dict[Group, int] = Field(default_factory=dict)
    recalculation: Recalculation | None = None
