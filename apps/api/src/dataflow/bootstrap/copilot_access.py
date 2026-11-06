"""Puerto del copiloto: tabla, semántica, métricas, validación de planes, ejecuciones y
evidencia por las interfaces públicas de cada módulo.

copilot no importa planning, analytics, executions ni understanding: bootstrap traduce sus
servicios a hechos simples (mismo patrón que dashboards, Fase 8).
"""

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from dataflow.modules.analytics.application import MetricService, addressed_cells
from dataflow.modules.analytics.contracts import MetricDraft
from dataflow.modules.copilot.contracts import (
    ColumnFact,
    ExecutionFact,
    MetricFact,
    PlanRef,
    ProposalProblem,
    ResultCell,
    ResultFacts,
    TableContext,
    TableRef,
    Validation,
)
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanDraft, Problem
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.public import SemanticReference, SemanticService
from dataflow.platform.errors import ApplicationError


def proposal_problems(problems: list[Problem]) -> list[ProposalProblem]:
    return [
        ProposalProblem(
            code=p.code,
            message=p.message,
            resolve_in="understanding" if p.resolve_in == "understanding" else "plan",
        )
        for p in problems
    ]


class CopilotAccess:
    def __init__(
        self,
        planning: PlanningService,
        executions: Executions,
        datasets: Datasets,
        semantics: SemanticService,
        metrics: MetricService,
        projects: ProjectPermissions,
    ) -> None:
        self.planning, self.executions, self.datasets = planning, executions, datasets
        self.semantics, self.metric_service, self.projects = semantics, metrics, projects

    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None:
        self.projects.require(owner, project, writable)

    def table(self, owner: UUID, version: UUID) -> TableContext:
        record = self.datasets.get(owner, version)
        tables = [t for t in self.executions.representations(owner, version) if t.kind == "table"]
        if not tables or not tables[0].columns:
            raise ApplicationError(
                "PLAN_TABLE_REQUIRED", "La versión elegida no tiene una tabla publicada.", 409
            )
        artifact = tables[0]
        context = self.semantics.context(owner, artifact.id)
        head = context.head
        semantic = {c.id: c for c in head.content.columns} if head else {}
        profile = {c.name: c for c in context.profile.columns} if context.profile else {}
        columns = []
        for facts in context.columns:
            decided = semantic.get(facts.id)
            profiled = profile.get(facts.name)
            columns.append(
                ColumnFact(
                    id=facts.id,
                    name=facts.name,
                    technical_type=facts.technical_type,
                    null_count=profiled.null_count if profiled else None,
                    distinct_count=profiled.unique_count if profiled else None,
                    role=decided.role if decided else None,
                    confirmed=bool(decided and decided.review.state == "confirmed"),
                    unit=decided.unit if decided else None,
                    currency=decided.currency if decided else None,
                    description=decided.description if decided else None,
                )
            )
        reference = (
            SemanticReference(
                id=head.id, revision=head.revision, content_sha256=head.content_sha256
            )
            if head
            else None
        )
        return TableContext(
            ref=TableRef(
                project_id=record.project_id,
                version_id=version,
                artifact_id=artifact.id,
                artifact_sha256=artifact.content.sha256,
                semantic_ref=reference.model_dump(mode="json") if reference else None,
            ),
            version_number=record.number,
            row_count=artifact.row_count,
            columns=columns,
            semantic_revision=head.revision if head else None,
            dataset_description=head.content.dataset_description if head else None,
            row_grain=head.content.row_grain.description if head else None,
        )

    def metrics(self, owner: UUID, artifact: UUID) -> list[MetricFact]:
        result = []
        for summary in self.metric_service.context(owner, artifact).metrics:
            content = summary.head.content
            result.append(
                MetricFact(
                    revision_id=summary.head.id,
                    content_sha256=summary.head.content_sha256,
                    label=content.label,
                    aggregation=content.aggregation,
                    measure_column_id=content.measure_column_id,
                    time_column_id=content.time_column_id,
                    filters=[f.model_dump(mode="json") for f in content.filters],
                    applicable=summary.applicable,
                )
            )
        return result

    def draft(self, table: TableRef, steps: list[dict[str, Any]]) -> PlanDraft | Validation:
        try:
            return PlanDraft.model_validate({"semantic_ref": table.semantic_ref, "steps": steps})
        except ValidationError:
            return Validation(
                valid=False,
                problems=[
                    ProposalProblem(
                        code="INVALID_PARAMETERS",
                        message="Los pasos propuestos no tienen la forma de un plan.",
                    )
                ],
            )

    def validate_plan(
        self, owner: UUID, table: TableRef, steps: list[dict[str, Any]]
    ) -> Validation:
        draft = self.draft(table, steps)
        if isinstance(draft, Validation):
            return draft
        try:
            validation = self.planning.validate_draft(owner, table.artifact_id, draft)
        except ApplicationError as exc:
            if exc.status >= 500 or exc.code in {"PROJECT_NOT_FOUND"}:
                raise
            return Validation(
                valid=False, problems=[ProposalProblem(code=exc.code, message=exc.message)]
            )
        return Validation(valid=validation.valid, problems=proposal_problems(validation.problems))

    def create_plan(
        self,
        owner: UUID,
        table: TableRef,
        steps: list[dict[str, Any]],
        key: UUID,
        correlation: str,
    ) -> PlanRef:
        draft = self.draft(table, steps)
        if isinstance(draft, Validation):
            raise ApplicationError("PROPOSAL_INVALID", draft.problems[0].message, 422)
        view = self.planning.create(
            owner,
            table.project_id,
            table.artifact_id,
            table.artifact_sha256,
            draft,
            key,
            correlation,
        )
        return PlanRef(
            revision_id=view.id,
            valid=view.validation.valid,
            problems=proposal_problems(view.validation.problems),
        )

    def execute(self, owner: UUID, plan_revision: UUID, key: UUID, correlation: str) -> UUID:
        return self.planning.execute(owner, plan_revision, key, correlation).id

    def create_metric(
        self, owner: UUID, table: TableRef, draft: dict[str, Any], key: UUID, correlation: str
    ) -> UUID:
        try:
            value = MetricDraft.model_validate(draft)
        except ValidationError as exc:
            raise ApplicationError(
                "PROPOSAL_INVALID", "El borrador de métrica no es válido.", 422
            ) from exc
        saved = self.metric_service.save(
            owner, table.artifact_id, table.artifact_sha256, None, 0, value, key, correlation
        )
        return saved.revision.id

    def execution(self, owner: UUID, execution: UUID) -> ExecutionFact:
        run = self.executions.get(owner, execution)
        return ExecutionFact(
            id=run.id, project_id=run.project_id, version_id=run.version_id, state=run.state
        )

    def result(self, owner: UUID, execution: UUID, limit: int) -> ResultFacts:
        result = self.metric_service.result(owner, execution)
        definitions = {m.key: m for m in result.metrics}
        cells: list[ResultCell] = []
        total = 0
        for row in result.rows:
            group = {d.name: row.labels.get(d.key) for d in result.dimensions}
            period = row.labels.get("period")
            for cell in addressed_cells(result, row):
                total += 1
                if len(cells) >= limit:
                    continue
                definition = definitions[cell.metric_key]
                detail = cell.detail or {}
                cells.append(
                    ResultCell(
                        evidence_id=cell.identifier,
                        cell=cell.name,
                        metric_key=cell.metric_key,
                        metric_label=definition.label,
                        aggregation=definition.aggregation,
                        currency=definition.currency,
                        unit=definition.unit,
                        value=cell.value,
                        group=group,
                        period=period,
                        comparison=str(detail["comparison"]) if "comparison" in detail else None,
                    )
                )
        return ResultFacts(
            execution_id=execution,
            operation=result.operation,
            metrics=[
                {
                    "clave": m.key,
                    "etiqueta": m.label,
                    "agregacion": m.aggregation,
                    "moneda": m.currency,
                    "unidad": m.unit,
                    "filas_entrada": m.counts.input_rows,
                    "excluidas_por_filtros": m.counts.excluded_by_filters,
                    "excluidas_por_nulos": m.counts.excluded_by_nulls,
                    "incluidas": m.counts.included_rows,
                }
                for m in result.metrics
            ],
            cells=cells,
            total_cells=total,
            rows=result.row_count,
        )

    def evidence_value(self, owner: UUID, execution: UUID, evidence_id: str) -> str | None:
        try:
            return self.metric_service.evidence(owner, execution, evidence_id).value
        except ApplicationError:
            return None
