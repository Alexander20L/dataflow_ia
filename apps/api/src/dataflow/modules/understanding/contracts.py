from typing import Literal

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
    value: int = Field(ge=0)


class OverviewChart(BaseModel):
    id: str
    title: str
    type: Literal["bar", "line"]
    column: str | None = None
    points: list[OverviewPoint]
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


class AutomaticOverview(BaseModel):
    """Snapshot calculado al importar: no requiere semántica, política ni IA."""

    model_config = ConfigDict(extra="forbid")
    algorithm: Literal["automatic-overview-v1", "automatic-overview-v2"] = "automatic-overview-v1"
    source_sha256: str
    kpis: list[OverviewKpi]
    charts: list[OverviewChart]
    table_detail: OverviewDetail
    limitations: list[str]
    interpretation: AutomaticInterpretation | None = None


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
