"""Casos de uso de analytics: métricas con revisiones inmutables, lectura de resultados y
resolución de evidencias."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.analytics.contracts import (
    AnalysisResult,
    AnalysisResultV2,
    AnalysisResultV3,
    AnyAnalysisResult,
    BaseTable,
    EvidenceReference,
    EvidenceView,
    MetricContent,
    MetricContext,
    MetricDraft,
    MetricFacts,
    MetricReference,
    MetricRepository,
    MetricRevision,
    MetricSummary,
    ResultRow,
    ResultRowV2,
    ResultRowV3,
    SaveMetricResponse,
    measure_types,
)
from dataflow.modules.analytics.domain import metric_problems
from dataflow.modules.analytics.engine import (
    Metric,
    cell_reference,
    change_pct_detail,
    comparison_detail,
    evidence_reference,
    rank_detail,
    share_detail,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class AnalyticsTables(Protocol):
    """Puerto implementado en bootstrap: tablas publicadas, permisos y resultados."""

    def table(
        self, owner: UUID, artifact: UUID
    ) -> tuple[UUID, BaseTable, list[dict[str, Any]]]: ...
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def analysis_result(self, owner: UUID, execution: UUID) -> bytes | None: ...


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def content_sha256(content: MetricContent) -> str:
    """Los campos de 11E no cuentan si no se usan: las métricas anteriores conservan su hash."""
    return digest("analytics_metric", content.hashed())


class MetricService:
    def __init__(self, repository: MetricRepository, tables: AnalyticsTables, uow: UnitOfWork):
        self.repository, self.tables, self.uow = repository, tables, uow

    def context(self, owner: UUID, artifact: UUID) -> MetricContext:
        """Métricas del proyecto con su aplicabilidad a esta tabla: una derivada conserva los
        IDs de columna y puede usar las métricas de su origen si los tipos son compatibles."""
        project, _, columns = self.tables.table(owner, artifact)
        summaries = []
        for family in self.repository.families(owner, project):
            head = self.repository.head(family)
            if head is None:
                continue
            revision, count = head
            problems = metric_problems(revision.content, columns)
            summaries.append(
                MetricSummary(
                    family_id=family,
                    head=revision,
                    revision_count=count,
                    anchored_here=revision.content.base_table.artifact_id == artifact,
                    applicable=not problems,
                    problems=problems,
                )
            )
        return MetricContext(artifact_id=artifact, metrics=summaries)

    def save(
        self,
        owner: UUID,
        artifact: UUID,
        table_sha256: str,
        family: UUID | None,
        expected: int,
        draft: MetricDraft,
        key: UUID,
        correlation: str,
    ) -> SaveMetricResponse:
        try:
            project, base, columns = self.tables.table(owner, artifact)
            self.tables.require_project(owner, project, writable=True)
            if base.artifact_sha256 != table_sha256:
                raise ApplicationError(
                    "INPUT_MISMATCH", "La tabla no coincide con la consultada.", 409
                )
            problems = metric_problems(draft, columns)
            if problems:
                raise ApplicationError(
                    "METRIC_INVALID", " ".join(problem.message for problem in problems), 422
                )
            scope = family or artifact
            fingerprint = digest(
                "analytics_metric_request",
                {
                    "family_id": str(family) if family else None,
                    "expected_revision": expected,
                    "draft": draft.hashed(),
                    "base_table": base.model_dump(mode="json"),
                },
            )
            self.repository.lock_scope(scope)
            replayed = self.repository.replay(owner, scope, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveMetricResponse(revision=replayed, changed=True)
            if family is None:
                if expected != 0:
                    raise ApplicationError("METRIC_CONFLICT", "La métrica cambió: recarga.", 409)
                family, head = self.repository.create_family(owner, project, base), 0
            else:
                anchored, head = self.repository.lock_family(owner, family)
                if anchored.artifact_id != artifact:
                    raise ApplicationError(
                        "METRIC_ANCHOR_MISMATCH",
                        "Edita la métrica desde la versión en la que se definió.",
                        409,
                    )
                if head != expected:
                    raise ApplicationError("METRIC_CONFLICT", "La métrica cambió: recarga.", 409)
            content = MetricContent(**draft.model_dump(), base_table=base)
            current = self.repository.head(family)
            if current and current[0].content == content:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return SaveMetricResponse(revision=current[0], changed=False)
            revision = MetricRevision(
                id=uuid4(),
                family_id=family,
                project_id=project,
                revision=head + 1,
                previous_revision_id=current[0].id if current else None,
                content=content,
                content_sha256=content_sha256(content),
                created_by=owner,
                created_at=datetime.now(UTC),
            )
            self.repository.append(family, head, revision, correlation)
            self.repository.remember(owner, scope, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveMetricResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def revision(self, owner: UUID, revision: UUID) -> MetricRevision:
        value = self.repository.revision(owner, revision)
        self.tables.require_project(owner, value.project_id)
        return value

    def facts(self, owner: UUID, revision: UUID) -> MetricFacts | None:
        """Para validar planes; None si no existe o es ajena."""
        try:
            value = self.repository.revision(owner, revision)
        except ApplicationError:
            return None
        content = value.content
        return MetricFacts(
            content_sha256=value.content_sha256,
            aggregation=content.aggregation,
            measure_column_id=content.measure_column_id,
            measure_types=sorted(measure_types(content.aggregation)),
            time_column_id=content.time_column_id,
            filter_column_ids=[f.column_id for f in content.filters],
            second_measure_column_id=content.second_measure_column_id,
            semi_additive=content.semi_additive,
            requires_query_v3=content.requires_query_v3,
        )

    def result(self, owner: UUID, execution: UUID) -> AnyAnalysisResult:
        content = self.tables.analysis_result(owner, execution)
        if content is None:
            raise ApplicationError(
                "RESULT_NOT_READY", "El resultado del análisis no está disponible.", 409
            )
        data = json.loads(content)
        if data.get("operation") == "analytics.query@3":
            return AnalysisResultV3.model_validate(data)
        if data.get("operation") == "analytics.query@2":
            return AnalysisResultV2.model_validate(data)
        return AnalysisResult.model_validate(data)

    def evidence(self, owner: UUID, execution: UUID, evidence_id: str) -> EvidenceView:
        """Resuelve una cifra por su `evidence_id` (de cualquier celda) y vuelve a calcular la
        dirección para comprobar que el identificador corresponde exactamente a esa cifra."""
        result = self.result(owner, execution)
        for row in result.rows:
            for cell in addressed_cells(result, row):
                if cell.identifier != evidence_id:
                    continue
                definition = next(m for m in result.metrics if m.key == cell.metric_key)
                metric = Metric(
                    MetricReference(
                        revision_id=definition.revision_id,
                        content_sha256=definition.content_sha256,
                    ),
                    definition.revision,
                    self.repository.revision(owner, definition.revision_id).content,
                )
                computed, payload = (
                    evidence_reference(result.scope, metric, row.key)
                    if cell.detail is None
                    else cell_reference(result.scope, metric, row.key, cell.name, cell.detail)
                )
                if computed != evidence_id:
                    raise ApplicationError(
                        "INTEGRITY_ERROR", "La evidencia no coincide con el resultado.", 409
                    )
                return EvidenceView(
                    reference=EvidenceReference(evidence_id=computed, **payload),
                    value=cell.value,
                    definition=definition,
                    labels=row.labels,
                    operation=result.operation,
                    metric_value=row.values[cell.metric_key],
                    snapshot=row.snapshots.get(cell.metric_key)
                    if isinstance(row, ResultRowV3)
                    else None,
                    **cell.context,
                )
        raise ApplicationError("EVIDENCE_NOT_FOUND", "Esa cifra no existe en el resultado.", 404)


@dataclass(frozen=True)
class AddressedCell:
    metric_key: str
    name: str
    identifier: str
    detail: dict[str, Any] | None  # None: `value`, dirección de @1
    value: str | None
    context: dict[str, Any]


def addressed_cells(result: AnyAnalysisResult, row: ResultRow) -> Iterator[AddressedCell]:
    """Todas las cifras direccionables de una fila, con el detalle que las generó."""
    for key, identifier in row.evidence.items():
        yield AddressedCell(key, "value", identifier, None, row.values[key], {})
    if not isinstance(result, AnalysisResultV2 | AnalysisResultV3) or not isinstance(
        row, ResultRowV2
    ):
        return
    for key, comparisons in row.comparisons.items():
        for kind, comparison in comparisons.items():
            context = {"comparison": comparison}
            base = comparison_detail(kind, comparison.base_period)
            yield AddressedCell(
                key, kind, comparison.evidence["base"], base, comparison.base, context
            )
            yield AddressedCell(
                key, "change", comparison.evidence["change"], base, comparison.change, context
            )
            yield AddressedCell(
                key,
                "change_pct",
                comparison.evidence["change_pct"],
                change_pct_detail(kind, comparison.base_period, result.change_scale),
                comparison.change_pct,
                context,
            )
    for key, share in row.share.items():
        total = next(
            (t for t in result.shares if t.metric == key and t.period == row.key["period"]),
            None,
        )
        yield AddressedCell(
            key,
            "share_of_total",
            share.evidence,
            share_detail(result.share_scale),
            share.value,
            {"share": share, "share_total": total},
        )
    if row.rank is not None and result.ranking is not None:
        ranking = result.ranking
        yield AddressedCell(
            ranking.metric,
            "rank",
            row.rank.evidence,
            rank_detail(ranking.direction, ranking.top_n, row.rank.tied_with_previous),
            str(row.rank.position),
            {"rank": row.rank, "ranking": ranking},
        )
