from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from dataflow.bootstrap.dependencies import Copilot, CurrentIdentity, OverviewAudits
from dataflow.modules.copilot.contracts import (
    ActionResult,
    Conversation,
    ConversationView,
    CopilotStatus,
    CreateConversationRequest,
    ExplainRequest,
    SendMessageRequest,
    TextAudit,
    TextAuditResponse,
    TurnResponse,
)
from dataflow.modules.copilot.overview import OverviewAuditView, OverviewEvidence

router = APIRouter(prefix="/api/v1", tags=["Copiloto"])
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


@router.get("/versions/{version_id}/overview-audit", operation_id="getOverviewAudit")
def overview_audit(
    version_id: UUID, identity: CurrentIdentity, service: OverviewAudits
) -> OverviewAuditView:
    return service.view(identity.user.id, version_id)


@router.get(
    "/versions/{version_id}/overview-audit/evidence/{evidence_id}",
    operation_id="getOverviewAuditEvidence",
)
def overview_evidence(
    version_id: UUID, evidence_id: str, identity: CurrentIdentity, service: OverviewAudits
) -> OverviewEvidence:
    return service.evidence(identity.user.id, version_id, evidence_id)


@router.get(
    "/projects/{project_id}/copilot/status",
    response_model=CopilotStatus,
    operation_id="getCopilotStatus",
)
def get_status(project_id: UUID, identity: CurrentIdentity, service: Copilot) -> CopilotStatus:
    return service.status(identity.user.id, project_id)


@router.get(
    "/projects/{project_id}/copilot/conversations",
    response_model=list[Conversation],
    operation_id="listCopilotConversations",
)
def list_conversations(
    project_id: UUID, identity: CurrentIdentity, service: Copilot
) -> list[Conversation]:
    return service.conversations(identity.user.id, project_id)


@router.post(
    "/projects/{project_id}/copilot/conversations",
    response_model=Conversation,
    status_code=201,
    operation_id="createCopilotConversation",
)
def create_conversation(
    project_id: UUID,
    body: CreateConversationRequest,
    identity: CurrentIdentity,
    service: Copilot,
    key: IdempotencyKey,
) -> Conversation:
    return service.create_conversation(identity.user.id, project_id, body.title, key)


@router.get(
    "/copilot/conversations/{conversation_id}",
    response_model=ConversationView,
    operation_id="getCopilotConversation",
)
def get_conversation(
    conversation_id: UUID, identity: CurrentIdentity, service: Copilot
) -> ConversationView:
    return service.view(identity.user.id, conversation_id)


@router.post(
    "/copilot/conversations/{conversation_id}/messages",
    response_model=TurnResponse,
    operation_id="sendCopilotMessage",
)
def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Copilot,
    key: IdempotencyKey,
) -> TurnResponse:
    return service.send(
        identity.user.id,
        conversation_id,
        body.version_id,
        body.text,
        key,
        request.state.correlation_id,
    )


@router.post(
    "/copilot/conversations/{conversation_id}/explanations",
    response_model=TurnResponse,
    operation_id="explainCopilotResult",
)
def explain_result(
    conversation_id: UUID,
    body: ExplainRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Copilot,
    key: IdempotencyKey,
) -> TurnResponse:
    return service.explain(
        identity.user.id, conversation_id, body.execution_id, key, request.state.correlation_id
    )


@router.post(
    "/copilot/messages/{message_id}/run-query",
    response_model=ActionResult,
    operation_id="runCopilotQuery",
)
def run_query(
    message_id: UUID, request: Request, identity: CurrentIdentity, service: Copilot
) -> ActionResult:
    return service.run_query(identity.user.id, message_id, request.state.correlation_id)


@router.post(
    "/copilot/messages/{message_id}/create-metric",
    response_model=ActionResult,
    operation_id="createCopilotMetric",
)
def create_metric(
    message_id: UUID, request: Request, identity: CurrentIdentity, service: Copilot
) -> ActionResult:
    return service.create_metric(identity.user.id, message_id, request.state.correlation_id)


@router.post(
    "/copilot/messages/{message_id}/cleaning-plan",
    response_model=ActionResult,
    operation_id="saveCopilotCleaningPlan",
)
def cleaning_plan(
    message_id: UUID, request: Request, identity: CurrentIdentity, service: Copilot
) -> ActionResult:
    return service.cleaning_plan(identity.user.id, message_id, request.state.correlation_id)


@router.post(
    "/dashboard-revisions/{revision_id}/text-audits",
    response_model=TextAuditResponse,
    operation_id="requestTextAudit",
)
def request_text_audit(
    revision_id: UUID,
    request: Request,
    identity: CurrentIdentity,
    service: Copilot,
    key: IdempotencyKey,
) -> TextAuditResponse:
    """Auditoría textual de una revisión de dashboard publicada (Fase 11F): la guardada si su
    clave de contenido ya existe (`reused`), o una nueva. No modifica el dashboard."""
    return service.text_audit(identity.user.id, revision_id, key, request.state.correlation_id)


@router.get(
    "/dashboard-revisions/{revision_id}/text-audits",
    response_model=list[TextAudit],
    operation_id="listTextAudits",
)
def list_text_audits(
    revision_id: UUID, identity: CurrentIdentity, service: Copilot
) -> list[TextAudit]:
    return service.text_audits(identity.user.id, revision_id)
