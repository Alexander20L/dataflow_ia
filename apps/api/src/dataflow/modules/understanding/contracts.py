from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class ProfileParameters(BaseModel):
    """Parámetros de understanding.profile@1."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: Literal["column-profile-v1"] = "column-profile-v1"
