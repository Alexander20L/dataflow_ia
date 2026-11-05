from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dataflow.modules.planning.public import COLUMN_REF

Predicate = Literal["is_null", "is_whitespace_only"]
Match = Literal["any", "all"]


def unique_columns(value: list[UUID]) -> list[UUID]:
    if len(set(value)) != len(value):
        raise ValueError("Cada columna sólo puede aparecer una vez.")
    return value


class TrimWhitespaceParameters(BaseModel):
    """cleaning.trim_whitespace@1: bordes SP/TAB/CR/LF; nulos se conservan; vacío → nulo."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    column_ids: list[UUID] = Field(
        min_length=1, max_length=128, json_schema_extra={COLUMN_REF: True}
    )

    _unique = field_validator("column_ids")(unique_columns)


class FilterRowsParameters(BaseModel):
    """cleaning.filter_rows@1: excluye registros que cumplen el predicado; conserva el orden."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    column_ids: list[UUID] = Field(
        min_length=1, max_length=128, json_schema_extra={COLUMN_REF: True}
    )
    predicate: Predicate
    match: Match = "any"

    _unique = field_validator("column_ids")(unique_columns)


class EffectCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_rows: int = Field(ge=0)
    output_rows: int = Field(ge=0)
    excluded_rows: int = Field(ge=0)
    modified_rows: int = Field(ge=0)
    modified_cells: int = Field(ge=0)
    created_nulls: int = Field(ge=0)


class EffectSample(BaseModel):
    """Ejemplo antes/después. `after` es None si el registro se excluye."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_row: int = Field(ge=1)
    change: Literal["modified", "excluded"]
    column_ids: list[str]
    before: dict[str, str | None]
    after: dict[str, str | None] | None


class EffectManifest(BaseModel):
    """Efecto exacto de una limpieza. Sin IDs temporales ni fechas: dos cálculos del mismo plan
    sobre la misma entrada y entorno producen el mismo documento y el mismo effect_sha256."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    plan: dict[str, Any]
    input: dict[str, Any]
    semantic_ref: dict[str, Any] | None
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output: dict[str, Any]
    row_lineage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    counts: EffectCounts


DERIVED_NAMESPACE = UUID("6f1c0b52-6c86-4f8e-9d3e-3c7f1f0a8b21")


def derived_version_id(producer_execution: UUID) -> UUID:
    """ID determinista de la versión derivada que publica una ejecución cleaning_apply: el
    finalizador asigna sus artefactos y la publicación registra la versión con el mismo ID."""
    return uuid5(DERIVED_NAMESPACE, f"derived:{producer_execution}")


@dataclass(frozen=True)
class ApprovedEffect:
    id: UUID
    plan_revision_id: UUID
    preview_execution_id: UUID
    effect_sha256: str
    revoked: bool


class ApprovalSource(Protocol):
    def approved_effect(self, approval: UUID) -> ApprovedEffect | None: ...
