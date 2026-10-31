from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from dataflow.bootstrap.dependencies import (
    Analysis,
    CurrentIdentity,
    DatasetAccess,
    ExecutionAccess,
)
from dataflow.modules.executions.contracts import Artifact, Execution, RunKind, RunState
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import SemanticReference

router = APIRouter(prefix="/api/v1", tags=["Executions"])


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table_artifact_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_kind: Literal["profile_quality", "quality_only"] = "profile_quality"
    semantic_ref: SemanticReference | None = None


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


class AttemptResponse(BaseModel):
    id: UUID
    number: int
    state: str
    environment: dict[str, Any]
    environment_sha256: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None


class ExecutionDetail(ExecutionResponse):
    attempt_history: list[AttemptResponse]


class ArtifactResponse(BaseModel):
    id: UUID
    execution_id: UUID
    version_id: UUID
    attempt_id: UUID | None
    step_id: str
    slot: str
    kind: Literal["table", "profile", "quality", "legacy_diagnostic"]
    object_id: UUID
    sha256: str
    byte_size: int
    row_count: int | None
    column_count: int | None
    columns: list[dict[str, Any]] | None
    logical_content_sha256: str | None


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


def artifact_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        execution_id=artifact.execution_id,
        version_id=artifact.version_id,
        attempt_id=artifact.attempt_id,
        step_id=artifact.step_id,
        slot=artifact.slot,
        kind=artifact.kind,
        object_id=artifact.content.object_id,
        sha256=artifact.content.sha256,
        byte_size=artifact.content.byte_size,
        row_count=artifact.row_count,
        column_count=artifact.column_count,
        columns=artifact.columns,
        logical_content_sha256=artifact.logical_content_sha256,
    )


@router.post(
    "/versions/{version_id}/analyses",
    response_model=ExecutionResponse,
    status_code=202,
    operation_id="createVersionAnalysis",
)
def create_analysis(
    version_id: UUID,
    body: AnalysisRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Analysis,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ExecutionResponse:
    return execution_response(
        service.submit(
            identity.user.id,
            version_id,
            body.table_artifact_id,
            body.table_sha256,
            body.analysis_kind,
            key,
            request.state.correlation_id,
            body.semantic_ref,
        )
    )


@router.get(
    "/versions/{version_id}/executions",
    response_model=list[ExecutionResponse],
    operation_id="listVersionExecutions",
)
def list_executions(
    version_id: UUID,
    identity: CurrentIdentity,
    datasets: DatasetAccess,
    executions: ExecutionAccess,
) -> list[ExecutionResponse]:
    datasets.get(identity.user.id, version_id)
    return [execution_response(run) for run in executions.for_version(identity.user.id, version_id)]


@router.get(
    "/versions/{version_id}/representations",
    response_model=list[ArtifactResponse],
    operation_id="listVersionRepresentations",
)
def representations(
    version_id: UUID,
    identity: CurrentIdentity,
    datasets: DatasetAccess,
    executions: ExecutionAccess,
) -> list[ArtifactResponse]:
    datasets.get(identity.user.id, version_id)
    return [
        artifact_response(artifact)
        for artifact in executions.representations(identity.user.id, version_id)
    ]


@router.get(
    "/executions/{execution_id}", response_model=ExecutionDetail, operation_id="getExecution"
)
def get_execution(
    execution_id: UUID, identity: CurrentIdentity, executions: ExecutionAccess
) -> ExecutionDetail:
    run = execution_response(executions.get(identity.user.id, execution_id))
    return ExecutionDetail(
        **run.model_dump(),
        attempt_history=[
            AttemptResponse.model_validate(item)
            for item in executions.attempts(identity.user.id, execution_id)
        ],
    )


@router.get(
    "/executions/{execution_id}/artifacts",
    response_model=list[ArtifactResponse],
    operation_id="listExecutionArtifacts",
)
def execution_artifacts(
    execution_id: UUID, identity: CurrentIdentity, executions: ExecutionAccess
) -> list[ArtifactResponse]:
    return [
        artifact_response(artifact)
        for artifact in executions.artifacts(identity.user.id, execution_id)
    ]


@router.get(
    "/executions/{execution_id}/quality",
    response_model=QualityReport,
    operation_id="getExecutionQuality",
)
def execution_quality(
    execution_id: UUID, identity: CurrentIdentity, service: Analysis
) -> QualityReport:
    return service.quality(identity.user.id, execution_id)


@router.get(
    "/executions/{execution_id}/profile",
    response_model=DatasetProfile,
    operation_id="getExecutionProfile",
)
def execution_profile(
    execution_id: UUID, identity: CurrentIdentity, service: Analysis
) -> DatasetProfile:
    return service.profile(identity.user.id, execution_id)


@router.post(
    "/executions/{execution_id}/cancel-analysis",
    response_model=ExecutionResponse,
    operation_id="cancelAnalysisExecution",
)
def cancel_analysis(
    execution_id: UUID, identity: CurrentIdentity, executions: ExecutionAccess
) -> ExecutionResponse:
    return execution_response(executions.cancel(identity.user.id, execution_id))
