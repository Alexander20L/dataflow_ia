"""HTTP de la exploración guiada (Fase 20), sólo lectura: nunca llama al proveedor."""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import CurrentIdentity, Explorations
from dataflow.modules.exploration.contracts import ExplorationView

router = APIRouter(prefix="/api/v1", tags=["Exploración guiada"])


@router.get(
    "/versions/{version_id}/exploration",
    response_model=ExplorationView,
    operation_id="getExploration",
)
def exploration(
    version_id: UUID, identity: CurrentIdentity, service: Explorations
) -> ExplorationView:
    """Consultas propuestas (reglas e IA), su validación, resultados exactos y relevancia."""
    return service.view(identity.user.id, version_id)
