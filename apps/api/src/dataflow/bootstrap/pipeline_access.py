"""Puerto del pipeline automático (Fase 11C) sobre los casos de uso existentes, y el gancho que
lo inicia al publicarse una importación."""

from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from dataflow.bootstrap.templates_access import TemplateTablesAccess
from dataflow.modules.analysis_sessions.public import AnalysisSessionService
from dataflow.modules.analytics.application import MetricService
from dataflow.modules.analytics.contracts import MetricDraft
from dataflow.modules.automation.application import AutomationService
from dataflow.modules.automation.infrastructure import SQLPolicyRepository
from dataflow.modules.automation.pipeline_contracts import ApprovalResult, MatchResult, PlanResult
from dataflow.modules.automation.pipeline_infrastructure import SQLRunRepository
from dataflow.modules.cleaning.application import CleaningProposals, CleaningService
from dataflow.modules.cleaning.contracts import derived_version_id
from dataflow.modules.cleaning.proposal import CastProposal
from dataflow.modules.dashboards.application import DashboardService
from dataflow.modules.dashboards.contracts import DashboardDraft
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanDraft
from dataflow.modules.quality.application import RulesetService
from dataflow.modules.templates.analysis import ANALYSIS_VERSION, analysis_spec, resolve
from dataflow.modules.templates.application import TemplateService
from dataflow.modules.understanding.public import SemanticService
from dataflow.modules.understanding.semantic_contracts import SemanticDraft
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

LIMIT_REASON = {
    "code": "AUTOMATION_LIMIT",
    "message": "Hay demasiados pipelines en curso; esta carga queda para revisión manual.",
}


def automation_available(db: Session) -> bool:
    """Con un esquema anterior a la Fase 11C (p. ej. durante una migración o su prueba) no hay
    tablas de automatización: no se inicia nada. `to_regclass` no falla ni aborta la
    transacción de publicación si la tabla no existe."""
    return bool(
        db.scalar(
            text(
                "SELECT to_regclass('automation_policy_families') IS NOT NULL"
                " AND to_regclass('automation_runs') IS NOT NULL"
            )
        )
    )


def start_pipeline(db: Session, owner: UUID, project: UUID, version: UUID) -> None:
    """Dentro de la transacción que publica la importación: si el proyecto tiene una política
    activa, crea el pipeline con la revisión vigente fijada. Idempotente por versión."""
    if not automation_available(db):
        return
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
        templates: TemplateService,
        tables: TemplateTablesAccess,
        semantics: SemanticService,
        metrics: MetricService,
        dashboards: DashboardService,
    ) -> None:
        self.templates, self.tables, self.semantics = templates, tables, semantics
        self.metrics, self.dashboards = metrics, dashboards
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
        self, owner: UUID, artifact: UUID, casts: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        proposal = self.proposals.get(
            owner,
            artifact,
            [
                CastProposal.model_validate({k: cast[k] for k in ("column_id", "type", "scale")})
                for cast in casts
            ],
        )
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

    # --- Fase 11D: interpretación reutilizable ---

    def mapping_match(self, owner: UUID, project: UUID, artifact: UUID) -> MatchResult:
        _, columns = self.tables.columns(owner, artifact)
        match = self.templates.match(owner, project, columns)
        ids = {column.name: column.id for column in columns}
        return MatchResult(
            status=match.status,
            revision_id=match.revision.id if match.revision else None,
            problems=match.problems,
            casts=[
                {
                    "column_id": str(ids[c.column]),
                    "column": c.column,
                    "type": c.type,
                    "scale": c.scale,
                }
                for c in match.casts
                if c.column in ids
            ],
        )

    def apply_mapping(self, owner: UUID, mapping_revision: UUID, artifact: UUID) -> UUID:
        """Confirma la semántica del mapeo sobre la tabla (revisión semántica normal)."""
        mapping = self.templates.revision(owner, mapping_revision)
        _, columns = self.tables.columns(owner, artifact)
        context = self.semantics.context(owner, artifact)
        draft = self.templates.semantic_draft(
            mapping, columns, context.editable.model_dump(mode="json")
        )
        saved = self.semantics.save(
            owner,
            artifact,
            context.table_ref.artifact_sha256,
            context.revision_count,
            SemanticDraft.model_validate(draft),
            uuid5(mapping_revision, str(artifact)),
            str(artifact),
        )
        return saved.revision.id

    # --- Fase 11E: dashboard automático ---

    def start_analysis(
        self, owner: UUID, project: UUID, mapping_revision: UUID, artifact: UUID, key: UUID
    ) -> dict[str, Any] | None:
        mapping = self.templates.revision(owner, mapping_revision)
        _, columns = self.tables.columns(owner, artifact)
        spec = analysis_spec(mapping.content, {column.name: column.id for column in columns})
        if spec is None:
            return None
        context = self.semantics.context(owner, artifact)
        sha256, head = context.table_ref.artifact_sha256, context.head
        semantic_ref = (
            {"id": str(head.id), "revision": head.revision, "content_sha256": head.content_sha256}
            if head
            else None
        )
        revisions: dict[str, dict[str, str]] = {}
        for metric in spec.metrics:
            saved = self.metrics.save(
                owner,
                artifact,
                sha256,
                None,
                0,
                MetricDraft.model_validate(metric.draft),
                uuid5(key, f"metric:{metric.name}"),
                str(key),
            )
            revisions[metric.name] = {
                "revision_id": str(saved.revision.id),
                "content_sha256": saved.revision.content_sha256,
            }
        queries: list[dict[str, Any]] = []
        for query in spec.queries:
            parameters = {
                "metrics": [revisions[name] for name in query.metrics],
                **resolve(query.parameters, revisions),
            }
            draft = PlanDraft.model_validate(
                {
                    "semantic_ref": semantic_ref,
                    "steps": [
                        {
                            "id": "query",
                            "operation": "analytics.query",
                            "version": query.version,
                            "input": {"kind": "input", "alias": "source"},
                            "parameters": parameters,
                        }
                    ],
                }
            )
            plan = self.planning.create(
                owner, project, artifact, sha256, draft, uuid5(key, f"plan:{query.name}"), str(key)
            )
            if not plan.validation.valid:
                raise ApplicationError(
                    "ANALYSIS_PLAN_INVALID",
                    "; ".join(problem.message for problem in plan.validation.problems),
                    409,
                )
            queries.append(
                {
                    "name": query.name,
                    "plan_revision_id": str(plan.id),
                    "execution_id": None,  # se lanza cuando hay capacidad (QUEUE_LIMIT)
                    "cards": [
                        {
                            "name": card.name,
                            "title": card.title,
                            "view": card.view,
                            "size": card.size,
                            "metric": f"m{card.metric}",
                        }
                        for card in query.cards
                    ],
                }
            )
        return {
            "template": spec.template,
            "title": spec.title,
            "analysis_version": ANALYSIS_VERSION,
            "metrics": revisions,
            "queries": queries,
        }

    def start_query(self, owner: UUID, plan_revision: UUID, key: UUID) -> UUID | None:
        """Ejecuta una consulta del dashboard; None si no hay capacidad (QUEUE_LIMIT): se
        reintenta en la próxima reconciliación sin perder lo ya lanzado."""
        try:
            return self.planning.execute(owner, plan_revision, key, str(key)).id
        except ApplicationError as error:
            if error.code == "QUEUE_LIMIT":
                return None
            raise

    def dashboard_head_revision(self, owner: UUID, family: UUID) -> int:
        return self.dashboards.head(owner, family).revision

    def publish_dashboard(
        self,
        owner: UUID,
        project: UUID,
        family: UUID | None,
        analysis: dict[str, Any],
        key: UUID,
    ) -> tuple[UUID, UUID]:
        draft = DashboardDraft.model_validate(
            {
                "title": analysis["title"],
                "description": "Generado por el modo automático con la versión activa.",
                "cards": [
                    {
                        # ID estable entre revisiones: misma tarjeta en cada carga.
                        "id": str(uuid5(project, f"{analysis['template']}:{card['name']}")),
                        "title": card["title"],
                        "plan_revision_id": query["plan_revision_id"],
                        "execution_id": query["execution_id"],
                        "view": card["view"],
                        "size": card["size"],
                        "metric": card["metric"],
                    }
                    for query in analysis["queries"]
                    for card in query["cards"]
                ],
            }
        )
        if family is None:
            saved = self.dashboards.create(owner, project, draft, key, str(key))
        else:
            expected = int(analysis["dashboard_publication_target"]["expected_revision"])
            saved = self.dashboards.revise(owner, family, expected, draft, key, str(key))
        return saved.revision.family_id, saved.revision.id
