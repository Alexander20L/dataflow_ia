"""HTTP de la entrega (Fase 17), sólo lectura: informe automático y progreso por etapas."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Response

from dataflow.bootstrap.dependencies import CurrentIdentity, Delivery
from dataflow.modules.delivery.contracts import Progress, ReportView

router = APIRouter(prefix="/api/v1", tags=["Entrega"])


@router.get(
    "/versions/{version_id}/progress", response_model=Progress, operation_id="getVersionProgress"
)
def version_progress(version_id: UUID, identity: CurrentIdentity, service: Delivery) -> Progress:
    """Etapas de la carga (análisis, investigación e informe) con su estado."""
    return service.progress(identity.user.id, version_id)


@router.get("/versions/{version_id}/report", response_model=ReportView, operation_id="getReport")
def report(version_id: UUID, identity: CurrentIdentity, service: Delivery) -> ReportView:
    """Estado del informe automático de la versión."""
    return service.report(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/report.pdf",
    operation_id="downloadReport",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def report_pdf(version_id: UUID, identity: CurrentIdentity, service: Delivery) -> Response:
    """PDF del informe automático (sólo cuando está listo)."""
    content, filename = service.pdf(identity.user.id, version_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )
