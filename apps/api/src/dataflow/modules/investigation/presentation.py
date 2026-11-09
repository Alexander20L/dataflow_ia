"""HTTP de la investigación automática (Fase 16), sólo lectura: nunca llama al proveedor."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path

from dataflow.bootstrap.dependencies import CurrentIdentity, Investigations
from dataflow.modules.analytics.contracts import AutomaticEvidence
from dataflow.modules.investigation.contracts import InvestigationView

router = APIRouter(prefix="/api/v1", tags=["Investigación automática"])


@router.get(
    "/versions/{version_id}/investigation",
    response_model=InvestigationView,
    operation_id="getInvestigation",
)
def investigation(
    version_id: UUID, identity: CurrentIdentity, service: Investigations
) -> InvestigationView:
    """Seguimientos por reglas y propuestas de la IA validadas, con su explicación."""
    return service.view(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/investigation/evidence/{evidence_id}",
    response_model=AutomaticEvidence,
    operation_id="getInvestigationEvidence",
)
def investigation_evidence(
    version_id: UUID,
    evidence_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    identity: CurrentIdentity,
    service: Investigations,
) -> AutomaticEvidence:
    """Procedencia de una cifra de la investigación o de los hallazgos que explica."""
    return service.evidence(identity.user.id, version_id, evidence_id)
