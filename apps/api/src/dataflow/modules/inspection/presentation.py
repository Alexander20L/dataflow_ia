"""HTTP de la pestaña Dataset (Fase 22): inspección de la versión y diccionario editable."""

from uuid import UUID

from fastapi import APIRouter

from dataflow.bootstrap.dependencies import CurrentIdentity, Inspections
from dataflow.modules.inspection.contracts import AnnotationRequest, InspectionView

router = APIRouter(prefix="/api/v1", tags=["Dataset"])


@router.get(
    "/versions/{version_id}/inspection",
    response_model=InspectionView,
    operation_id="getInspection",
)
def inspection(version_id: UUID, identity: CurrentIdentity, service: Inspections) -> InspectionView:
    """Resumen, perfil de cada columna, diagnóstico de calidad y lectura del archivo, calculados
    una vez sobre la tabla completa, y el diccionario vigente (con tus correcciones). Mientras
    se calcula devuelve el estado («queued» o «running»); las versiones anteriores a esta fase
    devuelven «unavailable»."""
    return service.view(identity.user.id, version_id)


@router.post(
    "/versions/{version_id}/dictionary",
    response_model=InspectionView,
    operation_id="annotateColumn",
)
def annotate(
    version_id: UUID, body: AnnotationRequest, identity: CurrentIdentity, service: Inspections
) -> InspectionView:
    """Corrección manual de una columna (rol, naturaleza, interpretación temporal, observación
    o confirmación). Se guarda como metadato: no cambia el archivo ni ningún cálculo, y las
    versiones siguientes del mismo archivo la heredan. Vale la última."""
    return service.annotate(identity.user.id, version_id, body)
