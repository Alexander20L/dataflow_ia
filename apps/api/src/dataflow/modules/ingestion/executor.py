import io
from typing import Any, Literal, Protocol
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
from dataflow.modules.ingestion.application import Analyzer, ProjectAccess, ReadOutput
from dataflow.modules.ingestion.contracts import ReadCsvParameters, ReadXlsxParameters
from dataflow.modules.quality.contracts import AnalyticalQualityParameters, QualityParameters
from dataflow.modules.quality.public import (
    QualityRulesParameters,
    QualityRulesReport,
    RulesetReference,
    RulesetRevision,
)
from dataflow.modules.understanding.contracts import (
    AnalyticalProfileParameters,
    AutomaticProfileParameters,
    InterpretedProfileParameters,
    ProfileParameters,
    profile_json,
)
from dataflow.modules.understanding.public import SemanticReference, SemanticService, TableReference
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import frame_types, table_logical_sha256


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
        return StepInput(
            "table", artifact.content, version.content.sha256, columns=artifact.columns
        )


class AnalyzerStep:
    output_kind: ArtifactKind
    transforms_data = False

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
        return publish_read(self, lease, step, source, result)


class ReadXlsxStep(AnalyzerStep):
    """ingestion.read_xlsx@1 (Fase 12A): libro original → tabla de la hoja o tabla elegida."""

    output_kind: ArtifactKind = "table"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "source")
        assert lease.execution.plan
        result = self.analyzer.read_xlsx(
            self.objects.read(source.content),
            ReadXlsxParameters.model_validate(step.parameters),
            lease.execution.plan.config,
            timeout,
        )
        return publish_read(self, lease, step, source, result)


def publish_read(
    reader: AnalyzerStep, lease: Lease, step: PlanStepSpec, source: StepInput, result: ReadOutput
) -> StepResult:
    """Tabla leída de un original: mismo artefacto para CSV y XLSX (Fase 12, principio común)."""
    if result.source_sha256 != source.source_sha256:
        raise ApplicationError("INTEGRITY_ERROR", "La salida no corresponde al original.", 409)
    table = reader.put(lease, step, "data.parquet", result.parquet)
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
    return StepResult([output], StepInput("table", table, source.source_sha256, result.separator))


class ProfileStep(AnalyzerStep):
    """understanding.profile@1–@4: tabla → perfil; dashboard desde @2, interpretación v1 en
    @3 e interpretación analítica con dashboard por medidas en @4."""

    output_kind: ArtifactKind = "profile"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "table")
        assert lease.execution.plan
        if step.version == 4:
            AnalyticalProfileParameters.model_validate(step.parameters)
        elif step.version == 3:
            InterpretedProfileParameters.model_validate(step.parameters)
        elif step.version == 2:
            AutomaticProfileParameters.model_validate(step.parameters)
        else:
            ProfileParameters.model_validate(step.parameters)
        profile = self.analyzer.profile(
            self.objects.read(source.content),
            source.separator,
            source.source_sha256,
            lease.execution.plan.config,
            timeout,
            include_overview=step.version == 2,
            include_interpretation=step.version == 3,
            include_analysis=step.version == 4,
        )
        if profile.source_sha256 != source.source_sha256:
            raise ApplicationError("INTEGRITY_ERROR", "La salida no corresponde al original.", 409)
        content = self.put(
            lease, step, "profile.json", profile_json(profile, step.version).encode()
        )
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
    """quality.evaluate@1: tabla → calidad; @3 añade los hallazgos automatic-quality-v1."""

    output_kind: ArtifactKind = "quality"

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "table")
        assert lease.execution.plan
        if step.version == 3:
            AnalyticalQualityParameters.model_validate(step.parameters)
        else:
            QualityParameters.model_validate(step.parameters)
        quality = self.analyzer.quality(
            self.objects.read(source.content),
            lease.execution.plan.config,
            timeout,
            analytical=step.version == 3,
        )
        content = self.put(lease, step, "quality.json", quality.serialized(step.version).encode())
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


class RulesetSource(Protocol):
    """Revisiones de reglas (inmutables) del propietario; implementado por quality."""

    def revision(self, owner: UUID, revision: UUID) -> RulesetRevision: ...


class QualityRulesStep(AnalyzerStep):
    """quality.evaluate@2: tabla → informe csv-quality-v2 con la revisión exacta de reglas."""

    output_kind: ArtifactKind = "quality_rules"

    def __init__(
        self, objects: ObjectStore, analyzer: Analyzer, rulesets: RulesetSource | None
    ) -> None:
        super().__init__(objects, analyzer)
        self.rulesets = rulesets
        self.prepared: dict[tuple[UUID, str], RulesetRevision] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        """Lee la revisión antes de cerrar la transacción de metadatos (no durante el cálculo)."""
        if self.rulesets is None:
            raise ApplicationError("UNSUPPORTED_OPERATION", "Reglas no disponibles.", 409)
        parameters = QualityRulesParameters.model_validate(step.parameters)
        revision = self.rulesets.revision(lease.owner_id, parameters.ruleset_revision_id)
        if revision.content_sha256 != parameters.ruleset_sha256:
            raise ApplicationError(
                "QUALITY_RULESET_MISMATCH", "La revisión de reglas no coincide con su hash.", 409
            )
        self.prepared[(lease.attempt_id, step.id)] = revision

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        self.require(source, "table")
        assert lease.execution.plan
        revision = self.prepared.pop((lease.attempt_id, step.id), None)
        if revision is None:
            raise ApplicationError("PROCESSING_ERROR", "Las reglas no se prepararon.", 409)
        report = self.analyzer.quality_rules(
            self.objects.read(source.content),
            source.columns or [],
            [rule.model_dump(mode="json") for rule in revision.content.rules],
            RulesetReference(
                id=revision.id, revision=revision.revision, content_sha256=revision.content_sha256
            ).model_dump(mode="json"),
            lease.execution.plan.config,
            timeout,
        )
        parsed = QualityRulesReport.model_validate_json(report)
        content = self.put(lease, step, "quality_rules.json", report)
        output = ArtifactOutput(
            uuid4(),
            step.id,
            "quality_rules",
            "quality_rules",
            content,
            "application/json",
            parsed.row_count,
            len(source.columns or []),
        )
        return StepResult([output])


def table_metadata(version_id: UUID, content: bytes) -> tuple[list[dict[str, Any]], str]:
    frame = pl.read_parquet(io.BytesIO(content))
    columns = [
        {
            "id": str(uuid5(version_id, f"{index}/{name}")),
            "name": name,
            "ordinal": index,
            "technical_type": data_type,
            "type_parameters": parameters,
            "nullable": True,
        }
        for index, (name, (data_type, parameters)) in enumerate(
            zip(frame.columns, frame_types(frame), strict=True)
        )
    ]
    return columns, table_logical_sha256(columns, frame)
