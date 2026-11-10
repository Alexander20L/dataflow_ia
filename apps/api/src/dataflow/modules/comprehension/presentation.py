"""HTTP de la comprensión del negocio (Fase 19): lectura y valoración opcional del usuario."""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import Comprehensions, CurrentIdentity
from dataflow.modules.comprehension.contracts import ComprehensionView, FeedbackRequest

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
    """Valoración opcional («Relevante» / «No relevante»): no bloquea ni recalcula; la
    siguiente carga del mismo archivo la tiene en cuenta. Vale la última."""
    return service.judge(identity.user.id, version_id, body)
