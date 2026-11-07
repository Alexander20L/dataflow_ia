from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from dataflow.bootstrap.dependencies import CurrentIdentity, Templates
from dataflow.modules.templates.contracts import (
    CandidateList,
    MappingList,
    MappingRevision,
    SaveMappingRequest,
)

router = APIRouter(prefix="/api/v1", tags=["Templates"])


@router.get(
    "/representations/{artifact_id}/template-candidates",
    response_model=CandidateList,
    operation_id="getTemplateCandidates",
)
def template_candidates(
    artifact_id: UUID, identity: CurrentIdentity, service: Templates
) -> CandidateList:
    """Moldes candidatos para la tabla (nunca confirmaciones) y, si el proyecto ya tiene un
    mapeo confirmado de ese molde, si es compatible con esta tabla."""
    return service.candidates(identity.user.id, artifact_id)


@router.get(
    "/projects/{project_id}/template-mappings",
    response_model=MappingList,
    operation_id="listTemplateMappings",
)
def list_mappings(project_id: UUID, identity: CurrentIdentity, service: Templates) -> MappingList:
    return MappingList(items=service.mappings(identity.user.id, project_id))


@router.post(
    "/projects/{project_id}/template-mappings",
    response_model=MappingRevision,
    operation_id="saveTemplateMapping",
)
def save_mapping(
    project_id: UUID,
    body: SaveMappingRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Templates,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> MappingRevision:
    """Guarda la interpretación confirmada (revisión inmutable por proyecto y molde)."""
    return service.save(
        identity.user.id,
        project_id,
        body.expected_revision,
        body.content,
        key,
        request.state.correlation_id,
    )


@router.get(
    "/template-mappings/{revision_id}",
    response_model=MappingRevision,
    operation_id="getTemplateMapping",
)
def get_mapping(
    revision_id: UUID, identity: CurrentIdentity, service: Templates
) -> MappingRevision:
    return service.revision(identity.user.id, revision_id)
