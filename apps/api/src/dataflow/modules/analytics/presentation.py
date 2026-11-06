from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from dataflow.bootstrap.dependencies import CurrentIdentity, Metrics
from dataflow.modules.analytics.contracts import (
    AnalysisResult,
    AnalysisResultV2,
    AnalysisResultView,
    EvidenceView,
    MetricContext,
    MetricRevision,
    SaveMetricRequest,
    SaveMetricResponse,
)
from dataflow.modules.analytics.exports import analysis_csv
from dataflow.platform.csv_export import CsvProfile

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


@router.get(
    "/representations/{artifact_id}/metrics",
    response_model=MetricContext,
    operation_id="getMetrics",
)
def context(artifact_id: UUID, identity: CurrentIdentity, service: Metrics) -> MetricContext:
    return service.context(identity.user.id, artifact_id)


@router.post(
    "/representations/{artifact_id}/metrics",
    response_model=SaveMetricResponse,
    operation_id="saveMetric",
)
def save(
    artifact_id: UUID,
    body: SaveMetricRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Metrics,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> SaveMetricResponse:
    return service.save(
        identity.user.id,
        artifact_id,
        body.table_sha256,
        body.family_id,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.get("/metrics/{revision_id}", response_model=MetricRevision, operation_id="getMetric")
def revision(revision_id: UUID, identity: CurrentIdentity, service: Metrics) -> MetricRevision:
    return service.revision(identity.user.id, revision_id)


@router.get(
    "/executions/{execution_id}/analysis",
    response_model=AnalysisResultView,
    operation_id="getExecutionAnalysis",
)
def result(
    execution_id: UUID, identity: CurrentIdentity, service: Metrics
) -> AnalysisResult | AnalysisResultV2:
    return service.result(identity.user.id, execution_id)


@router.get(
    "/executions/{execution_id}/evidence/{evidence_id}",
    response_model=EvidenceView,
    operation_id="getEvidence",
)
def evidence(
    execution_id: UUID, evidence_id: str, identity: CurrentIdentity, service: Metrics
) -> EvidenceView:
    return service.evidence(identity.user.id, execution_id, evidence_id)


@router.get(
    "/executions/{execution_id}/analysis.csv",
    response_class=Response,
    operation_id="exportAnalysisCsv",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
def export_result(
    execution_id: UUID,
    identity: CurrentIdentity,
    service: Metrics,
    profile: Annotated[CsvProfile, Query()] = "standard",
) -> Response:
    """Resultado de análisis en CSV; cada cifra con su `evidence_id`."""
    content = analysis_csv(service.result(identity.user.id, execution_id), profile)
    suffix = "" if profile == "standard" else "-excel"
    filename = f"analisis-{str(execution_id)[:8]}{suffix}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )
