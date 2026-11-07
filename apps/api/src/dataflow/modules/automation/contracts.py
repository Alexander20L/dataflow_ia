"""Política de automatización (Fase 11B, ADR-023).

Una política por proyecto, con revisiones inmutables, autoriza operaciones de limpieza concretas
sobre columnas concretas y fija barreras sobre el efecto. Los porcentajes globales son barreras
adicionales, nunca autorización suficiente. Desactivada y sin operaciones por defecto.

Las columnas se nombran por su **nombre exacto** (los IDs cambian en cada importación, Fase 6B):
la política se aplica a cualquier carga con esos nombres y es siempre una restricción.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CleaningOperation = Literal[
    "cleaning.normalize_null_tokens",
    "cleaning.trim_whitespace",
    "cleaning.cast",
    "cleaning.filter_rows",
    "cleaning.deduplicate",
]
ALL_COLUMNS = "*"
POLICY_VERSION: Literal["automation-policy@1"] = "automation-policy@1"


class AutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnScope(AutomationModel):
    """Columnas (por nombre exacto) en las que se permite una operación; `*` = todas."""

    operation: CleaningOperation
    columns: list[str] = Field(min_length=1, max_length=128)

    @field_validator("columns")
    @classmethod
    def unique_names(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not name or len(name) > 200 for name in value):
            raise ValueError("Nombres de columna únicos de 1 a 200 caracteres.")
        if ALL_COLUMNS in value and len(value) > 1:
            raise ValueError("«*» ya incluye todas las columnas.")
        return value


class NullTokens(AutomationModel):
    column: str = Field(min_length=1, max_length=200)
    tokens: list[str] = Field(min_length=1, max_length=20)

    @field_validator("tokens")
    @classmethod
    def exact_tokens(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not t or len(t) > 100 for t in value):
            raise ValueError("Marcadores únicos de 1 a 100 caracteres.")
        return value


Percent = Decimal


class PolicyContent(AutomationModel):
    schema_version: Literal["automation-policy@1"] = POLICY_VERSION
    enabled: bool = False
    allowed_operations: list[CleaningOperation] = Field(default_factory=list)
    column_scopes: list[ColumnScope] = Field(default_factory=list)
    null_tokens_by_column: list[NullTokens] = Field(default_factory=list)
    max_excluded_rows_pct: Percent = Field(default=Decimal(0), ge=0, le=100, decimal_places=2)
    max_nulls_created_pct: Percent = Field(default=Decimal(0), ge=0, le=100, decimal_places=2)
    max_rounded_cells: int = Field(default=0, ge=0)
    min_output_rows: int = Field(default=1, ge=0)
    evaluate_quality_rules: bool = True

    @model_validator(mode="after")
    def coherent(self) -> "PolicyContent":
        if len(set(self.allowed_operations)) != len(self.allowed_operations):
            raise ValueError("Cada operación sólo puede autorizarse una vez.")
        scoped = [scope.operation for scope in self.column_scopes]
        if len(set(scoped)) != len(scoped):
            raise ValueError("Cada operación sólo puede tener un alcance de columnas.")
        if not set(scoped) <= set(self.allowed_operations):
            raise ValueError("Sólo las operaciones autorizadas pueden tener alcance.")
        columns = [item.column for item in self.null_tokens_by_column]
        if len(set(columns)) != len(columns):
            raise ValueError("Cada columna sólo puede tener una lista de marcadores.")
        return self


class PolicyRevision(AutomationModel):
    id: UUID
    family_id: UUID
    project_id: UUID
    revision: int
    previous_revision_id: UUID | None
    content: PolicyContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class SavePolicyRequest(AutomationModel):
    expected_revision: int = Field(ge=0, strict=True)
    content: PolicyContent


ReasonCode = Literal[
    "POLICY_MISSING",
    "POLICY_DISABLED",
    "PLAN_INVALID",
    "EFFECT_NOT_READY",
    "EFFECT_BREAKDOWN_MISSING",
    "OPERATION_NOT_AUTHORIZED",
    "COLUMN_NOT_AUTHORIZED",
    "TOKENS_NOT_AUTHORIZED",
    "IDENTIFIER_CONVERSION",
    "EXCLUDED_ROWS_ABOVE_LIMIT",
    "NULLS_CREATED_ABOVE_LIMIT",
    "ROUNDED_CELLS_ABOVE_LIMIT",
    "OUTPUT_ROWS_BELOW_MINIMUM",
]


class Reason(AutomationModel):
    code: ReasonCode
    message: str
    step_id: str | None = None
    column: str | None = None
    measured: str | None = None
    limit: str | None = None


class Evaluation(AutomationModel):
    decision: Literal["approved", "blocked"]
    reasons: list[Reason]


class PolicyDecision(AutomationModel):
    """Resultado de evaluar una vista previa con la política vigente. Si se aprueba, existe una
    aprobación normal del efecto exacto (`approval_id`) atribuida a quien guardó la política."""

    preview_execution_id: UUID
    effect_sha256: str | None
    policy_revision_id: UUID | None
    evaluation: Evaluation
    approval_id: UUID | None


class ApprovalOrigin(AutomationModel):
    """Si una aprobación de limpieza la concedió una política: revisión exacta, ejecutor
    (`manual` si una persona pidió evaluar, `pipeline` en la Fase 11C) y evaluación."""

    approval_id: UUID
    automatic: bool
    policy_revision_id: UUID | None = None
    policy_revision: int | None = None
    executor: str | None = None
    pipeline_run_id: UUID | None = None
    evaluation: Evaluation | None = None
    created_at: datetime | None = None


# --- Hechos para la evaluación pura ---


@dataclass(frozen=True)
class PlannedStep:
    id: str
    operation: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ColumnEffect:
    column_id: str
    modified_cells: int
    created_nulls: int


@dataclass(frozen=True)
class EffectFacts:
    input_rows: int
    output_rows: int
    excluded_rows: int
    created_nulls: int
    rounded_cells: int
    columns: list[ColumnEffect] | None  # None: vista previa anterior a 11B, sin desglose


@dataclass(frozen=True)
class PreviewFacts:
    """Lo que la evaluación necesita de una vista previa terminada (bootstrap lo reúne)."""

    execution_id: UUID
    project_id: UUID
    state: str
    plan_valid: bool
    steps: list[PlannedStep]
    column_names: dict[str, str]  # ID de columna → nombre en la tabla de entrada
    effect_sha256: str | None
    effect: EffectFacts | None
    active_approval_id: UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# --- Puertos ---


class PolicyCleaning(Protocol):
    """Puerto sobre cleaning y proyectos (bootstrap lo implementa)."""

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None: ...
    def preview_facts(self, owner: UUID, execution: UUID) -> PreviewFacts: ...
    def approve_with(
        self,
        owner: UUID,
        execution: UUID,
        effect_sha256: str,
        correlation: str,
        before_commit: Callable[[UUID], None],
    ) -> UUID:
        """Aprobación normal del efecto exacto (ADR-015); `before_commit` registra el vínculo
        con la política en la misma transacción. Devuelve el ID de la aprobación."""
        ...

    def revoke_if_pending(self, owner: UUID, approval: UUID, correlation: str) -> bool:
        """Revoca una aprobación aún no aplicada; False si ya se aplicó o está en curso."""
        ...


class PolicyRepository(Protocol):
    def lock_project(self, project: UUID) -> None: ...
    def head(self, owner: UUID, project: UUID) -> PolicyRevision | None: ...
    def get(self, owner: UUID, revision: UUID) -> PolicyRevision: ...
    def replay(
        self, owner: UUID, project: UUID, key: UUID, fingerprint: str
    ) -> PolicyRevision | None: ...
    def append(
        self,
        owner: UUID,
        project: UUID,
        content: PolicyContent,
        content_sha256: str,
        key: UUID,
        fingerprint: str,
        correlation: str,
    ) -> PolicyRevision: ...
    def record_approval(
        self,
        approval: UUID,
        policy: PolicyRevision,
        preview: UUID,
        effect_sha256: str,
        evaluation: Evaluation,
        executor: str,
        pipeline_run_id: UUID | None,
    ) -> None: ...
    def approval_origin(self, owner: UUID, approval: UUID) -> ApprovalOrigin: ...
    def pending_automatic_approvals(self, owner: UUID, project: UUID) -> list[UUID]: ...
