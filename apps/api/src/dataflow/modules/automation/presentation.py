from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from dataflow.bootstrap.dependencies import Automation, CurrentIdentity
from dataflow.modules.automation.contracts import (
    ApprovalOrigin,
    AutomationModel,
    PolicyDecision,
    PolicyRevision,
    SavePolicyRequest,
)

router = APIRouter(prefix="/api/v1", tags=["Automation"])


class PolicyHead(AutomationModel):
    """Política vigente del proyecto; `revision` es None si todavía no se guardó ninguna."""

    revision: PolicyRevision | None


@router.get(
    "/projects/{project_id}/automation-policy",
    response_model=PolicyHead,
    operation_id="getAutomationPolicy",
)
def get_policy(project_id: UUID, identity: CurrentIdentity, service: Automation) -> PolicyHead:
    return PolicyHead(revision=service.policy(identity.user.id, project_id))


@router.post(
    "/projects/{project_id}/automation-policy",
    response_model=PolicyRevision,
    operation_id="saveAutomationPolicy",
)
def save_policy(
    project_id: UUID,
    body: SavePolicyRequest,
    request: Request,
    identity: CurrentIdentity,
    service: Automation,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> PolicyRevision:
    """Nueva revisión inmutable (`expected_revision`); sin cambios no crea revisión."""
    return service.save(
        identity.user.id,
        project_id,
        body.expected_revision,
        body.content,
        key,
        request.state.correlation_id,
    )


@router.get(
    "/automation-policies/{revision_id}",
    response_model=PolicyRevision,
    operation_id="getAutomationPolicyRevision",
)
def get_revision(
    revision_id: UUID, identity: CurrentIdentity, service: Automation
) -> PolicyRevision:
    return service.revision(identity.user.id, revision_id)


@router.post(
    "/previews/{execution_id}/policy-approvals",
    response_model=PolicyDecision,
    operation_id="approvePreviewByPolicy",
)
def approve_by_policy(
    execution_id: UUID, request: Request, identity: CurrentIdentity, service: Automation
) -> PolicyDecision:
    """Evalúa la vista previa con la política vigente. Si la autoriza, crea la aprobación del
    efecto exacto; si no, devuelve los motivos y no cambia nada (la persona puede aprobarla)."""
    return service.approve_preview(identity.user.id, execution_id, request.state.correlation_id)


@router.get(
    "/approvals/{approval_id}/origin",
    response_model=ApprovalOrigin,
    operation_id="getApprovalOrigin",
)
def approval_origin(
    approval_id: UUID, identity: CurrentIdentity, service: Automation
) -> ApprovalOrigin:
    """Si una aprobación de limpieza la concedió una política (revisión y evaluación)."""
    return service.approval_origin(identity.user.id, approval_id)
