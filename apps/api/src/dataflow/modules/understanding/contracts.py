from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OverviewKpi(BaseModel):
    id: str
    label: str
    value: str
    unit: Literal["count", "percent", "number"]
    column: str | None = None
    valid_rows: int | None = None
    excluded_rows: int | None = None


class OverviewPoint(BaseModel):
    label: str
    # Registros del punto. En los gráficos de una medida (automatic-overview-v3), `amount` es
    # la suma exacta de esa medida en el grupo y `value` cuántos registros la aportan.
    value: int = Field(ge=0)
    amount: str | None = None


class OverviewChart(BaseModel):
    id: str
    title: str
    type: Literal["bar", "line"]
    column: str | None = None
    points: list[OverviewPoint]
    measure: str | None = None
    valid_rows: int
    excluded_rows: int
    omitted_groups: int = 0


class OverviewDetail(BaseModel):
    columns: list[str]
    rows: list[list[str | None]]
    total_rows: int
    truncated: bool
    cells_truncated: bool = False


class AutomaticColumnHint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=0)
    name: str
    role: Literal["identifier", "date", "numeric", "category", "text", "empty"]
    statistics_allowed: bool = False
    evidence: list[str]


class AutomaticTemplateHint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    template: Literal["sales@1", "inventory@1"]
    label: str
    matched_roles: list[str]
    missing_roles: list[str]


class AutomaticInterpretation(BaseModel):
    """Lectura heurística, no una revisión semántica confirmada."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rules_version: Literal["automatic-interpretation-v1"] = "automatic-interpretation-v1"
    context: Literal["generic", "sales", "inventory", "ambiguous"]
    label: str
    summary: str
    columns: list[AutomaticColumnHint]
    candidates: list[AutomaticTemplateHint]
    available_analyses: list[str]
    limitations: list[str]


ColumnRole = Literal["identifier", "dimension", "measure", "time", "text", "empty"]
Status = Literal["known", "unknown", "ambiguous"]


class AnalyticalColumn(BaseModel):
    """Papel de una columna según automatic-interpretation-v2, con su evidencia."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=0)
    name: str
    role: ColumnRole
    time_part: Literal["date", "year", "month"] | None = None
    additivity: Literal["additive", "semi_additive", "non_additive", "unknown"] | None = None
    monetary: bool = False
    currency: Status | None = None
    currency_code: str | None = None
    unit: Status | None = None
    unit_label: str | None = None
    evidence: list[str]


class TimeAxis(BaseModel):
    """Eje temporal mensual: una fecha o Año + Mes compuestos. No rellena meses vacíos."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["date", "year_month"]
    columns: list[str]
    granularity: Literal["month"] = "month"
    first: str | None
    last: str | None
    periods: int
    years: list[str]
    missing: list[str]
    missing_count: int
    incomplete: list[str]
    unparsed_rows: int
    unparsed_sample_rows: list[int] = []


class KeyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    columns: list[str]
    unique: bool
    duplicate_rows: int = Field(ge=0)
    duplicate_sample_rows: list[int] = []
    evidence: str


class MeasureRelationship(BaseModel):
    """Relación comprobada fila a fila: `target` ≈ producto de `factors` con tolerancia."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["product"] = "product"
    target: str
    factors: list[str]
    compared_rows: int
    matching_rows: int
    tolerance: str
    exception_sample_rows: list[int] = []


class ColumnDependency(BaseModel):
    """Cada valor de `determinant` debería tener un único `dependent` (p. ej. código → nombre)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    determinant: str
    dependent: str
    determinant_values: int
    conflicting_values: int
    conflicting_rows: int
    sample_row_numbers: list[int] = []
    examples: list[str]


class LimitedAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject: str
    columns: list[str]
    reason: str


class AnalyticalInterpretation(BaseModel):
    """Interpretación sustentada por reglas: hipótesis con evidencia, no confirmaciones."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rules_version: Literal["automatic-interpretation-v2"] = "automatic-interpretation-v2"
    context: Literal["generic", "sales", "inventory", "ambiguous"]
    label: str
    summary: str
    row_meaning: str
    columns: list[AnalyticalColumn]
    time: TimeAxis | None
    keys: list[KeyCandidate]
    relationships: list[MeasureRelationship]
    dependencies: list[ColumnDependency]
    available_analyses: list[str]
    limited_analyses: list[LimitedAnalysis]
    limitations: list[str]


class AutomaticOverview(BaseModel):
    """Snapshot calculado al importar: no requiere semántica, política ni IA."""

    model_config = ConfigDict(extra="forbid")
    algorithm: Literal[
        "automatic-overview-v1", "automatic-overview-v2", "automatic-overview-v3"
    ] = "automatic-overview-v1"
    source_sha256: str
    kpis: list[OverviewKpi]
    charts: list[OverviewChart]
    table_detail: OverviewDetail
    limitations: list[str]
    interpretation: AutomaticInterpretation | None = None
    analysis: AnalyticalInterpretation | None = None


class NumericSummary(BaseModel):
    count: int
    total: str
    mean: str
    minimum: str
    maximum: str


class ColumnProfile(BaseModel):
    name: str
    # Tipo físico de la columna publicada (Fase 6: también columnas tipadas del catálogo).
    technical_type: Literal["string", "integer", "decimal", "date", "boolean"] = "string"
    suggested_type: Literal["string", "integer", "decimal", "date", "boolean"]
    null_count: int
    unique_count: int
    examples: list[str]
    numeric: NumericSummary | None = None


class DatasetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    engine_version: str
    polars_version: str
    source_sha256: str
    encoding: Literal["utf-8-sig"] = "utf-8-sig"
    separator: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    overview: AutomaticOverview | None = None


class ProfileParameters(BaseModel):
    """Parámetros de understanding.profile@1."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: Literal["column-profile-v1"] = "column-profile-v1"


class AutomaticProfileParameters(BaseModel):
    """understanding.profile@2: perfil y dashboard inicial sin configuración."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: Literal["column-profile-overview-v1"] = "column-profile-overview-v1"


class InterpretedProfileParameters(BaseModel):
    """understanding.profile@3: dashboard e interpretación descriptiva sin confirmación."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: Literal["column-profile-interpreted-v1"] = "column-profile-interpreted-v1"


class AnalyticalProfileParameters(BaseModel):
    """understanding.profile@4: interpretación analítica (automatic-interpretation-v2) y
    dashboard por medidas (automatic-overview-v3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: Literal["column-profile-analytical-v1"] = "column-profile-analytical-v1"


# Campos añadidos en profile@4: las versiones anteriores los omiten para que sus artefactos
# se serialicen exactamente igual que antes.
V4_FIELDS: dict[str, Any] = {
    "analysis": True,
    "charts": {"__all__": {"measure": True, "points": {"__all__": {"amount"}}}},
}


def profile_json(profile: DatasetProfile, version: int) -> str:
    """Serialización canónica de un perfil según la versión de understanding.profile."""
    if version == 1:
        return profile.model_dump_json(exclude={"overview"})
    if version == 2:
        return profile.model_dump_json(exclude={"overview": {"interpretation": True, **V4_FIELDS}})
    if version == 3:
        return profile.model_dump_json(exclude={"overview": V4_FIELDS})
    return profile.model_dump_json()
