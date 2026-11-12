"""HTTP de la comprensión del negocio (Fase 19): lectura y valoración opcional del usuario."""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import Comprehensions, CurrentIdentity
from dataflow.modules.comprehension.contracts import (
    ComprehensionView,
    FeedbackRequest,
    MeaningRequest,
)

router = APIRouter(prefix="/api/v1", tags=["Comprensión del negocio"])


@router.get(
    "/versions/{version_id}/comprehension",
    response_model=ComprehensionView,
    operation_id="getComprehension",
)
def comprehension(
    version_id: UUID, identity: CurrentIdentity, service: Comprehensions
) -> ComprehensionView:
    """Escalas de medida, asociaciones, hipótesis de la IA y relaciones con su evidencia."""
    return service.view(identity.user.id, version_id)


@router.post(
    "/versions/{version_id}/comprehension/feedback",
    response_model=ComprehensionView,
    operation_id="judgeRelationship",
)
def judge(
    version_id: UUID, body: FeedbackRequest, identity: CurrentIdentity, service: Comprehensions
) -> ComprehensionView:
    """Valoración opcional (validar o rechazar una relación): no bloquea. Desde la Fase 24
    cuenta ya: se rehacen la exploración, el dashboard y el informe; la siguiente carga del mismo
    archivo también la tiene en cuenta. Vale la última."""
    return service.judge(identity.user.id, version_id, body)


@router.post(
    "/versions/{version_id}/comprehension/meanings",
    response_model=ComprehensionView,
    operation_id="describeColumn",
)
def describe(
    version_id: UUID, body: MeaningRequest, identity: CurrentIdentity, service: Comprehensions
) -> ComprehensionView:
    """Fase 24: significado de una columna escrito o confirmado por el usuario. Lo heredan las
    versiones siguientes del mismo archivo y no cambia ningún cálculo. Sin texto y sin confirmar
    vuelve al de la IA."""
    return service.describe(identity.user.id, version_id, body)
