"""Casos de uso de analytics: métricas con revisiones inmutables, lectura de resultados y
resolución de evidencias."""

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.analytics.contracts import (
    AnalysisResult,
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
    SaveMetricResponse,
    measure_types,
)
from dataflow.modules.analytics.domain import metric_problems
from dataflow.modules.analytics.engine import Metric, evidence_reference
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
    return digest("analytics_metric", content.model_dump(mode="json"))


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
                    "draft": draft.model_dump(mode="json"),
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
        )

    def result(self, owner: UUID, execution: UUID) -> AnalysisResult:
        content = self.tables.analysis_result(owner, execution)
        if content is None:
            raise ApplicationError(
                "RESULT_NOT_READY", "El resultado del análisis no está disponible.", 409
            )
        return AnalysisResult.model_validate(json.loads(content))

    def evidence(self, owner: UUID, execution: UUID, evidence_id: str) -> EvidenceView:
        """Resuelve una cifra por su `evidence_id` y vuelve a calcular la dirección para
        comprobar que el identificador corresponde exactamente a esa cifra."""
        result = self.result(owner, execution)
        for row in result.rows:
            for key, identifier in row.evidence.items():
                if identifier != evidence_id:
                    continue
                definition = next(m for m in result.metrics if m.key == key)
                reference = MetricReference(
                    revision_id=definition.revision_id,
                    content_sha256=definition.content_sha256,
                )
                metric = Metric(
                    reference,
                    definition.revision,
                    self.repository.revision(owner, definition.revision_id).content,
                )
                computed, payload = evidence_reference(result.scope, metric, row.key)
                if computed != evidence_id:
                    raise ApplicationError(
                        "INTEGRITY_ERROR", "La evidencia no coincide con el resultado.", 409
                    )
                return EvidenceView(
                    reference=EvidenceReference(evidence_id=computed, **payload),
                    value=row.values[key],
                    definition=definition,
                    labels=row.labels,
                )
        raise ApplicationError("EVIDENCE_NOT_FOUND", "Esa cifra no existe en el resultado.", 404)
