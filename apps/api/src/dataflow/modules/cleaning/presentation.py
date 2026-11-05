from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import Field

from dataflow.bootstrap.dependencies import Cleaning, CurrentIdentity
from dataflow.modules.cleaning.contracts import (
    ApprovalView,
    CleaningModel,
    LineageView,
    PreviewView,
)
from dataflow.modules.executions.public import ExecutionResponse, execution_response

router = APIRouter(prefix="/api/v1", tags=["Cleaning"])


class ApprovalRequest(CleaningModel):
    effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post(
    "/plans/{revision_id}/previews",
    response_model=ExecutionResponse,
    status_code=202,
    operation_id="createCleaningPreview",
)
def create_preview(
    revision_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Cleaning,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ExecutionResponse:
    return execution_response(
        service.preview(identity.user.id, revision_id, key, request.state.correlation_id)
    )


@router.get(
    "/previews/{execution_id}", response_model=PreviewView, operation_id="getCleaningPreview"
)
def get_preview(execution_id: UUID, identity: CurrentIdentity, service: Cleaning) -> PreviewView:
    return service.get_preview(identity.user.id, execution_id)


@router.post(
    "/previews/{execution_id}/approvals",
    response_model=ApprovalView,
    status_code=201,
    operation_id="approveCleaningPreview",
)
def approve(
    execution_id: UUID,
    body: ApprovalRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Cleaning,
) -> ApprovalView:
    return service.approve(
        identity.user.id, execution_id, body.effect_sha256, request.state.correlation_id
    )


@router.post(
    "/approvals/{approval_id}/revoke",
    response_model=ApprovalView,
    operation_id="revokeCleaningApproval",
)
def revoke(
    approval_id: UUID, request: Request, identity: CurrentIdentity, service: Cleaning
) -> ApprovalView:
    return service.revoke(identity.user.id, approval_id, request.state.correlation_id)


@router.post(
    "/approvals/{approval_id}/apply",
    response_model=ExecutionResponse,
    status_code=202,
    operation_id="applyCleaningApproval",
)
def apply(
    approval_id: UUID, request: Request, identity: CurrentIdentity, service: Cleaning
) -> ExecutionResponse:
    return execution_response(
        service.apply(identity.user.id, approval_id, request.state.correlation_id)
    )


@router.get(
    "/versions/{version_id}/lineage", response_model=LineageView, operation_id="getVersionLineage"
)
def lineage(version_id: UUID, identity: CurrentIdentity, service: Cleaning) -> LineageView:
    return service.lineage(identity.user.id, version_id)
