from collections.abc import Callable
from uuid import UUID

from dataflow.modules.automation.contracts import (
    ColumnEffect,
    EffectFacts,
    PlannedStep,
    PreviewFacts,
)
from dataflow.modules.cleaning.application import CleaningService
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.errors import ApplicationError


class PolicyCleaningAccess:
    """Puerto de automation sobre cleaning, planning y proyectos (Fase 11B): reúne los hechos de
    una vista previa para la evaluación pura y usa los casos de uso de aprobación existentes."""

    def __init__(
        self,
        cleaning: CleaningService,
        planning: PlanningService,
        executions: Executions,
        projects: ProjectPermissions,
    ) -> None:
        self.cleaning, self.planning = cleaning, planning
        self.executions, self.projects = executions, projects

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None:
        self.projects.require(owner, project, writable=writable)

    def preview_facts(self, owner: UUID, execution: UUID) -> PreviewFacts:
        preview = self.cleaning.get_preview(owner, execution)
        plan = self.planning.get(owner, preview.plan_revision_id)
        table = self.executions.artifact(owner, plan.input.artifact_id)
        names = {str(column["id"]): str(column["name"]) for column in table.columns or []}
        effect = None
        if preview.manifest is not None:
            counts = preview.manifest.counts
            effect = EffectFacts(
                input_rows=counts.input_rows,
                output_rows=counts.output_rows,
                excluded_rows=counts.excluded_rows,
                created_nulls=counts.created_nulls,
                rounded_cells=preview.manifest.rounded_cells,
                columns=None
                if preview.column_effects is None
                else [
                    ColumnEffect(c.column_id, c.modified_cells, c.created_nulls)
                    for c in preview.column_effects
                ],
            )
        approval = preview.approval
        return PreviewFacts(
            execution_id=preview.execution_id,
            project_id=preview.project_id,
            state=preview.state,
            plan_valid=plan.validation.valid,
            steps=[PlannedStep(s.id, s.operation, dict(s.parameters)) for s in plan.steps],
            column_names=names,
            effect_sha256=preview.effect_sha256,
            effect=effect,
            active_approval_id=approval.id if approval and approval.status == "active" else None,
        )

    def approve_with(
        self,
        owner: UUID,
        execution: UUID,
        effect_sha256: str,
        correlation: str,
        before_commit: Callable[[UUID], None],
    ) -> UUID:
        approval = self.cleaning.approve(
            owner,
            execution,
            effect_sha256,
            correlation,
            before_commit=lambda view: before_commit(view.id),
        )
        return approval.id

    def revoke_if_pending(self, owner: UUID, approval: UUID, correlation: str) -> bool:
        try:
            self.cleaning.revoke(owner, approval, correlation)
        except ApplicationError as error:
            if error.status == 409:  # en curso, ya aplicada o proyecto archivado
                return False
            raise
        return True
