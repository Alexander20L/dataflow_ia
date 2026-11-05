from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from dataflow.bootstrap.dependencies import CurrentIdentity, DatasetAccess, ExecutionAccess
from dataflow.modules.executions.contracts import (
    Artifact,
    ArtifactKind,
    ExecutionResponse,
    execution_response,
)

router = APIRouter(prefix="/api/v1", tags=["Executions"])


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
    kind: ArtifactKind
    object_id: UUID
    sha256: str
    byte_size: int
    row_count: int | None
    column_count: int | None
    columns: list[dict[str, Any]] | None
    logical_content_sha256: str | None


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


@router.post(
    "/executions/{execution_id}/cancel-analysis",
    response_model=ExecutionResponse,
    operation_id="cancelAnalysisExecution",
)
def cancel_analysis(
    execution_id: UUID, identity: CurrentIdentity, executions: ExecutionAccess
) -> ExecutionResponse:
    return execution_response(executions.cancel(identity.user.id, execution_id))
