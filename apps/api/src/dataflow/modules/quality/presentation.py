from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from dataflow.bootstrap.dependencies import CurrentIdentity, Rulesets
from dataflow.modules.quality.rules_contracts import (
    QualityRulesReport,
    RulesetContext,
    RulesetRevision,
    RulesetRevisionPage,
    SaveRulesetRequest,
    SaveRulesetResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Quality rules"])


@router.get(
    "/representations/{artifact_id}/quality-rulesets",
    response_model=RulesetContext,
    operation_id="getQualityRulesets",
)
def context(artifact_id: UUID, identity: CurrentIdentity, service: Rulesets) -> RulesetContext:
    return service.context(identity.user.id, artifact_id)


@router.post(
    "/representations/{artifact_id}/quality-rulesets",
    response_model=SaveRulesetResponse,
    operation_id="saveQualityRuleset",
)
def save(
    artifact_id: UUID,
    body: SaveRulesetRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Rulesets,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> SaveRulesetResponse:
    return service.save(
        identity.user.id,
        artifact_id,
        body.table_sha256,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.get(
    "/quality-rulesets/{revision_id}",
    response_model=RulesetRevision,
    operation_id="getQualityRulesetRevision",
)
def revision(revision_id: UUID, identity: CurrentIdentity, service: Rulesets) -> RulesetRevision:
    return service.revision(identity.user.id, revision_id)


@router.get(
    "/quality-ruleset-families/{family_id}/revisions",
    response_model=RulesetRevisionPage,
    operation_id="listQualityRulesetRevisions",
)
def history(family_id: UUID, identity: CurrentIdentity, service: Rulesets) -> RulesetRevisionPage:
    return service.history(identity.user.id, family_id)


@router.get(
    "/executions/{execution_id}/quality-rules",
    response_model=QualityRulesReport,
    operation_id="getExecutionQualityRules",
)
def report(execution_id: UUID, identity: CurrentIdentity, service: Rulesets) -> QualityRulesReport:
    return service.report(identity.user.id, execution_id)
