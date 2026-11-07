"""Puerto del pipeline automático (Fase 11C) sobre los casos de uso existentes, y el gancho que
lo inicia al publicarse una importación."""

from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from dataflow.modules.analysis_sessions.public import AnalysisSessionService
from dataflow.modules.automation.application import AutomationService
from dataflow.modules.automation.infrastructure import SQLPolicyRepository
from dataflow.modules.automation.pipeline_contracts import ApprovalResult, PlanResult
from dataflow.modules.automation.pipeline_infrastructure import SQLRunRepository
from dataflow.modules.cleaning.application import CleaningProposals, CleaningService
from dataflow.modules.cleaning.contracts import derived_version_id
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanDraft
from dataflow.modules.quality.application import RulesetService
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

LIMIT_REASON = {
    "code": "AUTOMATION_LIMIT",
    "message": "Hay demasiados pipelines en curso; esta carga queda para revisión manual.",
}


def start_pipeline(db: Session, owner: UUID, project: UUID, version: UUID) -> None:
    """Dentro de la transacción que publica la importación: si el proyecto tiene una política
    activa, crea el pipeline con la revisión vigente fijada. Idempotente por versión."""
    policy = SQLPolicyRepository(db).head(owner, project)
    if policy is None or not policy.content.enabled:
        return
    runs = SQLRunRepository(db)
    if runs.exists_for_version(version):
        return
    if runs.running_count(owner) >= get_settings().automation_max_running_per_owner:
        runs.create(owner, project, version, policy.id, "needs_review", [LIMIT_REASON])
        return
    runs.create(owner, project, version, policy.id)


class PipelineAccess:
    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        proposals: CleaningProposals,
        planning: PlanningService,
        cleaning: CleaningService,
        automation: AutomationService,
        rulesets: RulesetService,
        sessions: AnalysisSessionService,
    ) -> None:
        self.datasets, self.executions = datasets, executions
        self.proposals, self.planning, self.cleaning = proposals, planning, cleaning
        self.automation, self.rulesets, self.sessions = automation, rulesets, sessions

    def table_of(self, owner: UUID, version: UUID) -> tuple[UUID, str] | None:
        try:
            binding = self.datasets.binding(owner, version)
        except ApplicationError:
            return None
        if binding.table_artifact_id is None:
            return None
        table = self.executions.artifact(owner, binding.table_artifact_id)
        return table.id, table.content.sha256

    def proposal(
        self, owner: UUID, artifact: UUID
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        proposal = self.proposals.get(owner, artifact)
        semantic = proposal.semantic_revision
        return (
            [step.model_dump(mode="json") for step in proposal.steps],
            semantic.model_dump(mode="json") if semantic else None,
        )

    def create_plan(
        self,
        owner: UUID,
        project: UUID,
        artifact: UUID,
        sha256: str,
        steps: list[dict[str, Any]],
        semantic_ref: dict[str, Any] | None,
        key: UUID,
    ) -> PlanResult:
        draft = PlanDraft.model_validate({"semantic_ref": semantic_ref, "steps": steps})
        plan = self.planning.create(owner, project, artifact, sha256, draft, key, str(key))
        return PlanResult(
            revision_id=plan.id,
            valid=plan.validation.valid,
            problems=[problem.code for problem in plan.validation.problems],
        )

    def start_preview(self, owner: UUID, plan_revision: UUID, key: UUID) -> UUID:
        return self.cleaning.preview(owner, plan_revision, key, str(key)).id

    def execution_state(self, owner: UUID, execution: UUID) -> tuple[str, str | None]:
        run = self.executions.get(owner, execution)
        return run.state, run.error_code

    def approve(
        self, owner: UUID, preview: UUID, policy_revision: UUID, run: UUID
    ) -> ApprovalResult:
        decision = self.automation.approve_preview(
            owner,
            preview,
            str(run),
            executor="pipeline",
            pipeline_run_id=run,
            expected_policy=policy_revision,
        )
        approved = decision.evaluation.decision == "approved" and decision.approval_id is not None
        return ApprovalResult(
            approved=approved,
            approval_id=decision.approval_id,
            reasons=[item.model_dump(mode="json") for item in decision.evaluation.reasons],
        )

    def start_apply(self, owner: UUID, approval: UUID) -> UUID:
        return self.cleaning.apply(owner, approval, str(approval)).id

    def derived_version(self, apply_execution: UUID) -> UUID:
        return derived_version_id(apply_execution)

    def version_state(self, owner: UUID, version: UUID) -> str | None:
        try:
            binding = self.datasets.binding(owner, version)
        except ApplicationError:
            return None
        return self.executions.get(owner, binding.execution_id).state

    def applicable_ruleset(self, owner: UUID, artifact: UUID) -> tuple[UUID, str] | None:
        context = self.rulesets.context(owner, artifact)
        for summary in [context.own, *context.others]:
            if summary is not None and summary.applicable:
                return summary.head.id, summary.head.content_sha256
        return None

    def start_rules(
        self,
        owner: UUID,
        project: UUID,
        artifact: UUID,
        sha256: str,
        ruleset: tuple[UUID, str],
        key: UUID,
    ) -> UUID:
        draft = PlanDraft.model_validate(
            {
                "steps": [
                    {
                        "id": "rules",
                        "operation": "quality.evaluate",
                        "version": 2,
                        "input": {"kind": "input", "alias": "source"},
                        "parameters": {
                            "rule_set": "csv-quality-v2",
                            "ruleset_revision_id": str(ruleset[0]),
                            "ruleset_sha256": ruleset[1],
                        },
                    }
                ]
            }
        )
        plan = self.planning.create(
            owner, project, artifact, sha256, draft, uuid5(key, "plan"), str(key)
        )
        if not plan.validation.valid:
            raise ApplicationError(
                "RULES_PLAN_INVALID", "El plan de reglas de calidad no es válido.", 409
            )
        return self.planning.execute(owner, plan.id, uuid5(key, "execution"), str(key)).id

    def evaluate_rules(self, owner: UUID, policy_revision: UUID) -> bool:
        return self.automation.revision(owner, policy_revision).content.evaluate_quality_rules

    def select_source(self, owner: UUID, project: UUID, version: UUID) -> None:
        session, _ = self.sessions.open(owner, project)
        self.sessions.select(owner, session.id, version, session.revision, str(version))

    def cancel_execution(self, owner: UUID, execution: UUID) -> None:
        self.executions.cancel(owner, execution)
