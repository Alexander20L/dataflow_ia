"""HTTP de cleaning: sólo lectura del linaje (Fase 13).

La vista previa, la aprobación y la aplicación manuales se retiraron (ADR-026): la limpieza la
decide y ejecuta el recorrido automático.
"""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import Cleaning, CurrentIdentity
from dataflow.modules.cleaning.contracts import LineageView

router = APIRouter(prefix="/api/v1", tags=["Cleaning"])


@router.get(
    "/versions/{version_id}/lineage", response_model=LineageView, operation_id="getVersionLineage"
)
def lineage(version_id: UUID, identity: CurrentIdentity, service: Cleaning) -> LineageView:
    return service.lineage(identity.user.id, version_id)
