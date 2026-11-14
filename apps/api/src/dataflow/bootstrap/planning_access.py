from uuid import UUID

from dataflow.modules.analytics.application import MetricService
from dataflow.modules.analytics.contracts import MEASURED, SHAREABLE
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.contracts import (
    MetricRequirement,
    PinnedTable,
    RulesetRequirement,
    SemanticRole,
    TableInput,
)
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.quality.application import RulesetService
from dataflow.modules.understanding.public import (
    SemanticReference,
    SemanticService,
    TableReference,
)
from dataflow.platform.errors import ApplicationError


class PlanningTableAccess:
    """Puerto de planning: resuelve tablas, permisos y semántica mediante interfaces públicas."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        projects: ProjectPermissions,
        semantics: SemanticService,
        rulesets: RulesetService,
        metrics: MetricService,
    ) -> None:
        self.datasets, self.executions = datasets, executions
        self.projects, self.semantics, self.rulesets = projects, semantics, rulesets
        self.metrics = metrics

    def table(self, owner: UUID, artifact: UUID) -> PinnedTable:
        table = self.executions.artifact(owner, artifact)
        if table.kind != "table" or not table.columns:
            raise ApplicationError(
                "PLAN_TABLE_REQUIRED",
                "Selecciona una representación tabular publicada con esquema.",
                409,
            )
        version = self.datasets.get(owner, table.version_id)
        self.projects.require(owner, version.project_id)
        return PinnedTable(
            version.project_id,
            TableInput(
                version_id=version.id,
                version_content_sha256=version.content.sha256,
                artifact_id=table.id,
                artifact_sha256=table.content.sha256,
            ),
            frozenset(UUID(str(column["id"])) for column in table.columns),
            {
                UUID(str(column["id"])): column.get("technical_type", "string")
                for column in table.columns
            },
        )

    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None:
        self.projects.require(owner, project, writable)

    def confirmed_roles(
        self, owner: UUID, reference: SemanticReference, table: TableInput
    ) -> dict[UUID, SemanticRole]:
        self.semantics.resolve_for_table(
            owner,
            reference,
            TableReference(
                version_id=table.version_id,
                version_content_sha256=table.version_content_sha256,
                artifact_id=table.artifact_id,
                artifact_sha256=table.artifact_sha256,
            ),
        )
        revision = self.semantics.get(owner, reference.id)
        return {
            column.id: column.role
            for column in revision.content.columns
            if column.review.state == "confirmed"
        }

    def semantic_reference(self, owner: UUID, revision: UUID) -> SemanticReference:
        value = self.semantics.get(owner, revision)
        return SemanticReference(
            id=value.id, revision=value.revision, content_sha256=value.content_sha256
        )

    def quality_ruleset(self, owner: UUID, revision: UUID) -> RulesetRequirement | None:
        facts = self.rulesets.facts(owner, revision)
        if facts is None:
            return None
        return RulesetRequirement(
            facts.content_sha256,
            {column: frozenset(types) for column, types in facts.column_types.items()},
        )

    def analytics_metric(self, owner: UUID, revision: UUID) -> MetricRequirement | None:
        facts = self.metrics.facts(owner, revision)
        if facts is None:
            return None
        return MetricRequirement(
            facts.content_sha256,
            facts.measure_column_id,
            frozenset(facts.measure_types),
            facts.aggregation in MEASURED,
            facts.time_column_id,
            tuple(facts.filter_column_ids),
            facts.aggregation in SHAREABLE | {"sum_product"},
            facts.second_measure_column_id,
            facts.semi_additive is not None,
            3 if facts.requires_query_v3 else 1,
        )

    def column_units(
        self, owner: UUID, reference: SemanticReference, table: TableInput
    ) -> dict[UUID, str | None]:
        """Moneda (preferente) o unidad de las columnas confirmadas en la revisión fijada."""
        self.confirmed_roles(owner, reference, table)  # verifica revisión ↔ tabla
        revision = self.semantics.get(owner, reference.id)
        return {
            column.id: f"currency:{column.currency}"
            if column.currency
            else f"unit:{column.unit}"
            if column.unit
            else None
            for column in revision.content.columns
            if column.review.state == "confirmed"
        }

    def lock_owner(self, owner: UUID) -> None:
        self.datasets.lock_owner(owner)
