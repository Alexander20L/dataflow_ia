from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from pydantic import Field

from dataflow.bootstrap.dependencies import CurrentIdentity, Semantics
from dataflow.modules.understanding.semantic_contracts import (
    RevisionPage,
    SemanticDraft,
    SemanticModel,
    SemanticRevision,
    SemanticSaveResult,
    UnderstandingContext,
)

router = APIRouter(prefix="/api/v1", tags=["Semantic understanding"])


class SaveSemanticRequest(SemanticModel):
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0, strict=True)
    draft: SemanticDraft


@router.get(
    "/representations/{artifact_id}/understanding",
    response_model=UnderstandingContext,
    operation_id="getUnderstanding",
)
def context(
    artifact_id: UUID, identity: CurrentIdentity, service: Semantics
) -> UnderstandingContext:
    return service.context(identity.user.id, artifact_id)


@router.get(
    "/representations/{artifact_id}/semantic-contracts",
    response_model=RevisionPage,
    operation_id="listSemanticRevisions",
)
def history(
    artifact_id: UUID,
    identity: CurrentIdentity,
    service: Semantics,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RevisionPage:
    return service.page(identity.user.id, artifact_id, limit, offset)


@router.get(
    "/semantic-contracts/{revision_id}",
    response_model=SemanticRevision,
    operation_id="getSemanticRevision",
)
def revision(revision_id: UUID, identity: CurrentIdentity, service: Semantics) -> SemanticRevision:
    return service.get(identity.user.id, revision_id)


@router.post(
    "/representations/{artifact_id}/semantic-contracts",
    response_model=SemanticSaveResult,
    operation_id="saveSemanticRevision",
)
def save(
    artifact_id: UUID,
    body: SaveSemanticRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Semantics,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> SemanticSaveResult:
    return service.save(
        identity.user.id,
        artifact_id,
        body.table_sha256,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )
