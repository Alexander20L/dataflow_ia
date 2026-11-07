from uuid import UUID

from dataflow.modules.cleaning.proposal import (
    ConfirmedTokens,
    ProposalColumn,
    ProposalInputs,
    ProposalIssue,
    ProposalSemanticRef,
)
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.ingestion.application import IngestionService
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanView
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.public import SemanticService


class CleaningPlanAccess:
    """Puerto de cleaning sobre planning y proyectos (planes guardados, validación y permisos)."""

    def __init__(
        self, planning: PlanningService, projects: ProjectPermissions, datasets: Datasets
    ) -> None:
        self.planning, self.projects, self.datasets = planning, projects, datasets

    def plan(self, owner: UUID, revision: UUID) -> PlanView:
        return self.planning.get(owner, revision)

    def require_write(self, owner: UUID, project: UUID) -> None:
        self.projects.require(owner, project, writable=True)

    def lock_owner(self, owner: UUID) -> None:
        self.datasets.lock_owner(owner)


class CleaningProposalAccess:
    """Puerto de la propuesta de limpieza: columnas y revisión semántica vigente (understanding,
    que también comprueba el acceso al proyecto) y diagnóstico de calidad de la versión."""

    def __init__(self, semantics: SemanticService, ingestion: IngestionService) -> None:
        self.semantics, self.ingestion = semantics, ingestion

    def proposal_inputs(self, owner: UUID, artifact: UUID) -> ProposalInputs:
        context = self.semantics.context(owner, artifact)
        diagnostic = self.ingestion.diagnostic(owner, context.table_ref.version_id)
        head = context.head
        tokens = (
            [
                ConfirmedTokens(column_id=column.id, tokens=list(column.null_policy.tokens))
                for column in head.content.columns
                if column.review.state == "confirmed"
                and column.null_policy.mode == "explicit_tokens"
            ]
            if head
            else []
        )
        return ProposalInputs(
            representation_id=artifact,
            table_sha256=context.table_ref.artifact_sha256,
            semantic_revision=ProposalSemanticRef(
                id=head.id, revision=head.revision, content_sha256=head.content_sha256
            )
            if head
            else None,
            columns=[
                ProposalColumn(id=c.id, name=c.name, technical_type=c.technical_type)
                for c in context.columns
            ],
            issues=[
                ProposalIssue(rule=issue.rule, column=issue.column)
                for issue in diagnostic.quality.issues
            ],
            confirmed_tokens=tokens,
        )
