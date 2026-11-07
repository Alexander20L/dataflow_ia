from uuid import UUID

from dataflow.modules.automation.contracts import (
    ApprovalOrigin,
    PolicyCleaning,
    PolicyContent,
    PolicyDecision,
    PolicyRepository,
    PolicyRevision,
)
from dataflow.modules.automation.domain import evaluate
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class AutomationService:
    """Política de automatización y aprobación por política (Fase 11B, ADR-023).

    La política no elimina la aprobación: cuando autoriza un efecto, se crea una aprobación
    normal del `effect_sha256` exacto (ADR-015), atribuida a quien guardó la política, y en la
    misma transacción el vínculo con la revisión de política y su evaluación. La aplicación
    recalcula y compara el efecto como siempre.
    """

    def __init__(
        self, repository: PolicyRepository, cleaning: PolicyCleaning, uow: UnitOfWork
    ) -> None:
        self.repository, self.cleaning, self.uow = repository, cleaning, uow

    def policy(self, owner: UUID, project: UUID) -> PolicyRevision | None:
        self.cleaning.require_project(owner, project, writable=False)
        return self.repository.head(owner, project)

    def revision(self, owner: UUID, revision: UUID) -> PolicyRevision:
        return self.repository.get(owner, revision)

    def save(
        self,
        owner: UUID,
        project: UUID,
        expected: int,
        content: PolicyContent,
        key: UUID,
        correlation: str,
    ) -> PolicyRevision:
        content_sha256 = digest("automation_policy", content.model_dump(mode="json"))
        fingerprint = digest(
            "automation_policy_request", {"expected": expected, "content": content_sha256}
        )
        try:
            self.cleaning.require_project(owner, project, writable=True)
            self.repository.lock_project(project)
            replayed = self.repository.replay(owner, project, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return replayed
            head = self.repository.head(owner, project)
            if (head.revision if head else 0) != expected:
                raise ApplicationError(
                    "AUTOMATION_POLICY_CONFLICT",
                    "La política cambió mientras tanto. Recárgala y vuelve a intentarlo.",
                    409,
                )
            if head and head.content_sha256 == content_sha256:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return head
            saved = self.repository.append(
                owner, project, content, content_sha256, key, fingerprint, correlation
            )
            pending = self.repository.pending_automatic_approvals(owner, project) if head else []
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        # Sustituir o desactivar la política revoca las aprobaciones automáticas aún no
        # aplicadas; cada revocación es su propia transacción (las aplicadas no cambian).
        for approval in pending:
            self.cleaning.revoke_if_pending(owner, approval, correlation)
        return saved

    def approve_preview(
        self,
        owner: UUID,
        execution: UUID,
        correlation: str,
        executor: str = "manual",
        pipeline_run_id: UUID | None = None,
    ) -> PolicyDecision:
        """Evalúa la vista previa con la política vigente; si la autoriza, la aprueba."""
        facts = self.cleaning.preview_facts(owner, execution)
        self.cleaning.require_project(owner, facts.project_id, writable=True)
        policy = self.repository.head(owner, facts.project_id)
        evaluation = evaluate(policy.content if policy else None, facts)
        decision = PolicyDecision(
            preview_execution_id=execution,
            effect_sha256=facts.effect_sha256,
            policy_revision_id=policy.id if policy else None,
            evaluation=evaluation,
            approval_id=None,
        )
        if evaluation.decision != "approved" or policy is None or facts.effect_sha256 is None:
            self.uow.rollback()
            return decision
        if facts.active_approval_id:
            # Ya hay una aprobación vigente del mismo efecto (humana o automática): se reutiliza.
            self.uow.rollback()
            return decision.model_copy(update={"approval_id": facts.active_approval_id})
        approval = self.cleaning.approve_with(
            owner,
            execution,
            facts.effect_sha256,
            correlation,
            lambda approval_id: self.repository.record_approval(
                approval_id,
                policy,
                execution,
                facts.effect_sha256 or "",
                evaluation,
                executor,
                pipeline_run_id,
            ),
        )
        return decision.model_copy(update={"approval_id": approval})

    def approval_origin(self, owner: UUID, approval: UUID) -> ApprovalOrigin:
        """Si la aprobación la concedió una política (y cuál), o si fue humana."""
        return self.repository.approval_origin(owner, approval)
