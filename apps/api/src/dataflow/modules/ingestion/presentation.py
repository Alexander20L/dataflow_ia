from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from dataflow.bootstrap.dependencies import Analysis, CurrentIdentity, Ingestion
from dataflow.modules.executions.contracts import ExecutionResponse, execution_response
from dataflow.modules.ingestion.contracts import Diagnostic, IngestionSummary, PreviewPage
from dataflow.modules.ingestion.domain import ImportState
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.config import get_settings
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
    "/versions/{version_id}/preview", response_model=PreviewPage, operation_id="previewVersion"
)
def preview(
    version_id: UUID,
    identity: CurrentIdentity,
    service: Ingestion,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    issue_id: Annotated[str | None, Query(max_length=100)] = None,
) -> PreviewPage:
    return service.preview(identity.user.id, version_id, limit, offset, issue_id)


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


@router.post(
    "/executions/{execution_id}/cancel", response_model=VersionResponse, operation_id="cancelImport"
)
def cancel(execution_id: UUID, identity: CurrentIdentity, service: Ingestion) -> VersionResponse:
    return VersionResponse.model_validate(service.cancel(identity.user.id, execution_id))


# Rutas de análisis de sistema: viven aquí para que executions no importe quality/understanding.
# Conservan prefijo, etiqueta y operation_id del contrato 0.5.
analysis_router = APIRouter(prefix="/api/v1", tags=["Executions"])


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table_artifact_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_kind: Literal["profile_quality", "quality_only"] = "profile_quality"
    semantic_ref: SemanticReference | None = None


@analysis_router.post(
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
