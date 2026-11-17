"""HTTP de analytics: sólo lectura de resultados y evidencia (Fase 13, ADR-026)."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Query, Response

from dataflow.bootstrap.dependencies import CurrentIdentity, Metrics
from dataflow.modules.analytics.contracts import (
    AnalysisResultView,
    AnyAnalysisResult,
    EvidenceView,
)
from dataflow.modules.analytics.exports import analysis_csv
from dataflow.platform.csv_export import CsvProfile

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


@router.get(
    "/executions/{execution_id}/analysis",
    response_model=AnalysisResultView,
    operation_id="getExecutionAnalysis",
)
def result(execution_id: UUID, identity: CurrentIdentity, service: Metrics) -> AnyAnalysisResult:
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
