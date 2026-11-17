"""HTTP de la entrega (Fase 17), sólo lectura: informe automático y progreso por etapas."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Response

from dataflow.bootstrap.dependencies import CurrentIdentity, Dashboards, Delivery
from dataflow.modules.curation.contracts import (
    DashboardCustomizationRequest,
    FindingFeedbackRequest,
)
from dataflow.modules.delivery.contracts import (
    DashboardFilterRequest,
    DashboardFilterResult,
    DashboardView,
    Progress,
    ReportHistory,
    ReportReview,
    ReportView,
    ReviewRequest,
)

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
def report_pdf(
    version_id: UUID,
    identity: CurrentIdentity,
    service: Delivery,
    execution_id: UUID | None = None,
) -> Response:
    """PDF del informe automático (sólo cuando está listo). Fase 27: `execution_id` descarga
    una versión anterior del historial."""
    content, filename = service.pdf(identity.user.id, version_id, execution_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )


@router.get(
    "/versions/{version_id}/dashboard", response_model=DashboardView, operation_id="getDashboard"
)
def dashboard(version_id: UUID, identity: CurrentIdentity, service: Dashboards) -> DashboardView:
    """Fase 21: dashboard adaptado a los datos, con las marcas «sí va / no va» aplicadas."""
    return service.view(identity.user.id, version_id)


@router.post(
    "/versions/{version_id}/dashboard/feedback",
    response_model=DashboardView,
    operation_id="judgeFinding",
)
def judge_finding(
    version_id: UUID,
    request: FindingFeedbackRequest,
    identity: CurrentIdentity,
    service: Dashboards,
) -> DashboardView:
    """Marca opcional de un elemento («keep», «drop» o «none»). No recalcula nada: reordena el
    dashboard y encola una versión nueva del informe con ese orden."""
    return service.judge(identity.user.id, version_id, request)


@router.post(
    "/versions/{version_id}/dashboard/filter",
    response_model=DashboardFilterResult,
    operation_id="filterDashboard",
)
def filter_dashboard(
    version_id: UUID,
    request: DashboardFilterRequest,
    identity: CurrentIdentity,
    service: Dashboards,
) -> DashboardFilterResult:
    """Fase 26: recalcula, con el motor exacto y sobre todas las filas que cumplen los filtros
    (meses y valores de dimensiones), los indicadores y los gráficos que dependen de ellos. No
    guarda nada ni cambia el dashboard."""
    return service.filter(identity.user.id, version_id, request)


@router.post(
    "/versions/{version_id}/dashboard/custom",
    response_model=DashboardView,
    operation_id="saveDashboardCustomization",
)
def save_dashboard_customization(
    version_id: UUID,
    request: DashboardCustomizationRequest,
    identity: CurrentIdentity,
    service: Dashboards,
) -> DashboardView:
    """Fase 26: guarda la versión personalizada del dashboard (secciones, orden, gráficos
    visibles, indicadores destacados y títulos) como una revisión nueva. La versión automática
    no cambia. 409 si la revisión esperada no es la vigente."""
    return service.customize(identity.user.id, version_id, request)


# --- Fase 27: pestaña Informe (historial, revisión humana y versiones nuevas) ---------------


@router.get(
    "/versions/{version_id}/report/history",
    response_model=ReportHistory,
    operation_id="getReportHistory",
)
def report_history(version_id: UUID, identity: CurrentIdentity, service: Delivery) -> ReportHistory:
    """Todas las versiones del informe, de la más reciente a la primera."""
    return service.history(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/report/versions/{execution_id}",
    response_model=ReportView,
    operation_id="getReportVersion",
)
def report_version(
    version_id: UUID, execution_id: UUID, identity: CurrentIdentity, service: Delivery
) -> ReportView:
    """Una versión concreta del informe, con su documento para la vista previa."""
    return service.at(identity.user.id, version_id, execution_id)[0]


@router.get(
    "/versions/{version_id}/report/review",
    response_model=ReportReview,
    operation_id="getReportReview",
)
def report_review(version_id: UUID, identity: CurrentIdentity, service: Delivery) -> ReportReview:
    """Hallazgos candidatos con su revisión (pendiente, aprobado o rechazado) y si la selección
    difiere de la del último informe."""
    return service.candidates(identity.user.id, version_id)


@router.post(
    "/versions/{version_id}/report/review",
    response_model=ReportReview,
    operation_id="reviewReportFinding",
)
def review_report_finding(
    version_id: UUID, request: ReviewRequest, identity: CurrentIdentity, service: Delivery
) -> ReportReview:
    """Aprueba, rechaza o deja pendiente un hallazgo. No genera el informe."""
    return service.review(identity.user.id, version_id, request)


@router.post(
    "/versions/{version_id}/report/versions",
    response_model=ReportView,
    operation_id="generateReportVersion",
)
def generate_report_version(
    version_id: UUID, identity: CurrentIdentity, service: Delivery
) -> ReportView:
    """Genera una versión nueva del informe con la selección vigente; la anterior se conserva.
    409 `REPORT_UP_TO_DATE` si la selección no cambió."""
    return service.generate(identity.user.id, version_id)
