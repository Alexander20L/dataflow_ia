"""HTTP de la explicación automática del dashboard (C2), sólo lectura.

El chat del copiloto, sus acciones con botón y la auditoría textual de dashboards editables se
retiraron en la Fase 13 (ADR-026). La explicación se genera sola en el worker; estos GET nunca
llaman al proveedor.
"""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import CurrentIdentity, OverviewAudits
from dataflow.modules.copilot.overview import OverviewAuditView, OverviewEvidence

router = APIRouter(prefix="/api/v1", tags=["Explicación automática"])


@router.get("/versions/{version_id}/overview-audit", operation_id="getOverviewAudit")
def overview_audit(
    version_id: UUID, identity: CurrentIdentity, service: OverviewAudits
) -> OverviewAuditView:
    return service.view(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/overview-audit/evidence/{evidence_id}",
    operation_id="getOverviewAuditEvidence",
)
def overview_evidence(
    version_id: UUID, evidence_id: str, identity: CurrentIdentity, service: OverviewAudits
) -> OverviewEvidence:
    return service.evidence(identity.user.id, version_id, evidence_id)
