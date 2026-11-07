"""Ejecutor de analytics.query@1, @2 y @3: de sólo lectura, se ejecutan como plan normal."""

import json
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.analytics.contracts import (
    AnalysisResult,
    AnalysisResultV2,
    AnalysisResultV3,
    AnyAnalysisResult,
    BaseTable,
    EvidenceScope,
    MetricRevision,
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
    product_unit,
)
from dataflow.modules.datasets.public import ObjectStore
from dataflow.modules.executions.public import (
    ArtifactKind,
    ArtifactOutput,
    Lease,
    PlanStepSpec,
    StepInput,
    StepResult,
)
from dataflow.platform.errors import ApplicationError
from dataflow.platform.isolation import run_isolated

MODULE = "dataflow.modules.analytics.processor"


def query_parameters(step: PlanStepSpec) -> QueryParameters:
    """Parámetros según la versión del paso: @1 conserva su modelo y su resultado."""
    models: dict[int, type[QueryParameters]] = {2: QueryParametersV2, 3: QueryParametersV3}
    return models.get(step.version, QueryParameters).model_validate(step.parameters)


class MetricSource(Protocol):
    """Revisiones de métricas y unidades semánticas, leídas antes del cálculo."""

    def metric(self, owner: UUID, revision: UUID) -> MetricRevision: ...
    def units(
        self, owner: UUID, semantic_revision: UUID
    ) -> dict[UUID, tuple[str | None, str | None]]: ...


class AnalyticsQueryStep:
    output_kind: ArtifactKind = "analysis_result"
    transforms_data = False

    def __init__(self, objects: ObjectStore, root: Path, sources: MetricSource | None) -> None:
        self.objects, self.root, self.sources = objects, root, sources
        self.prepared: dict[tuple[UUID, str], list[dict[str, Any]]] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        """Lee las revisiones exactas y la unidad/moneda de la revisión semántica fijada antes de
        cerrar la transacción de metadatos (el cálculo no abre transacciones)."""
        if self.sources is None:
            raise ApplicationError("UNSUPPORTED_OPERATION", "Análisis no disponible.", 409)
        assert lease.execution.plan
        parameters = query_parameters(step)
        semantic = lease.execution.plan.content.get("semantic_ref")
        units = self.sources.units(lease.owner_id, UUID(semantic["id"])) if semantic else {}
        metrics = []
        for reference in parameters.metrics:
            revision = self.sources.metric(lease.owner_id, reference.revision_id)
            if revision.content_sha256 != reference.content_sha256:
                raise ApplicationError(
                    "METRIC_REFERENCE_MISMATCH", "La métrica no coincide con su hash.", 409
                )
            unit, currency = units.get(revision.content.measure_column_id, (None, None))
            second = revision.content.second_measure_column_id
            if second is not None:
                combined = product_unit((unit, currency), units.get(second, (None, None)))
                if combined is None:
                    raise ApplicationError(
                        "UNIT_MISMATCH", "sum_product no multiplica dos monedas.", 422
                    )
                unit, currency = combined
            metrics.append(
                {
                    "reference": reference.model_dump(mode="json"),
                    "revision": revision.revision,
                    "content": revision.content.model_dump(mode="json"),
                    "unit": unit,
                    "currency": currency,
                }
            )
        self.prepared[(lease.attempt_id, step.id)] = metrics

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "table":
            raise ApplicationError(
                "INPUT_KIND_MISMATCH", "El análisis requiere una entrada «table».", 409
            )
        plan = lease.execution.plan
        assert plan
        metrics = self.prepared.pop((lease.attempt_id, step.id), None)
        if metrics is None:
            raise ApplicationError("PROCESSING_ERROR", "Las métricas no se prepararon.", 409)
        parameters = query_parameters(step)
        table = plan.content["input"]
        scope = EvidenceScope(
            execution_id=lease.execution_id,
            step_id=step.id,
            input=BaseTable(
                version_id=table["version_id"],
                artifact_id=table["artifact_id"],
                artifact_sha256=table["artifact_sha256"],
            ),
            semantic_ref=plan.content.get("semantic_ref"),
            query_filters=parameters.filters,
            time_grain=parameters.time_grain,
            time_range=parameters.time_range,
        )
        files = run_isolated(
            self.root,
            MODULE,
            {"input.parquet": self.objects.read(source.content)},
            [
                "--mode",
                "query",
                "--operation-version",
                str(step.version),
                "--input",
                "{dir}/input.parquet",
                "--columns-json",
                json.dumps(source.columns or [], ensure_ascii=False),
                "--metrics-json",
                json.dumps(metrics, ensure_ascii=False),
                "--parameters-json",
                parameters.model_dump_json(),
                "--scope-json",
                scope.model_dump_json(),
                "--max-rows",
                str(plan.config.max_rows),
                "--max-columns",
                str(plan.config.max_columns),
            ],
            ["analysis.json"],
            min(timeout, plan.config.timeout_seconds),
        )
        report = files["analysis.json"]
        parsed: AnyAnalysisResult = (
            AnalysisResultV3.model_validate_json(report)
            if step.version == 3
            else AnalysisResultV2.model_validate_json(report)
            if step.version == 2
            else AnalysisResult.model_validate_json(report)
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/analysis.json", report)
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "analysis_result",
                    "analysis_result",
                    content,
                    "application/json",
                    parsed.row_count,
                    len(parsed.dimensions) + len(parsed.metrics),
                )
            ]
        )
