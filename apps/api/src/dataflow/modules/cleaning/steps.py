"""Ejecutores de las operaciones cleaning.* y finalizadores de vista previa y aplicación.

Los pasos encadenan tablas intermedias bajo el prefijo privado del intento (no se registran ni
se publican). El finalizador calcula el efecto sobre el dataset completo; sólo la aplicación
publica la tabla final, y únicamente si su efecto coincide con el aprobado.
"""

import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from dataflow.modules.cleaning.contracts import (
    ApprovalSource,
    ApprovedEffect,
    CastParameters,
    DeduplicateParameters,
    EffectManifest,
    FilterRowsParameters,
    NormalizeNullTokensParameters,
    TrimWhitespaceParameters,
    derived_version_id,
)
from dataflow.modules.cleaning.domain import (
    check_counts,
    effect_sha256,
    require_same_effect,
    require_valid_approval,
)
from dataflow.modules.cleaning.engine import EffectResult, IsolatedCleaner
from dataflow.modules.datasets.public import ObjectStore, StoredObject
from dataflow.modules.executions.public import (
    ArtifactKind,
    ArtifactOutput,
    Lease,
    PlanStepSpec,
    StepInput,
    StepResult,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

PARQUET = "application/vnd.apache.parquet"


def prefix(lease: Lease) -> str:
    return f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}"


def column_names(source: StepInput, ids: list[UUID]) -> list[str]:
    names = {str(column["id"]): str(column["name"]) for column in source.columns or []}
    missing = [str(column) for column in ids if str(column) not in names]
    if not source.columns or missing:
        raise ApplicationError(
            "UNKNOWN_COLUMN", "Una columna del plan no existe en la tabla fijada.", 409
        )
    return [names[str(column)] for column in ids]


def parse[T: BaseModel](model: type[T], parameters: dict[str, Any]) -> T:
    # Parámetros inválidos no son un fallo transitorio: no se reintentan.
    try:
        return model.model_validate(parameters)
    except ValidationError as exc:
        raise ApplicationError(
            "INVALID_PARAMETERS", "Los parámetros del paso no son válidos.", 409
        ) from exc


def require_table(source: StepInput) -> None:
    if source.kind != "table":
        raise ApplicationError(
            "INPUT_KIND_MISMATCH", "La limpieza requiere una entrada «table».", 409
        )


class CleaningStep:
    output_kind: ArtifactKind = "table"
    transforms_data = True

    def __init__(self, objects: ObjectStore, cleaner: IsolatedCleaner) -> None:
        self.objects, self.cleaner = objects, cleaner

    def chained(
        self,
        lease: Lease,
        step: PlanStepSpec,
        source: StepInput,
        data: bytes,
        columns: list[dict[str, Any]] | None = None,
    ) -> StepResult:
        """Tabla intermedia privada del intento. `columns` es el esquema de salida si la
        operación cambia tipos; si no, se conserva el de la entrada."""
        reference = self.objects.put(f"{prefix(lease)}/steps/{step.id}/data.parquet", data)
        return StepResult(
            [],
            StepInput(
                "table",
                reference,
                source.source_sha256,
                source.separator,
                source.columns if columns is None else columns,
                lineage=True,
            ),
        )


class TrimWhitespaceStep(CleaningStep):
    """cleaning.trim_whitespace@1."""

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        require_table(source)
        assert lease.execution.plan
        parameters = parse(TrimWhitespaceParameters, step.parameters)
        data = self.cleaner.trim(
            self.objects.read(source.content),
            column_names(source, parameters.column_ids),
            source.lineage,
            lease.execution.plan.config,
            timeout,
        )
        return self.chained(lease, step, source, data)


class FilterRowsStep(CleaningStep):
    """cleaning.filter_rows@1."""

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        require_table(source)
        assert lease.execution.plan
        parameters = parse(FilterRowsParameters, step.parameters)
        data = self.cleaner.filter(
            self.objects.read(source.content),
            column_names(source, parameters.column_ids),
            parameters.predicate,
            parameters.match,
            source.lineage,
            lease.execution.plan.config,
            timeout,
        )
        return self.chained(lease, step, source, data)


class NormalizeNullTokensStep(CleaningStep):
    """cleaning.normalize_null_tokens@1."""

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        require_table(source)
        assert lease.execution.plan
        parameters = parse(NormalizeNullTokensParameters, step.parameters)
        data = self.cleaner.normalize_null_tokens(
            self.objects.read(source.content),
            column_names(source, parameters.column_ids),
            parameters.tokens,
            source.lineage,
            lease.execution.plan.config,
            timeout,
        )
        return self.chained(lease, step, source, data)


class DeduplicateStep(CleaningStep):
    """cleaning.deduplicate@1."""

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        require_table(source)
        assert lease.execution.plan
        parameters = parse(DeduplicateParameters, step.parameters)
        data = self.cleaner.deduplicate(
            self.objects.read(source.content),
            column_names(source, parameters.column_ids),
            [str(column) for column in parameters.column_ids],
            parameters.null_keys,
            source.lineage,
            lease.execution.plan.config,
            timeout,
        )
        return self.chained(lease, step, source, data)


class CastStep(CleaningStep):
    """cleaning.cast@1: convierte una columna de texto; el esquema de salida declara el tipo."""

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        require_table(source)
        assert lease.execution.plan
        parameters = parse(CastParameters, step.parameters)
        [name] = column_names(source, [parameters.column_id])
        data = self.cleaner.cast(
            self.objects.read(source.content),
            name,
            str(parameters.column_id),
            parameters.type,
            parameters.scale,
            source.lineage,
            lease.execution.plan.config,
            timeout,
        )
        columns = [
            {
                **column,
                "technical_type": parameters.type,
                "type_parameters": {"scale": parameters.scale}
                if parameters.type == "decimal"
                else {},
            }
            if str(column["id"]) == str(parameters.column_id)
            else column
            for column in source.columns or []
        ]
        return self.chained(lease, step, source, data, columns)


def build_manifest(
    lease: Lease, source: StepInput, final: StepInput, result: EffectResult
) -> EffectManifest:
    """Manifiesto sin IDs temporales ni fechas: plan, entrada, semántica, configuración,
    entorno, salida lógica, linaje y conteos exactos."""
    plan = lease.execution.plan
    assert plan
    check_counts(result.counts)
    return EffectManifest(
        plan={"revision_id": str(plan.id), "content_sha256": plan.content_sha256},
        input=plan.content["input"],
        semantic_ref=plan.content.get("semantic_ref"),
        config_sha256=str(lease.environment["config_sha256"]),
        environment_sha256=digest("environment", lease.environment),
        output={
            "columns": final.columns or [],
            "logical_content_sha256": result.logical_content_sha256,
        },
        row_lineage_sha256=result.row_lineage_sha256,
        counts=result.counts,
        rounded_cells=result.rounded_cells,
    )


class EffectFinalizer:
    def __init__(self, objects: ObjectStore, cleaner: IsolatedCleaner) -> None:
        self.objects, self.cleaner = objects, cleaner

    def effect(
        self, lease: Lease, source: StepInput, final: StepInput, timeout: float
    ) -> tuple[EffectResult, EffectManifest, str]:
        assert lease.execution.plan
        if not final.lineage:
            raise ApplicationError("EFFECT_INVALID", "La tabla final no conserva linaje.", 409)
        result = self.cleaner.effect(
            self.objects.read(source.content),
            self.objects.read(final.content),
            source.columns or [],
            final.columns or [],
            lease.execution.plan.config,
            timeout,
        )
        manifest = build_manifest(lease, source, final, result)
        return result, manifest, effect_sha256(manifest)

    def json_output(
        self, lease: Lease, step: str, kind: ArtifactKind, name: str, value: Any, rows: int
    ) -> ArtifactOutput:
        content = self.objects.put(
            f"{prefix(lease)}/{step}/{name}",
            json.dumps(value, ensure_ascii=False, sort_keys=True).encode(),
        )
        return ArtifactOutput(uuid4(), step, kind, kind, content, "application/json", rows, 0)

    def effect_outputs(
        self,
        lease: Lease,
        result: EffectResult,
        manifest: EffectManifest,
        sha: str,
    ) -> list[ArtifactOutput]:
        rows = result.counts.output_rows
        return [
            self.json_output(
                lease,
                "effect",
                "effect",
                "effect.json",
                {"effect_sha256": sha, "manifest": manifest.model_dump(mode="json")},
                rows,
            ),
            self.json_output(
                lease,
                "effect",
                "effect_samples",
                "samples.json",
                [sample.model_dump(mode="json") for sample in result.samples],
                rows,
            ),
        ]


class PreviewFinalizer(EffectFinalizer):
    """cleaning_preview: calcula el efecto completo; no publica tabla ni versión."""

    expected: set[tuple[str, ArtifactKind]] = {
        ("effect", "effect"),
        ("effect", "effect_samples"),
    }

    def prepare(self, lease: Lease) -> None:
        return None

    def finalize(
        self, lease: Lease, context: Any, source: StepInput, final: StepInput, timeout: float
    ) -> list[ArtifactOutput]:
        result, manifest, sha = self.effect(lease, source, final, timeout)
        return self.effect_outputs(lease, result, manifest, sha)


class ApplyFinalizer(EffectFinalizer):
    """cleaning_apply: recalcula el efecto, exige que coincida con el aprobado y prepara la
    tabla derivada y su linaje para la versión derivada (que se registra al publicar)."""

    expected: set[tuple[str, ArtifactKind]] = {
        ("effect", "effect"),
        ("effect", "effect_samples"),
        ("result", "table"),
        ("result", "row_lineage"),
    }

    def __init__(
        self, objects: ObjectStore, cleaner: IsolatedCleaner, approvals: ApprovalSource
    ) -> None:
        super().__init__(objects, cleaner)
        self.approvals = approvals

    def prepare(self, lease: Lease) -> ApprovedEffect:
        return require_valid_approval(self.approvals, lease)

    def finalize(
        self, lease: Lease, context: Any, source: StepInput, final: StepInput, timeout: float
    ) -> list[ArtifactOutput]:
        approved: ApprovedEffect = context
        result, manifest, sha = self.effect(lease, source, final, timeout)
        require_same_effect(approved.effect_sha256, sha)
        version = derived_version_id(lease.execution_id)
        columns = len(final.columns or [])
        table = self.put(lease, "table.parquet", result.table)
        lineage = self.put(lease, "row_lineage.parquet", result.lineage)
        rows = result.counts.output_rows
        return [
            *self.effect_outputs(lease, result, manifest, sha),
            ArtifactOutput(
                uuid4(),
                "result",
                "table",
                "table",
                table,
                PARQUET,
                rows,
                columns,
                final.columns,
                result.logical_content_sha256,
                version,
            ),
            ArtifactOutput(
                uuid4(),
                "result",
                "row_lineage",
                "row_lineage",
                lineage,
                PARQUET,
                rows,
                2,
                logical_content_sha256=result.row_lineage_sha256,
                version_id=version,
            ),
        ]

    def put(self, lease: Lease, name: str, content: bytes) -> StoredObject:
        return self.objects.put(f"{prefix(lease)}/result/{name}", content)
