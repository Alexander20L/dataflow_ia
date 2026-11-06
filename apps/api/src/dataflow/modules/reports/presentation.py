from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from dataflow.bootstrap.dependencies import CurrentIdentity, Reports
from dataflow.modules.reports.contracts import (
    CreateReportRequest,
    PdfRender,
    RefreshReportRequest,
    RenderResponse,
    ReportRevision,
    ReportSummary,
    ReportView,
    ReviseReportRequest,
    RevisionItem,
    SaveReportResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Reports"])
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


@router.get(
    "/projects/{project_id}/reports", response_model=list[ReportSummary], operation_id="listReports"
)
def list_reports(
    project_id: UUID, identity: CurrentIdentity, service: Reports
) -> list[ReportSummary]:
    return service.summaries(identity.user.id, project_id)


@router.post(
    "/projects/{project_id}/reports",
    response_model=SaveReportResponse,
    status_code=201,
    operation_id="createReport",
)
def create_report(
    project_id: UUID,
    body: CreateReportRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Reports,
    key: IdempotencyKey,
) -> SaveReportResponse:
    return service.create(
        identity.user.id,
        project_id,
        body.version_id,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.get("/reports/{family_id}", response_model=ReportView, operation_id="getReport")
def get_report(
    family_id: UUID,
    identity: CurrentIdentity,
    service: Reports,
    revision: Annotated[UUID | None, Query()] = None,
) -> ReportView:
    """Revisión vigente (o una revisión anterior exacta) con la procedencia de cada bloque."""
    return service.view(identity.user.id, family_id, revision)


@router.get(
    "/reports/{family_id}/revisions",
    response_model=list[RevisionItem],
    operation_id="listReportRevisions",
)
def list_revisions(
    family_id: UUID, identity: CurrentIdentity, service: Reports
) -> list[RevisionItem]:
    return service.revisions(identity.user.id, family_id)


@router.post(
    "/reports/{family_id}/revisions",
    response_model=SaveReportResponse,
    operation_id="reviseReport",
)
def revise_report(
    family_id: UUID,
    body: ReviseReportRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Reports,
    key: IdempotencyKey,
) -> SaveReportResponse:
    return service.revise(
        identity.user.id,
        family_id,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.post(
    "/reports/{family_id}/refresh",
    response_model=SaveReportResponse,
    operation_id="refreshReport",
)
def refresh_report(
    family_id: UUID,
    body: RefreshReportRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Reports,
    key: IdempotencyKey,
) -> SaveReportResponse:
    return service.refresh(
        identity.user.id,
        family_id,
        body.expected_revision,
        body.version_id,
        key,
        request.state.correlation_id,
    )


@router.get(
    "/report-revisions/{revision_id}",
    response_model=ReportRevision,
    operation_id="getReportRevision",
)
def get_revision(revision_id: UUID, identity: CurrentIdentity, service: Reports) -> ReportRevision:
    return service.revision(identity.user.id, revision_id)


@router.post(
    "/report-revisions/{revision_id}/pdf",
    response_model=RenderResponse,
    status_code=202,
    operation_id="renderReportPdf",
)
def render_pdf(
    revision_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Reports,
    key: IdempotencyKey,
) -> RenderResponse:
    """Encola el PDF de esta revisión exacta en el worker."""
    return service.render(identity.user.id, revision_id, key, request.state.correlation_id)


@router.get(
    "/reports/{family_id}/pdfs", response_model=list[PdfRender], operation_id="listReportPdfs"
)
def list_pdfs(family_id: UUID, identity: CurrentIdentity, service: Reports) -> list[PdfRender]:
    return service.renders(identity.user.id, family_id)


@router.get(
    "/report-pdfs/{execution_id}",
    response_class=Response,
    operation_id="downloadReportPdf",
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
def download_pdf(execution_id: UUID, identity: CurrentIdentity, service: Reports) -> Response:
    filename, content, sha256 = service.pdf(identity.user.id, execution_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "X-Content-SHA256": sha256,
        },
    )
