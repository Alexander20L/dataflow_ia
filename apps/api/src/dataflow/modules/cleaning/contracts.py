from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dataflow.modules.cleaning.conversion import FORMATS, CastFormat, CastType
from dataflow.modules.planning.public import COLUMN_REF
from dataflow.platform.data_types import ALL_TYPES, TEXT, DataType

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


NullKeys = Literal["reject", "group_nulls"]


class NormalizeNullTokensParameters(BaseModel):
    """cleaning.normalize_null_tokens@1: una celda de texto igual EXACTAMENTE a un token pasa a
    nulo (sin recortar ni ignorar mayúsculas). Los tokens van explícitos en el plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    column_ids: list[UUID] = Field(
        min_length=1, max_length=128, json_schema_extra={COLUMN_REF: True}
    )
    tokens: list[str] = Field(min_length=1, max_length=20)

    _unique = field_validator("column_ids")(unique_columns)

    @field_validator("tokens")
    @classmethod
    def token_limits(cls, values: list[str]) -> list[str]:
        if any(not 1 <= len(value) <= 100 for value in values) or len(set(values)) != len(values):
            raise ValueError("Tokens únicos de 1 a 100 caracteres.")
        return values


class DeduplicateParameters(BaseModel):
    """cleaning.deduplicate@1: excluye los registros cuya clave ya apareció antes en el orden de
    la tabla (conserva la primera aparición). `null_keys`: «reject» hace fallar el plan si una
    clave tiene nulos (se listan); «group_nulls» trata los nulos como iguales entre sí."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    column_ids: list[UUID] = Field(
        min_length=1, max_length=128, json_schema_extra={COLUMN_REF: True}
    )
    keep: Literal["first"] = "first"
    null_keys: NullKeys

    _unique = field_validator("column_ids")(unique_columns)


class CastParameters(BaseModel):
    """cleaning.cast@1: una columna de texto a un tipo y formato del catálogo. Sin recortar
    espacios, sin exclusiones ni valores imputados: un solo valor que no convierte hace fallar
    el plan (política estricta) y la vista previa lista los valores y su motivo."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    column_id: UUID = Field(json_schema_extra={COLUMN_REF: True})
    type: CastType
    format: CastFormat
    scale: int | None = Field(default=None, ge=0, le=12)
    confirm_identifier_conversion: bool = False

    @model_validator(mode="after")
    def compatible_format(self) -> "CastParameters":
        if FORMATS[self.type] != self.format:
            raise ValueError(f"El formato «{self.format}» no corresponde al tipo «{self.type}».")
        if (self.type == "decimal") != (self.scale is not None):
            raise ValueError("La escala (0 a 12) es obligatoria para decimal y sólo para decimal.")
        return self


def cast_column_types(parameters: CastParameters) -> dict[str, frozenset[DataType]]:
    return {"column_id": TEXT}


def cast_output_schema(parameters: CastParameters, schema: Any) -> dict[UUID, DataType]:
    return {**schema, parameters.column_id: parameters.type}


def tokens_column_types(
    parameters: NormalizeNullTokensParameters,
) -> dict[str, frozenset[DataType]]:
    return {"column_ids": TEXT}


def deduplicate_column_types(parameters: DeduplicateParameters) -> dict[str, frozenset[DataType]]:
    return {"column_ids": ALL_TYPES}


def trim_column_types(parameters: TrimWhitespaceParameters) -> dict[str, frozenset[DataType]]:
    return {"column_ids": TEXT}


def filter_column_types(parameters: FilterRowsParameters) -> dict[str, frozenset[DataType]]:
    # «Sólo espacios» únicamente tiene sentido en texto; «nulo» en cualquier tipo.
    return {"column_ids": TEXT if parameters.predicate == "is_whitespace_only" else ALL_TYPES}


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
    # Fase 6: celdas de texto convertidas a decimal cuyo valor cambió al redondear.
    rounded_cells: int = Field(default=0, ge=0)


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


class CleaningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalView(CleaningModel):
    id: UUID
    plan_revision_id: UUID
    preview_execution_id: UUID
    effect_sha256: str
    input_artifact_sha256: str
    semantic_revision_id: UUID | None
    config_sha256: str
    environment_sha256: str
    approved_by: UUID
    approved_at: datetime
    revoked_at: datetime | None
    status: Literal["active", "revoked"]


class ApplyStatus(CleaningModel):
    execution_id: UUID
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None
    error_message: str | None


class FailureSample(CleaningModel):
    """Un valor que impide completar la limpieza (política estricta)."""

    column_id: str
    column: str
    source_row: int = Field(ge=1)
    value: str | None
    reason: str
    message: str


class PreviewFailure(CleaningModel):
    """Detalle de una vista previa fallida: conteo total exacto y hasta 50 casos."""

    code: str
    total: int = Field(ge=1)
    samples: list[FailureSample] = Field(max_length=50)


class PreviewView(CleaningModel):
    execution_id: UUID
    plan_revision_id: UUID
    project_id: UUID
    version_id: UUID
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None
    error_message: str | None
    effect_sha256: str | None
    manifest: EffectManifest | None
    samples: list[EffectSample]
    approval: ApprovalView | None
    apply: ApplyStatus | None
    failure: PreviewFailure | None = None


class LineageOperation(CleaningModel):
    step_id: str
    operation: str
    version: int
    parameters: dict[str, Any]


class LineageView(CleaningModel):
    version_id: UUID
    kind: Literal["imported", "derived"]
    parent_version_id: UUID | None
    producer_execution_id: UUID | None
    plan_revision_id: UUID | None
    effect_sha256: str | None
    operations: list[LineageOperation]


class ApprovalRepository(Protocol):
    def get(self, owner: UUID, approval: UUID) -> ApprovalView: ...
    def active(self, preview: UUID) -> ApprovalView | None: ...
    def add(self, approval: ApprovalView, correlation: str) -> None: ...
    def revoke(self, approval: UUID, at: datetime, correlation: str) -> None: ...
