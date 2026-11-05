import io
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

import polars as pl

from dataflow.modules.datasets.contracts import StoredObject
from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import (
    ArtifactKind,
    ArtifactOutput,
    Executions,
    Lease,
    PlanStepSpec,
    StepInput,
    StepResult,
)
from dataflow.modules.ingestion.application import Analyzer, ProjectAccess
from dataflow.modules.ingestion.contracts import ReadCsvParameters
from dataflow.modules.quality.contracts import QualityParameters
from dataflow.modules.understanding.contracts import ProfileParameters
from dataflow.modules.understanding.public import SemanticReference, SemanticService, TableReference
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class SourceInputResolver:
    """Input `source`: el original de la versión fijada en el plan."""

    def __init__(self, datasets: Datasets, projects: ProjectAccess) -> None:
        self.datasets, self.projects = datasets, projects

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan
        version = self.datasets.get(run.owner_id, run.version_id)
        self.projects.require(run.owner_id, run.project_id)
        input_ref = run.plan.content["input"]
        if (
            input_ref["version_id"] != str(version.id)
            or input_ref["version_content_sha256"] != version.content.sha256
        ):
            raise ApplicationError("INPUT_MISMATCH", "La versión fijada no coincide.", 409)
        return StepInput("source", version.content, version.content.sha256)


class TableInputResolver:
    """Input `table`: representación publicada exacta y, si existe, su revisión semántica."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        projects: ProjectAccess,
        semantics: SemanticService | None = None,
    ) -> None:
        self.datasets, self.executions = datasets, executions
        self.projects, self.semantics = projects, semantics

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        version = self.datasets.get(run.owner_id, run.version_id)
        self.projects.require(run.owner_id, run.project_id)
        artifact = self.executions.artifact(run.owner_id, run.input_artifact_id)
        input_ref = run.plan.content["input"]
        if (
            input_ref.get("kind") != "table"
            or input_ref.get("version_id") != str(version.id)
            or artifact.kind != "table"
            or artifact.version_id != version.id
            or artifact.content.sha256 != run.input_artifact_sha256
            or input_ref.get("artifact_id") != str(artifact.id)
            or input_ref.get("artifact_sha256") != artifact.content.sha256
            or input_ref["version_content_sha256"] != version.content.sha256
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La tabla fijada no coincide con el plan.", 409
            )
        if run.plan.content.get("semantic_ref") is not None:
            if not self.semantics:
                raise ApplicationError(
                    "SEMANTICS_UNAVAILABLE", "No se puede verificar la revisión semántica.", 409
                )
            self.semantics.resolve_for_table(
                run.owner_id,
                SemanticReference.model_validate(run.plan.content["semantic_ref"]),
                TableReference(
                    version_id=version.id,
                    version_content_sha256=version.content.sha256,
                    artifact_id=artifact.id,
                    artifact_sha256=artifact.content.sha256,
                ),
            )
        # Las tablas publicadas conservan "," como separador de procedencia (contrato 0.4/0.5).
        return StepInput("table", artifact.content, version.content.sha256)


class AnalyzerStep:
    output_kind: ArtifactKind

    def __init__(self, objects: ObjectStore, analyzer: Analyzer) -> None:
        self.objects, self.analyzer = objects, analyzer

    def require(self, source: StepInput, kind: Literal["source", "table"]) -> None:
        if source.kind != kind:
            raise ApplicationError(
                "INPUT_KIND_MISMATCH", f"La operación requiere una entrada «{kind}».", 409
            )

    def put(self, lease: Lease, step: PlanStepSpec, name: str, content: bytes) -> StoredObject:
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        return self.objects.put(f"{prefix}/{name}", content)


class ReadCsvStep(AnalyzerStep):
    """ingestion.read_csv@1: fuente → tabla."""

    output_kind: ArtifactKind = "table"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "source")
        assert lease.execution.plan
        parameters = ReadCsvParameters.model_validate(step.parameters)
        result = self.analyzer.read(
            self.objects.read(source.content),
            parameters.separator,
            lease.execution.plan.config,
            timeout,
        )
        if result.source_sha256 != source.source_sha256:
            raise ApplicationError("INTEGRITY_ERROR", "La salida no corresponde al original.", 409)
        table = self.put(lease, step, "data.parquet", result.parquet)
        columns, logical_hash = table_metadata(lease.version_id, result.parquet)
        output = ArtifactOutput(
            uuid4(),
            step.id,
            "table",
            "table",
            table,
            "application/vnd.apache.parquet",
            result.row_count,
            result.column_count,
            columns,
            logical_hash,
        )
        return StepResult(
            [output], StepInput("table", table, source.source_sha256, result.separator)
        )


class ProfileStep(AnalyzerStep):
    """understanding.profile@1: tabla → perfil."""

    output_kind: ArtifactKind = "profile"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "table")
        assert lease.execution.plan
        ProfileParameters.model_validate(step.parameters)
        profile = self.analyzer.profile(
            self.objects.read(source.content),
            source.separator,
            source.source_sha256,
            lease.execution.plan.config,
            timeout,
        )
        if profile.source_sha256 != source.source_sha256:
            raise ApplicationError("INTEGRITY_ERROR", "La salida no corresponde al original.", 409)
        content = self.put(lease, step, "profile.json", profile.model_dump_json().encode())
        output = ArtifactOutput(
            uuid4(),
            step.id,
            "profile",
            "profile",
            content,
            "application/json",
            profile.row_count,
            profile.column_count,
        )
        return StepResult([output])


class QualityStep(AnalyzerStep):
    """quality.evaluate@1: tabla → calidad."""

    output_kind: ArtifactKind = "quality"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "table")
        assert lease.execution.plan
        QualityParameters.model_validate(step.parameters)
        quality = self.analyzer.quality(
            self.objects.read(source.content), lease.execution.plan.config, timeout
        )
        content = self.put(lease, step, "quality.json", quality.model_dump_json().encode())
        output = ArtifactOutput(
            uuid4(),
            step.id,
            "quality",
            "quality",
            content,
            "application/json",
            quality.row_count,
            quality.cell_count // quality.row_count,
        )
        return StepResult([output])


def table_metadata(version_id: UUID, content: bytes) -> tuple[list[dict[str, Any]], str]:
    frame = pl.read_parquet(io.BytesIO(content))
    columns = [
        {
            "id": str(uuid5(version_id, f"{index}/{name}")),
            "name": name,
            "ordinal": index,
            "technical_type": "string",
            "type_parameters": {},
            "nullable": True,
        }
        for index, name in enumerate(frame.columns)
    ]
    return columns, digest(
        "table", {"columns": columns, "rows": [list(row) for row in frame.iter_rows()]}
    )
