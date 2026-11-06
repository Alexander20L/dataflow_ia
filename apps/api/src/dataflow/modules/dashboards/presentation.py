from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from dataflow.bootstrap.dependencies import CurrentIdentity, Dashboards
from dataflow.modules.dashboards.contracts import (
    CreateDashboardRequest,
    DashboardRevision,
    DashboardSummary,
    DashboardView,
    RefreshDashboardRequest,
    RefreshDashboardResponse,
    ReviseDashboardRequest,
    SaveDashboardResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Dashboards"])
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


@router.get(
    "/projects/{project_id}/dashboards",
    response_model=list[DashboardSummary],
    operation_id="listDashboards",
)
def list_dashboards(
    project_id: UUID, identity: CurrentIdentity, service: Dashboards
) -> list[DashboardSummary]:
    return service.summaries(identity.user.id, project_id)


@router.post(
    "/projects/{project_id}/dashboards",
    response_model=SaveDashboardResponse,
    status_code=201,
    operation_id="createDashboard",
)
def create_dashboard(
    project_id: UUID,
    body: CreateDashboardRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Dashboards,
    key: IdempotencyKey,
) -> SaveDashboardResponse:
    return service.create(
        identity.user.id, project_id, body.draft, key, request.state.correlation_id
    )


@router.get("/dashboards/{family_id}", response_model=DashboardView, operation_id="getDashboard")
def get_dashboard(family_id: UUID, identity: CurrentIdentity, service: Dashboards) -> DashboardView:
    return service.view(identity.user.id, family_id)


@router.post(
    "/dashboards/{family_id}/revisions",
    response_model=SaveDashboardResponse,
    operation_id="reviseDashboard",
)
def revise_dashboard(
    family_id: UUID,
    body: ReviseDashboardRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Dashboards,
    key: IdempotencyKey,
) -> SaveDashboardResponse:
    return service.revise(
        identity.user.id,
        family_id,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.post(
    "/dashboards/{family_id}/refresh",
    response_model=RefreshDashboardResponse,
    operation_id="refreshDashboard",
)
def refresh_dashboard(
    family_id: UUID,
    body: RefreshDashboardRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Dashboards,
    key: IdempotencyKey,
) -> RefreshDashboardResponse:
    return service.refresh(
        identity.user.id,
        family_id,
        body.expected_revision,
        body.version_id,
        key,
        request.state.correlation_id,
    )


@router.get(
    "/dashboard-revisions/{revision_id}",
    response_model=DashboardRevision,
    operation_id="getDashboardRevision",
)
def get_revision(
    revision_id: UUID, identity: CurrentIdentity, service: Dashboards
) -> DashboardRevision:
    return service.revision(identity.user.id, revision_id)
