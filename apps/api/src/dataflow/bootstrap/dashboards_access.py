"""Puerto de dashboards: planes, ejecuciones, versiones y semántica por interfaces públicas.

dashboards no importa planning ni executions: bootstrap traduce sus servicios a hechos simples.
"""

from typing import Any
from uuid import UUID

from dataflow.modules.dashboards.contracts import ExecutionFacts, PlanFacts, TargetTable
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanDraft, PlanView
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.public import SemanticReference, SemanticService
from dataflow.platform.errors import ApplicationError


def plan_facts(view: PlanView) -> PlanFacts:
    return PlanFacts(
        revision_id=view.id,
        project_id=view.project_id,
        version_id=view.input.version_id,
        artifact_id=view.input.artifact_id,
        operations=[f"{step.operation}@{step.version}" for step in view.steps],
        parameters=dict(view.steps[0].parameters) if view.steps else {},
        steps=[step.model_dump(mode="json") for step in view.steps],
        semantic_ref=view.semantic_ref.model_dump(mode="json") if view.semantic_ref else None,
        valid=view.validation.valid,
        problems=[(problem.code, problem.message) for problem in view.validation.problems],
    )


class DashboardAccess:
    def __init__(
        self,
        planning: PlanningService,
        executions: Executions,
        datasets: Datasets,
        semantics: SemanticService,
        projects: ProjectPermissions,
    ) -> None:
        self.planning, self.executions, self.datasets = planning, executions, datasets
        self.semantics, self.projects = semantics, projects

    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None:
        self.projects.require(owner, project, writable)

    def plan(self, owner: UUID, revision: UUID) -> PlanFacts:
        return plan_facts(self.planning.get(owner, revision))

    def execution(self, owner: UUID, execution: UUID) -> ExecutionFacts:
        run = self.executions.get(owner, execution)
        rows = next(
            (
                artifact.row_count
                for artifact in self.executions.artifacts(owner, execution)
                if artifact.kind == "analysis_result"
            ),
            None,
        )
        return ExecutionFacts(
            id=run.id,
            project_id=run.project_id,
            plan_revision_id=run.plan.id if run.plan else None,
            version_id=run.version_id,
            state=run.state,
            finished_at=run.finished_at,
            error_message=run.error_message,
            result_rows=rows,
        )

    def version_number(self, owner: UUID, version: UUID) -> int:
        return self.datasets.get(owner, version).number

    def target(self, owner: UUID, version: UUID) -> TargetTable:
        record = self.datasets.get(owner, version)
        tables = [t for t in self.executions.representations(owner, version) if t.kind == "table"]
        if not tables or not tables[0].columns:
            raise ApplicationError(
                "PLAN_TABLE_REQUIRED", "La versión elegida no tiene una tabla publicada.", 409
            )
        table = tables[0]
        head = self.semantics.context(owner, table.id).head
        reference = (
            SemanticReference(
                id=head.id, revision=head.revision, content_sha256=head.content_sha256
            )
            if head
            else None
        )
        return TargetTable(
            project_id=record.project_id,
            version_id=version,
            artifact_id=table.id,
            artifact_sha256=table.content.sha256,
            semantic_ref=reference.model_dump(mode="json") if reference else None,
        )

    def create_plan(
        self,
        owner: UUID,
        table: TargetTable,
        steps: list[dict[str, Any]],
        key: UUID,
        correlation: str,
    ) -> PlanFacts:
        draft = PlanDraft.model_validate({"semantic_ref": table.semantic_ref, "steps": steps})
        view = self.planning.create(
            owner,
            table.project_id,
            table.artifact_id,
            table.artifact_sha256,
            draft,
            key,
            correlation,
        )
        return plan_facts(view)

    def execute(self, owner: UUID, plan_revision: UUID, key: UUID, correlation: str) -> UUID:
        return self.planning.execute(owner, plan_revision, key, correlation).id
