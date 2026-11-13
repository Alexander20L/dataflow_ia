"""HTTP de la exploración guiada (Fase 20) y de la investigación (Fase 25).

Lectura de la investigación de una versión (la última o una del historial) y control del
usuario: pausar, cancelar, reanudar y volver a investigar. Nunca llama al proveedor: el trabajo
de fondo hace los cálculos y las llamadas a la IA.
"""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import CurrentIdentity, Explorations
from dataflow.modules.exploration.contracts import (
    ExplorationView,
    InvestigationCommand,
    InvestigationHistory,
)

router = APIRouter(prefix="/api/v1", tags=["Exploración guiada"])


@router.get(
    "/versions/{version_id}/exploration",
    response_model=ExplorationView,
    operation_id="getExploration",
)
def exploration(
    version_id: UUID,
    identity: CurrentIdentity,
    service: Explorations,
    execution_id: UUID | None = None,
) -> ExplorationView:
    """Plan, árbol, resultados exactos, evidencias y clasificación de la investigación. Con
    `execution_id`, una investigación anterior del historial."""
    return service.view(identity.user.id, version_id, execution_id)


@router.get(
    "/versions/{version_id}/exploration/history",
    response_model=InvestigationHistory,
    operation_id="getInvestigationHistory",
)
def history(
    version_id: UUID, identity: CurrentIdentity, service: Explorations
) -> InvestigationHistory:
    """Fase 25: las investigaciones de la versión, de la más reciente a la primera."""
    return service.history(identity.user.id, version_id)


@router.post(
    "/versions/{version_id}/exploration/control",
    response_model=ExplorationView,
    operation_id="controlInvestigation",
)
def control(
    version_id: UUID,
    request: InvestigationCommand,
    identity: CurrentIdentity,
    service: Explorations,
) -> ExplorationView:
    """Fase 25: pausar o cancelar la investigación en marcha (se detiene al terminar la
    investigación en curso y conserva lo calculado), reanudar la pausada o volver a investigar.
    Responde 409 si la acción no corresponde al estado."""
    return service.command(identity.user.id, version_id, request.action)
