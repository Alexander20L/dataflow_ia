from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.datasets.contracts import StoredObject

RunKind = Literal["csv_import", "table_analysis"]
RunState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ArtifactKind = Literal["table", "profile", "quality", "legacy_diagnostic"]


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_catalog: Literal["analysis-v1"] = "analysis-v1"
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


@dataclass(frozen=True)
class PreparedWork:
    reference: StoredObject
    source_sha256: str
    config: ProcessingConfig
    separator: str
    quality_only: bool = False


class Executor(Protocol):
    def prepare(self, lease: Lease) -> PreparedWork: ...
    def compute(self, lease: Lease, work: PreparedWork) -> list[ArtifactOutput]: ...


class PublicationHook(Protocol):
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
    def get(self, owner: UUID, execution: UUID) -> Execution: ...
    def for_version(self, owner: UUID, version: UUID) -> list[Execution]: ...
    def representations(self, owner: UUID, version: UUID) -> list[Artifact]: ...
    def artifact(self, owner: UUID, artifact: UUID) -> Artifact: ...
    def artifacts(self, owner: UUID, execution: UUID) -> list[Artifact]: ...
    def attempts(self, owner: UUID, execution: UUID) -> list[dict[str, Any]]: ...
    def cancel(self, owner: UUID, execution: UUID) -> Execution: ...
    def claim(self, kinds: set[RunKind], environment: dict[str, Any]) -> Lease | None: ...
    def stage(self, lease: Lease, outputs: list[ArtifactOutput]) -> list[Artifact] | None: ...
    def succeed(self, lease: Lease) -> bool: ...
    def fail(self, lease: Lease, code: str, message: str, retryable: bool) -> None: ...
