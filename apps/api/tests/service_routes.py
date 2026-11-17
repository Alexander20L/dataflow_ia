"""Rutas HTTP **sólo de pruebas** sobre los servicios que conserva la Fase 13.

La Fase 13 (ADR-026) retiró del contrato las rutas manuales (planes, semántica, vista previa y
aprobación de limpieza, reglas de calidad, métricas, análisis a petición). Sus servicios y motores
se conservan porque el recorrido automático los usa, y sus pruebas siguen ejercitándolos con la
misma forma de petición que antes. `conftest.py` monta este router sólo en la aplicación de
pruebas: nunca forma parte de la API ni de OpenAPI.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from dataflow.bootstrap.dependencies import (
    Analysis,
    Cleaning,
    CurrentIdentity,
    Db,
    ExecutionAccess,
    Metrics,
    Objects,
)
from dataflow.bootstrap.services import (
    make_cleaning_proposals,
    make_planning,
    make_rulesets,
    make_semantics,
)
from dataflow.modules.analytics.contracts import (
    MetricContext,
    MetricRevision,
    SaveMetricRequest,
    SaveMetricResponse,
)
from dataflow.modules.cleaning.application import CleaningProposals
from dataflow.modules.cleaning.contracts import ApprovalView, CleaningModel, PreviewView
from dataflow.modules.cleaning.proposal import CleaningProposal
from dataflow.modules.executions.public import ExecutionResponse, execution_response
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import (
    ApplicableOperation,
    PlanDraft,
    PlanPage,
    PlanView,
)
from dataflow.modules.quality.application import RulesetService
from dataflow.modules.quality.rules_contracts import (
    QualityRulesReport,
    RulesetContext,
    RulesetRevision,
    RulesetRevisionPage,
    SaveRulesetRequest,
    SaveRulesetResponse,
)
from dataflow.modules.understanding.public import SemanticService
from dataflow.modules.understanding.semantic_contracts import (
    RevisionPage,
    SemanticDraft,
    SemanticModel,
    SemanticReference,
    SemanticRevision,
    SemanticSaveResult,
    UnderstandingContext,
)

router = APIRouter(prefix="/api/v1")
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def planning_service(db: Db, objects: Objects) -> PlanningService:
    return make_planning(db, objects)


def semantic_service(db: Db, objects: Objects) -> SemanticService:
    return make_semantics(db, objects)


def ruleset_service(db: Db, objects: Objects) -> RulesetService:
    return make_rulesets(db, objects)


def proposal_service(db: Db, objects: Objects) -> CleaningProposals:
    return make_cleaning_proposals(db, objects)


Planning = Annotated[PlanningService, Depends(planning_service)]
Semantics = Annotated[SemanticService, Depends(semantic_service)]
Rulesets = Annotated[RulesetService, Depends(ruleset_service)]
Proposals = Annotated[CleaningProposals, Depends(proposal_service)]


# --- Planes --------------------------------------------------------------------------------


class CreatePlanRequest(PlanDraft):
    table_artifact_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RevisePlanRequest(PlanDraft):
    expected_revision: int = Field(ge=1, strict=True)


@router.get("/operations")
def operations(identity: CurrentIdentity, service: Planning) -> dict[str, Any]:
    return {
        "catalog_version": service.catalog.catalog_version,
        "operations": [
            {
                "name": d.name,
                "version": d.version,
                "key": d.key,
                "title": d.title,
                "input_kind": d.input_kind,
                "output_kind": d.output_kind,
                "transforms_data": d.transforms_data,
                "parameters_schema": d.parameters.model_json_schema(),
                "requirements": [r.model_dump(mode="json") for r in d.requirements],
            }
            for d in service.operations()
        ],
    }


@router.get("/representations/{artifact_id}/applicable-operations")
def applicable_operations(
    artifact_id: UUID,
    identity: CurrentIdentity,
    service: Planning,
    semantic_revision_id: UUID | None = None,
) -> list[ApplicableOperation]:
    return service.applicable(identity.user.id, artifact_id, semantic_revision_id)


@router.post("/projects/{project_id}/plans", status_code=201)
def create_plan(
    project_id: UUID,
    body: CreatePlanRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Planning,
    key: Key,
) -> PlanView:
    return service.create(
        identity.user.id,
        project_id,
        body.table_artifact_id,
        body.table_sha256,
        PlanDraft(semantic_ref=body.semantic_ref, steps=body.steps),
        key,
        request.state.correlation_id,
    )


@router.post("/plans/{family_id}/revisions", status_code=201)
def revise_plan(
    family_id: UUID, body: RevisePlanRequest, identity: CurrentIdentity, service: Planning
) -> PlanView:
    return service.revise(
        identity.user.id,
        family_id,
        body.expected_revision,
        PlanDraft(semantic_ref=body.semantic_ref, steps=body.steps),
    )


@router.get("/plans/{revision_id}")
def get_plan(revision_id: UUID, identity: CurrentIdentity, service: Planning) -> PlanView:
    return service.get(identity.user.id, revision_id)


@router.get("/projects/{project_id}/plans")
def list_plans(
    project_id: UUID,
    identity: CurrentIdentity,
    service: Planning,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlanPage:
    return service.page(identity.user.id, project_id, limit, offset)


@router.post("/plans/{revision_id}/executions", status_code=202)
def execute_plan(
    revision_id: UUID, request: Request, identity: CurrentIdentity, service: Planning, key: Key
) -> ExecutionResponse:
    return execution_response(
        service.execute(identity.user.id, revision_id, key, request.state.correlation_id)
    )


# --- Semántica -----------------------------------------------------------------------------


class SaveSemanticRequest(SemanticModel):
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0, strict=True)
    draft: SemanticDraft


@router.get("/representations/{artifact_id}/understanding")
def understanding(
    artifact_id: UUID, identity: CurrentIdentity, service: Semantics
) -> UnderstandingContext:
    return service.context(identity.user.id, artifact_id)


@router.get("/representations/{artifact_id}/semantic-contracts")
def semantic_history(
    artifact_id: UUID,
    identity: CurrentIdentity,
    service: Semantics,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RevisionPage:
    return service.page(identity.user.id, artifact_id, limit, offset)


@router.get("/semantic-contracts/{revision_id}")
def semantic_revision(
    revision_id: UUID, identity: CurrentIdentity, service: Semantics
) -> SemanticRevision:
    return service.get(identity.user.id, revision_id)


@router.post("/representations/{artifact_id}/semantic-contracts")
def save_semantics(
    artifact_id: UUID,
    body: SaveSemanticRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Semantics,
    key: Key,
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


# --- Limpieza ------------------------------------------------------------------------------


class ApprovalRequest(CleaningModel):
    effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/plans/{revision_id}/previews", status_code=202)
def create_preview(
    revision_id: UUID, request: Request, identity: CurrentIdentity, service: Cleaning, key: Key
) -> ExecutionResponse:
    return execution_response(
        service.preview(identity.user.id, revision_id, key, request.state.correlation_id)
    )


@router.get("/previews/{execution_id}")
def get_preview(execution_id: UUID, identity: CurrentIdentity, service: Cleaning) -> PreviewView:
    return service.get_preview(identity.user.id, execution_id)


@router.post("/previews/{execution_id}/approvals", status_code=201)
def approve(
    execution_id: UUID,
    body: ApprovalRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Cleaning,
) -> ApprovalView:
    return service.approve(
        identity.user.id, execution_id, body.effect_sha256, request.state.correlation_id
    )


@router.post("/approvals/{approval_id}/revoke")
def revoke(
    approval_id: UUID, request: Request, identity: CurrentIdentity, service: Cleaning
) -> ApprovalView:
    return service.revoke(identity.user.id, approval_id, request.state.correlation_id)


@router.post("/approvals/{approval_id}/apply", status_code=202)
def apply(
    approval_id: UUID, request: Request, identity: CurrentIdentity, service: Cleaning
) -> ExecutionResponse:
    return execution_response(
        service.apply(identity.user.id, approval_id, request.state.correlation_id)
    )


@router.get("/representations/{artifact_id}/cleaning-proposal")
def cleaning_proposal(
    artifact_id: UUID, identity: CurrentIdentity, service: Proposals
) -> CleaningProposal:
    return service.get(identity.user.id, artifact_id)


# --- Reglas de calidad ---------------------------------------------------------------------


@router.get("/representations/{artifact_id}/quality-rulesets")
def rulesets(artifact_id: UUID, identity: CurrentIdentity, service: Rulesets) -> RulesetContext:
    return service.context(identity.user.id, artifact_id)


@router.post("/representations/{artifact_id}/quality-rulesets")
def save_ruleset(
    artifact_id: UUID,
    body: SaveRulesetRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Rulesets,
    key: Key,
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


@router.get("/quality-rulesets/{revision_id}")
def ruleset(revision_id: UUID, identity: CurrentIdentity, service: Rulesets) -> RulesetRevision:
    return service.revision(identity.user.id, revision_id)


@router.get("/quality-ruleset-families/{family_id}/revisions")
def ruleset_history(
    family_id: UUID, identity: CurrentIdentity, service: Rulesets
) -> RulesetRevisionPage:
    return service.history(identity.user.id, family_id)


@router.get("/executions/{execution_id}/quality-rules")
def rules_report(
    execution_id: UUID, identity: CurrentIdentity, service: Rulesets
) -> QualityRulesReport:
    return service.report(identity.user.id, execution_id)


# --- Métricas ------------------------------------------------------------------------------


@router.get("/representations/{artifact_id}/metrics")
def metrics(artifact_id: UUID, identity: CurrentIdentity, service: Metrics) -> MetricContext:
    return service.context(identity.user.id, artifact_id)


@router.post("/representations/{artifact_id}/metrics")
def save_metric(
    artifact_id: UUID,
    body: SaveMetricRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Metrics,
    key: Key,
) -> SaveMetricResponse:
    return service.save(
        identity.user.id,
        artifact_id,
        body.table_sha256,
        body.family_id,
        body.expected_revision,
        body.draft,
        key,
        request.state.correlation_id,
    )


@router.get("/metrics/{revision_id}")
def metric(revision_id: UUID, identity: CurrentIdentity, service: Metrics) -> MetricRevision:
    return service.revision(identity.user.id, revision_id)


# --- Análisis de una tabla a petición --------------------------------------------------------


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table_artifact_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_kind: Literal["profile_quality", "quality_only"] = "profile_quality"
    semantic_ref: SemanticReference | None = None


@router.post("/versions/{version_id}/analyses", status_code=202)
def create_analysis(
    version_id: UUID,
    body: AnalysisRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Analysis,
    key: Key,
) -> ExecutionResponse:
    return execution_response(
        service.submit(
            identity.user.id,
            version_id,
            body.table_artifact_id,
            body.table_sha256,
            body.analysis_kind,
            key,
            request.state.correlation_id,
            body.semantic_ref,
        )
    )


@router.post("/executions/{execution_id}/cancel-analysis")
def cancel_analysis(
    execution_id: UUID, identity: CurrentIdentity, executions: ExecutionAccess
) -> ExecutionResponse:
    return execution_response(executions.cancel(identity.user.id, execution_id))
