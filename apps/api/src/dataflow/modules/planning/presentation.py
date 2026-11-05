from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from pydantic import Field

from dataflow.bootstrap.dependencies import CurrentIdentity, Planning
from dataflow.modules.executions.public import ExecutionResponse, execution_response
from dataflow.modules.planning.contracts import (
    ApplicableOperation,
    InputKind,
    OperationDescriptor,
    OutputKind,
    PlanDraft,
    PlanningModel,
    PlanPage,
    PlanView,
    Requirement,
)

router = APIRouter(prefix="/api/v1", tags=["Planning"])


class OperationResponse(PlanningModel):
    name: str
    version: int
    key: str
    title: str
    input_kind: InputKind
    output_kind: OutputKind
    transforms_data: bool
    parameters_schema: dict[str, Any]
    requirements: list[Requirement]


class OperationCatalogResponse(PlanningModel):
    catalog_version: str
    operations: list[OperationResponse]


class CreatePlanRequest(PlanDraft):
    table_artifact_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RevisePlanRequest(PlanDraft):
    expected_revision: int = Field(ge=1, strict=True)


def operation_response(descriptor: OperationDescriptor) -> OperationResponse:
    return OperationResponse(
        name=descriptor.name,
        version=descriptor.version,
        key=descriptor.key,
        title=descriptor.title,
        input_kind=descriptor.input_kind,
        output_kind=descriptor.output_kind,
        transforms_data=descriptor.transforms_data,
        parameters_schema=descriptor.parameters.model_json_schema(),
        requirements=list(descriptor.requirements),
    )


@router.get("/operations", response_model=OperationCatalogResponse, operation_id="listOperations")
def operations(identity: CurrentIdentity, service: Planning) -> OperationCatalogResponse:
    return OperationCatalogResponse(
        catalog_version=service.catalog.catalog_version,
        operations=[operation_response(d) for d in service.operations()],
    )


@router.get(
    "/representations/{artifact_id}/applicable-operations",
    response_model=list[ApplicableOperation],
    operation_id="listApplicableOperations",
)
def applicable_operations(
    artifact_id: UUID,
    identity: CurrentIdentity,
    service: Planning,
    semantic_revision_id: UUID | None = None,
) -> list[ApplicableOperation]:
    return service.applicable(identity.user.id, artifact_id, semantic_revision_id)


@router.post(
    "/projects/{project_id}/plans",
    response_model=PlanView,
    status_code=201,
    operation_id="createPlan",
)
def create_plan(
    project_id: UUID,
    body: CreatePlanRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Planning,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> PlanView:
    return service.create(
        identity.user.id,
        project_id,
        body.table_artifact_id,
        body.table_sha256,
        PlanDraft(semantic_ref=body.semantic_ref, steps=body.steps),
        key,
        request.state.correlation_id,
    )


@router.post(
    "/plans/{family_id}/revisions",
    response_model=PlanView,
    status_code=201,
    operation_id="revisePlan",
)
def revise_plan(
    family_id: UUID, body: RevisePlanRequest, identity: CurrentIdentity, service: Planning
) -> PlanView:
    return service.revise(
        identity.user.id,
        family_id,
        body.expected_revision,
        PlanDraft(semantic_ref=body.semantic_ref, steps=body.steps),
    )


@router.get("/plans/{revision_id}", response_model=PlanView, operation_id="getPlan")
def get_plan(revision_id: UUID, identity: CurrentIdentity, service: Planning) -> PlanView:
    return service.get(identity.user.id, revision_id)


@router.get("/projects/{project_id}/plans", response_model=PlanPage, operation_id="listPlans")
def list_plans(
    project_id: UUID,
    identity: CurrentIdentity,
    service: Planning,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlanPage:
    return service.page(identity.user.id, project_id, limit, offset)


@router.post(
    "/plans/{revision_id}/executions",
    response_model=ExecutionResponse,
    status_code=202,
    operation_id="executePlan",
)
def execute_plan(
    revision_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Planning,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ExecutionResponse:
    return execution_response(
        service.execute(identity.user.id, revision_id, key, request.state.correlation_id)
    )
