from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from dataflow.bootstrap.dependencies import Analysis, CurrentIdentity, Ingestion
from dataflow.modules.analytics.contracts import AutomaticAnalysis, AutomaticEvidence
from dataflow.modules.ingestion.contracts import (
    Diagnostic,
    IngestionSummary,
    ReadXlsxParameters,
    RecordsPage,
    SourceOrigin,
    SourceReview,
    SqlServerConnection,
    XlsxInspection,
    XlsxSelection,
)
from dataflow.modules.ingestion.domain import ImportState
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.config import get_settings
from dataflow.platform.csv_export import CsvProfile
from dataflow.platform.errors import ApplicationError

router = APIRouter(prefix="/api/v1", tags=["Datasets"])


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_id: UUID
    project_id: UUID
    number: int
    file_name: str
    sha256: str
    byte_size: int
    created_at: datetime
    execution_id: UUID
    state: ImportState
    row_count: int | None
    column_count: int | None
    error_code: str | None
    error_message: str | None
    attempts: int
    kind: Literal["imported", "derived"]
    parent_version_id: UUID | None
    source_selection: XlsxSelection | None = None
    source_origin: SourceOrigin | None = None


class VersionPage(BaseModel):
    items: list[VersionResponse]
    total: int
    limit: int
    offset: int


@router.get(
    "/datasets/summary", response_model=IngestionSummary, operation_id="getIngestionSummary"
)
def summary(identity: CurrentIdentity, service: Ingestion) -> IngestionSummary:
    return service.summary(identity.user.id)


@router.post(
    "/projects/{project_id}/imports",
    status_code=202,
    response_model=VersionResponse,
    operation_id="uploadCsv",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_csv(
    project_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Ingestion,
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    request_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    separator: Literal["auto", ",", ";", "tab"] = "auto",
) -> VersionResponse:
    if request.headers.get("content-type", "").split(";")[0].strip() != "text/csv":
        raise ApplicationError(
            "CSV_CONTENT_TYPE", "Envía el contenido CSV con Content-Type text/csv.", 415
        )
    maximum = get_settings().max_upload_bytes
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise ApplicationError("FILE_TOO_LARGE", "El CSV supera el límite de 5 MB.", 413)
        chunks.append(chunk)
    version = await run_in_threadpool(
        service.submit,
        identity.user.id,
        project_id,
        file_name,
        b"".join(chunks),
        separator,
        request_key,
        request.state.correlation_id,
    )
    return VersionResponse.model_validate(version)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_BODY = {
    "requestBody": {
        "required": True,
        "content": {XLSX_MIME: {"schema": {"type": "string", "format": "binary"}}},
    }
}


PDF_MIME = "application/pdf"
PDF_BODY = {
    "requestBody": {
        "required": True,
        "content": {PDF_MIME: {"schema": {"type": "string", "format": "binary"}}},
    }
}


async def xlsx_body(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";")[0].strip() != XLSX_MIME:
        raise ApplicationError(
            "XLSX_CONTENT_TYPE", f"Envía el libro con Content-Type {XLSX_MIME}.", 415
        )
    return await limited_body(request)


async def limited_body(request: Request) -> bytes:
    maximum = get_settings().max_upload_bytes
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise ApplicationError("FILE_TOO_LARGE", "El libro supera el límite de 5 MB.", 413)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/projects/{project_id}/imports/xlsx/inspect",
    response_model=XlsxInspection,
    operation_id="inspectXlsx",
    openapi_extra=XLSX_BODY,
)
async def inspect_xlsx(
    project_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Ingestion,
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    sheet: Annotated[str | None, Query(min_length=1, max_length=31)] = None,
    table: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    header_row: Annotated[int, Query(ge=1, le=1_048_576)] = 1,
) -> XlsxInspection:
    """Hojas, tablas con nombre y vista previa; no guarda nada. Sin `sheet` ni `table`
    muestra la elección automática del sistema (`selection`, Fase 13B)."""
    content = await xlsx_body(request)
    return await run_in_threadpool(
        service.inspect_xlsx,
        identity.user.id,
        project_id,
        file_name,
        content,
        sheet,
        table,
        header_row,
    )


@router.post(
    "/projects/{project_id}/imports/xlsx",
    status_code=202,
    response_model=VersionResponse,
    operation_id="uploadXlsx",
    openapi_extra=XLSX_BODY,
)
async def upload_xlsx(
    project_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Ingestion,
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    request_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    sheet: Annotated[str | None, Query(min_length=1, max_length=31)] = None,
    table: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    header_row: Annotated[int, Query(ge=1, le=1_048_576)] = 1,
) -> VersionResponse:
    """Importa un libro con ingestion.read_xlsx@1. Sin `sheet` ni `table` (Fase 13B), el
    sistema elige la hoja o tabla y la cabecera (`xlsx-selection-v1`) y lo informa en
    `source_selection`; con `table` hay que indicar también su `sheet`."""
    if sheet is None and table is not None:
        raise ApplicationError(
            "XLSX_SHEET_REQUIRED", "Indica la hoja de la tabla o deja que el sistema elija.", 422
        )
    content = await xlsx_body(request)
    version = await run_in_threadpool(
        service.submit_xlsx,
        identity.user.id,
        project_id,
        file_name,
        content,
        ReadXlsxParameters(sheet=sheet, table=table, header_row=header_row) if sheet else None,
        request_key,
        request.state.correlation_id,
    )
    return VersionResponse.model_validate(version)


@router.post(
    "/projects/{project_id}/imports/pdf",
    status_code=202,
    response_model=VersionResponse,
    operation_id="uploadPdf",
    openapi_extra=PDF_BODY,
)
async def upload_pdf(
    project_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Ingestion,
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
    request_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> VersionResponse:
    """Fase 18B: importa las tablas de un PDF con texto (`pdf-selection-v1`). Devuelve la
    versión de la tabla principal; las demás tablas se registran como versiones propias y se
    indican en `source_origin`. PDF escaneado: 422 `PDF_NO_TEXT`; sin tablas: `PDF_NO_TABLES`."""
    if request.headers.get("content-type", "").split(";")[0].strip() != PDF_MIME:
        raise ApplicationError(
            "PDF_CONTENT_TYPE", f"Envía el PDF con Content-Type {PDF_MIME}.", 415
        )
    content = await limited_body(request)
    version = await run_in_threadpool(
        service.submit_pdf,
        identity.user.id,
        project_id,
        file_name,
        content,
        request_key,
        request.state.correlation_id,
    )
    return VersionResponse.model_validate(version)


@router.post(
    "/projects/{project_id}/imports/sqlserver",
    status_code=202,
    response_model=VersionResponse,
    operation_id="importSqlServer",
)
async def import_sqlserver(
    project_id: UUID,
    body: SqlServerConnection,
    request: Request,
    identity: CurrentIdentity,
    service: Ingestion,
    request_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> VersionResponse:
    """Fase 18B: copia de un solo uso de las tablas de una base de SQL Server
    (`sqlserver-selection-v1`); cada tabla es una versión con su CSV original. La contraseña se
    usa para la copia y se descarta. Sólo servidores de `DATAFLOW_SQLSERVER_ALLOWED_HOSTS`."""
    version = await run_in_threadpool(
        service.submit_sqlserver,
        identity.user.id,
        project_id,
        body,
        get_settings().sqlserver_allowed_hosts,
        request_key,
        request.state.correlation_id,
    )
    return VersionResponse.model_validate(version)


@router.get(
    "/projects/{project_id}/versions", response_model=VersionPage, operation_id="listVersions"
)
def list_versions(
    project_id: UUID,
    identity: CurrentIdentity,
    service: Ingestion,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VersionPage:
    items, total = service.versions(identity.user.id, project_id, limit, offset)
    return VersionPage(
        items=[VersionResponse.model_validate(v) for v in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/versions/{version_id}", response_model=VersionResponse, operation_id="getVersion")
def get_version(version_id: UUID, identity: CurrentIdentity, service: Ingestion) -> VersionResponse:
    return VersionResponse.model_validate(service.version(identity.user.id, version_id))


@router.get(
    "/versions/{version_id}/diagnostic", response_model=Diagnostic, operation_id="getDiagnostic"
)
def diagnostic(version_id: UUID, identity: CurrentIdentity, service: Ingestion) -> Diagnostic:
    return service.diagnostic(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/reading", response_model=SourceReview, operation_id="getSourceReview"
)
def source_review(version_id: UUID, identity: CurrentIdentity, service: Ingestion) -> SourceReview:
    """Cómo se leyó el archivo (codificación, separador, valores regionales) y qué columnas
    cambiaron respecto de la versión anterior del mismo archivo (Fase 18). Sólo lectura."""
    return service.review(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/automatic-analysis",
    response_model=AutomaticAnalysis,
    operation_id="getAutomaticAnalysis",
)
def automatic_analysis(
    version_id: UUID, identity: CurrentIdentity, service: Ingestion
) -> AutomaticAnalysis:
    """Plan analítico automático y hallazgos con evidencia, guardados al importar."""
    return service.automatic_analysis(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/automatic-analysis/evidence/{evidence_id}",
    response_model=AutomaticEvidence,
    operation_id="getAutomaticEvidence",
)
def automatic_evidence(
    version_id: UUID,
    evidence_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    identity: CurrentIdentity,
    service: Ingestion,
) -> AutomaticEvidence:
    """Procedencia exacta de una cifra del análisis automático (método y entradas)."""
    return service.automatic_evidence(identity.user.id, version_id, evidence_id)


@router.get(
    "/versions/{version_id}/preview", response_model=RecordsPage, operation_id="previewVersion"
)
def preview(
    version_id: UUID,
    identity: CurrentIdentity,
    service: Ingestion,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    issue_id: Annotated[str | None, Query(max_length=100)] = None,
    sort: Annotated[UUID | None, Query()] = None,
    descending: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> RecordsPage:
    """Registros tal como se leyeron, paginados en el servidor. `sort` es el identificador de
    una columna; `search` busca el texto literal (sin distinguir mayúsculas) en todas."""
    return service.preview(
        identity.user.id, version_id, limit, offset, issue_id, sort, descending, search
    )


@router.get(
    "/versions/{version_id}/original",
    response_class=Response,
    operation_id="downloadOriginal",
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
def original(version_id: UUID, identity: CurrentIdentity, service: Ingestion) -> Response:
    filename, content = service.original(identity.user.id, version_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )


CSV_RESPONSE = {200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}}


@router.get(
    "/versions/{version_id}/export.csv",
    response_class=Response,
    operation_id="exportVersionCsv",
    responses=CSV_RESPONSE,  # type: ignore[arg-type]
)
def export_version(
    version_id: UUID,
    identity: CurrentIdentity,
    service: Ingestion,
    profile: Annotated[CsvProfile, Query()] = "standard",
) -> Response:
    """Tabla de la versión (también derivada) en el perfil `standard` o `excel_regional`."""
    filename, content = service.export_csv(identity.user.id, version_id, profile)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )


@router.post(
    "/executions/{execution_id}/cancel", response_model=VersionResponse, operation_id="cancelImport"
)
def cancel(execution_id: UUID, identity: CurrentIdentity, service: Ingestion) -> VersionResponse:
    return VersionResponse.model_validate(service.cancel(identity.user.id, execution_id))


# Rutas de análisis de sistema: viven aquí para que executions no importe quality/understanding.
# Conservan prefijo, etiqueta y operation_id del contrato 0.5.
analysis_router = APIRouter(prefix="/api/v1", tags=["Executions"])


@analysis_router.get(
    "/executions/{execution_id}/quality",
    response_model=QualityReport,
    operation_id="getExecutionQuality",
)
def execution_quality(
    execution_id: UUID, identity: CurrentIdentity, service: Analysis
) -> QualityReport:
    return service.quality(identity.user.id, execution_id)


@analysis_router.get(
    "/executions/{execution_id}/profile",
    response_model=DatasetProfile,
    operation_id="getExecutionProfile",
)
def execution_profile(
    execution_id: UUID, identity: CurrentIdentity, service: Analysis
) -> DatasetProfile:
    return service.profile(identity.user.id, execution_id)
