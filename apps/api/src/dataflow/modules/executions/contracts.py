from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.datasets.contracts import StoredObject

# report_render (Fase 9): informe exacto a PDF; su entrada es una instantánea del informe.
RunKind = Literal[
    "csv_import", "table_analysis", "plan", "cleaning_preview", "cleaning_apply", "report_render"
]
RunState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ArtifactKind = Literal[
    "table",
    "profile",
    "quality",
    "legacy_diagnostic",
    "effect",
    "effect_samples",
    "row_lineage",
    "quality_rules",
    "analysis_result",
    "report_pdf",
]


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # analysis-v1: Fase 4 (lectura, perfil, calidad); analysis-v2: añade cleaning.* (Fase 5);
    # analysis-v3: conversiones, tokens nulos y deduplicación (Fase 6A);
    # analysis-v4: quality.evaluate@2 con reglas del usuario (Fase 6B);
    # analysis-v5: analytics.query@1 con métricas definidas (Fase 7A);
    # analysis-v6: analytics.query@2 con comparaciones, ranking y participación (Fase 7B);
    # analysis-v7: analytics.query@3 con sum_product y último corte (Fase 11E).
    # Los planes guardados conservan el valor con el que se crearon (y su hash).
    operation_catalog: Literal[
        "analysis-v1",
        "analysis-v2",
        "analysis-v3",
        "analysis-v4",
        "analysis-v5",
        "analysis-v6",
        "analysis-v7",
    ] = "analysis-v7"
    rule_catalog: Literal["csv-quality-v1"] = "csv-quality-v1"
    max_rows: int = Field(ge=1, le=100000)
    max_columns: int = Field(ge=1, le=128)
    max_field_chars: Literal[10000] = 10000
    max_attempts: int = Field(default=3, ge=1, le=3)
    timeout_seconds: int = Field(ge=5, le=60)
    lease_seconds: Literal[120] = 120
    decimal_precision: Literal[50] = 50
    rounding: Literal["HALF_EVEN"] = "HALF_EVEN"
    order: Literal["preserve_input"] = "preserve_input"


@dataclass(frozen=True)
class PlanRevision:
    id: UUID
    family_id: UUID
    revision: int
    content: dict[str, Any]
    content_sha256: str
    created_by: UUID
    created_at: datetime

    @property
    def config(self) -> ProcessingConfig:
        return ProcessingConfig.model_validate(self.content["config"])


@dataclass(frozen=True)
class PlanBinding:
    """Vínculo de un plan de usuario con su proyecto, tabla exacta y revisión semántica."""

    project_id: UUID
    input_artifact_id: UUID
    input_artifact_sha256: str
    semantic_revision_id: UUID | None


@dataclass(frozen=True)
class UserPlan:
    revision: PlanRevision
    binding: PlanBinding
    head_revision: int


@dataclass(frozen=True)
class Execution:
    id: UUID
    project_id: UUID
    owner_id: UUID
    version_id: UUID
    kind: RunKind
    state: RunState
    attempts: int
    plan: PlanRevision | None
    input_artifact_id: UUID | None
    input_artifact_sha256: str | None
    row_count: int | None
    column_count: int | None
    error_code: str | None
    error_message: str | None
    reproducibility: Literal["complete", "legacy_partial"]
    created_at: datetime
    finished_at: datetime | None
    # Clave idempotente de la solicitud; en cleaning_apply identifica la aprobación aplicada.
    request_key: UUID | None = None


@dataclass(frozen=True)
class Lease:
    execution: Execution
    attempt_id: UUID
    token: UUID
    environment: dict[str, Any]

    @property
    def execution_id(self) -> UUID:
        return self.execution.id

    @property
    def version_id(self) -> UUID:
        return self.execution.version_id

    @property
    def owner_id(self) -> UUID:
        return self.execution.owner_id


@dataclass(frozen=True)
class ArtifactOutput:
    id: UUID
    step_id: str
    slot: str
    kind: ArtifactKind
    content: StoredObject
    media_type: str
    row_count: int
    column_count: int
    columns: list[dict[str, Any]] | None = None
    logical_content_sha256: str | None = None
    # Versión a la que pertenece el artefacto; por defecto, la de la ejecución (su entrada).
    version_id: UUID | None = None


@dataclass(frozen=True)
class Artifact:
    id: UUID
    execution_id: UUID
    version_id: UUID
    attempt_id: UUID | None
    step_id: str
    slot: str
    kind: ArtifactKind
    content: StoredObject
    row_count: int | None
    column_count: int | None
    columns: list[dict[str, Any]] | None
    logical_content_sha256: str | None


InputKind = Literal["source", "table", "report"]


@dataclass(frozen=True)
class StepInput:
    """Entrada de un paso: el input fijado del plan o la tabla producida por un paso anterior."""

    kind: InputKind
    content: StoredObject
    # Procedencia que conservan los diagnósticos: hash del original y separador efectivo.
    source_sha256: str
    separator: str = ","
    # Esquema publicado (IDs de columna) y si la tabla lleva la columna interna de linaje.
    columns: list[dict[str, Any]] | None = None
    lineage: bool = False


@dataclass(frozen=True)
class PlanStepSpec:
    id: str
    operation: str
    version: int
    input_step: str | None  # None: consume el input del plan.
    parameters: dict[str, Any]


@dataclass(frozen=True)
class StepResult:
    outputs: list[ArtifactOutput]
    table: StepInput | None = None


class InputResolver(Protocol):
    """Verifica autorización y hashes del input fijado; único punto con acceso a metadatos."""

    def prepare(self, lease: Lease) -> StepInput: ...


class StepExecutor(Protocol):
    """Calcula un paso sin acceso a la base de datos dentro de `timeout` segundos."""

    @property
    def output_kind(self) -> ArtifactKind: ...
    @property
    def transforms_data(self) -> bool: ...
    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult: ...


class StepRegistry(Protocol):
    def executor(self, operation: str, version: int) -> StepExecutor | None: ...


class PlanFinalizer(Protocol):
    """Salidas de un tipo de ejecución que no se publican paso a paso (limpieza: efecto y tabla
    final). `prepare` se ejecuta con acceso a metadatos; `finalize`, sin base de datos."""

    @property
    def expected(self) -> set[tuple[str, ArtifactKind]]: ...
    def prepare(self, lease: Lease) -> Any: ...
    def finalize(
        self, lease: Lease, context: Any, source: StepInput, final: StepInput, timeout: float
    ) -> list[ArtifactOutput]: ...


class PlanResponse(BaseModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    revision: int
    previous_revision_id: UUID | None = None
    content: dict[str, Any]
    content_sha256: str
    created_by: UUID
    created_at: datetime


# DTO HTTP compartido por rutas de ejecuciones, ingesta y planificación (sin docstring: cambiaría
# la descripción del esquema OpenAPI).
class ExecutionResponse(BaseModel):
    id: UUID
    project_id: UUID
    version_id: UUID
    kind: RunKind
    state: RunState
    attempts: int
    plan: PlanResponse | None
    input_artifact_id: UUID | None
    input_artifact_sha256: str | None
    row_count: int | None
    column_count: int | None
    error_code: str | None
    error_message: str | None
    reproducibility: Literal["complete", "legacy_partial"]
    created_at: datetime
    finished_at: datetime | None


def execution_response(run: Execution) -> ExecutionResponse:
    plan = (
        PlanResponse(
            id=run.plan.id,
            family_id=run.plan.family_id,
            revision=run.plan.revision,
            content=run.plan.content,
            content_sha256=run.plan.content_sha256,
            created_by=run.plan.created_by,
            created_at=run.plan.created_at,
        )
        if run.plan
        else None
    )
    return ExecutionResponse(
        id=run.id,
        project_id=run.project_id,
        version_id=run.version_id,
        kind=run.kind,
        state=run.state,
        attempts=run.attempts,
        plan=plan,
        input_artifact_id=run.input_artifact_id,
        input_artifact_sha256=run.input_artifact_sha256,
        row_count=run.row_count,
        column_count=run.column_count,
        error_code=run.error_code,
        error_message=run.error_message,
        reproducibility=run.reproducibility,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


class PublicationHook(Protocol):
    def prepare(self, lease: Lease, outputs: list[ArtifactOutput]) -> None: ...
    def published(self, lease: Lease, artifacts: list[Artifact]) -> None: ...


class ExecutionRepository(Protocol):
    def find_request(
        self, owner: UUID, project: UUID, kind: RunKind, key: UUID, fingerprint: str
    ) -> Execution | None: ...
    def active_count(
        self, owner: UUID, project: UUID | None = None, kind: RunKind | None = None
    ) -> int: ...
    def counts(self, owner: UUID, kind: RunKind) -> dict[str, int]: ...
    def enqueue(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        kind: RunKind,
        key: UUID,
        fingerprint: str,
        plan: PlanRevision,
        correlation: str,
        input_artifact: UUID | None = None,
        input_sha256: str | None = None,
    ) -> Execution: ...
    def enqueue_existing_plan(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        key: UUID,
        fingerprint: str,
        plan: UUID,
        correlation: str,
        input_artifact: UUID,
        input_sha256: str,
        kind: RunKind = "plan",
    ) -> Execution: ...
    def save_plan_revision(self, plan: PlanRevision, binding: PlanBinding) -> None: ...
    def plan_revision(self, owner: UUID, revision: UUID) -> UserPlan: ...
    def lock_plan_family(self, owner: UUID, family: UUID) -> UserPlan: ...
    def plans_for_project(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[UserPlan], int]: ...
    def get(self, owner: UUID, execution: UUID) -> Execution: ...
    def for_version(self, owner: UUID, version: UUID) -> list[Execution]: ...
    def representations(self, owner: UUID, version: UUID) -> list[Artifact]: ...
    def artifact(self, owner: UUID, artifact: UUID) -> Artifact: ...
    def artifacts(self, owner: UUID, execution: UUID) -> list[Artifact]: ...
    def attempts(self, owner: UUID, execution: UUID) -> list[dict[str, Any]]: ...
    def error_details(self, owner: UUID, execution: UUID) -> tuple[str, dict[str, Any]] | None: ...
    def cancel(self, owner: UUID, execution: UUID) -> Execution: ...
    def claim(self, kinds: set[RunKind], environment: dict[str, Any]) -> Lease | None: ...
    def stage(self, lease: Lease, outputs: list[ArtifactOutput]) -> list[Artifact] | None: ...
    def succeed(self, lease: Lease) -> bool: ...
    def fail(
        self,
        lease: Lease,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None: ...
