from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

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
