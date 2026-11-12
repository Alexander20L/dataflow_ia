"""Pestaña Dataset (Fase 22, ADR-039): une la cola, el motor de inspección, los datos del
original y las correcciones manuales sin acoplar los módulos entre sí.

Al publicarse una carga se encola un trabajo `inspection` (el primero de los de fondo) cuyo
input fija la tabla leída, el perfil y la calidad de la carga. Se calcula una sola vez sobre la
tabla completa y se guarda como artefacto: cambiar de subvista no recalcula nada. Las
correcciones del diccionario se aplican al leer y nunca tocan el archivo ni el cálculo.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.comprehension_job import source_key
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.executions.public import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Execution,
    Executions,
    Lease,
    PlanRevision,
    PlanStepSpec,
    ProcessingConfig,
    StepInput,
    StepResult,
)
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer, PolarsPreview
from dataflow.modules.ingestion.contracts import SourceFacts
from dataflow.modules.inspection.contracts import (
    AnnotationRequest,
    Inspection,
    InspectionScope,
    InspectionView,
)
from dataflow.modules.inspection.domain import dictionary, groups, validate_annotation
from dataflow.modules.inspection.engine import FileMeta, inspect
from dataflow.modules.inspection.infrastructure import SQLColumnAnnotations
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

STEP = "inspection.inspect"


def stored(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.id),
        "key": artifact.content.key,
        "sha256": artifact.content.sha256,
        "byte_size": artifact.content.byte_size,
    }


def reference(item: dict[str, Any]) -> StoredObject:
    return StoredObject(str(item["key"]), str(item["sha256"]), int(item["byte_size"]))


def enqueue_inspection(
    executions: Executions,
    datasets: Datasets,
    lease: Lease,
    artifacts: list[Artifact],
    config: ProcessingConfig,
) -> None:
    """Encola la inspección de la carga recién publicada (tabla, perfil y, si hay, calidad)."""
    run = lease.execution
    table = next((a for a in artifacts if a.kind == "table"), None)
    profile = next((a for a in artifacts if a.kind == "profile"), None)
    quality = next((a for a in artifacts if a.kind == "quality"), None)
    if run.plan is None or table is None or profile is None:
        return
    key = uuid5(lease.execution_id, "inspection@1")
    fingerprint = digest(
        "inspection_request",
        {
            "table_sha256": table.content.sha256,
            "profile_sha256": profile.content.sha256,
            "quality_sha256": quality.content.sha256 if quality else "",
            "operation": f"{STEP}@1",
        },
    )
    if executions.find_request(lease.owner_id, run.project_id, "inspection", key, fingerprint):
        return
    version = datasets.get(lease.owner_id, lease.version_id)
    steps = run.plan.content.get("steps", [])
    read: dict[str, Any] = next((s for s in steps if s.get("id") == "read"), {})
    content = {
        "objective": None,
        "input": {
            "kind": "inspection",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "file_name": version.file_name,
            "uploaded_at": version.created_at.isoformat(),
            "source_key": source_key(version.file_name, run.plan.content),
            "original": {
                "key": version.content.key,
                "sha256": version.content.sha256,
                "byte_size": version.content.byte_size,
            },
            "read_operation": str(read.get("operation") or ""),
            "read_parameters": read.get("parameters") or {},
            "selection_rule": (run.plan.content.get("source_selection") or {}).get("rule"),
            "origin": run.plan.content.get("source_origin"),
            "artifact_id": str(profile.id),
            "artifact_sha256": profile.content.sha256,
            "profile": stored(profile),
            "table": stored(table) | {"columns": table.columns or []},
            "quality": stored(quality) if quality else None,
        },
        "steps": [
            {
                "id": "inspect",
                "operation": STEP,
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {"rules": "dataset-inspection-v1"},
            }
        ],
        "config": config.model_dump(),
    }
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), lease.owner_id, datetime.now(UTC)
    )
    executions.enqueue_followup(
        lease.owner_id,
        run.project_id,
        lease.version_id,
        key,
        fingerprint,
        plan,
        str(lease.execution_id),
        profile.id,
        profile.content.sha256,
        kind="inspection",
    )


class InspectionInput:
    """Comprueba que la tabla, el perfil y la calidad fijados son los de la carga."""

    def __init__(
        self, datasets: Datasets, executions: Executions, projects: ProjectPermissions
    ) -> None:
        self.datasets, self.executions, self.projects = datasets, executions, projects

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        self.projects.require(run.owner_id, run.project_id, writable=True)
        version = self.datasets.get(run.owner_id, run.version_id)
        given = run.plan.content["input"]
        profile = self.executions.artifact(run.owner_id, run.input_artifact_id)
        table = self.executions.artifact(run.owner_id, UUID(given["table"]["artifact_id"]))
        quality = (
            self.executions.artifact(run.owner_id, UUID(given["quality"]["artifact_id"]))
            if given.get("quality")
            else None
        )
        if (
            profile.kind != "profile"
            or table.kind != "table"
            or profile.version_id != version.id
            or table.version_id != version.id
            or profile.execution_id != table.execution_id
            or str(version.id) != given.get("version_id")
            or version.content.sha256 != given.get("version_content_sha256")
            or profile.content.sha256 != run.input_artifact_sha256
            or profile.content != reference(given["profile"])
            or table.content != reference(given["table"])
            or (
                quality is not None
                and (
                    quality.kind != "quality"
                    or quality.execution_id != table.execution_id
                    or quality.content != reference(given["quality"])
                )
            )
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La tabla fijada para la inspección no coincide.", 409
            )
        return StepInput("inspection", profile.content, table.content.sha256)


def file_format(
    operation: str, origin: dict[str, Any] | None
) -> Literal["csv", "xlsx", "pdf", "sqlserver", "other"]:
    if origin and origin.get("kind") == "sqlserver":
        return "sqlserver"
    if operation == "ingestion.read_xlsx":
        return "xlsx"
    if operation == "ingestion.read_pdf":
        return "pdf"
    if operation == "ingestion.read_csv":
        return "csv"
    return "other"


class InspectionStep:
    output_kind: ArtifactKind = "inspection"
    transforms_data = False

    def __init__(self, objects: ObjectStore, analyzer: IsolatedAnalyzer | None) -> None:
        self.objects, self.analyzer = objects, analyzer

    def facts(
        self, lease: Lease, given: dict[str, Any], kind: str, timeout: float
    ) -> SourceFacts | None:
        """Datos del original leídos en el subproceso de ingesta. Si no se pueden obtener, la
        inspección sale sin ellos (lo dice en «Archivo»), nunca con datos inventados."""
        if self.analyzer is None or kind not in {"csv", "xlsx"}:
            return None
        parameters = dict(given.get("read_parameters") or {})
        original = self.objects.read(reference(given["original"]))
        request = {
            "format": kind,
            "encoding": parameters.get("encoding"),
            "separator": parameters.get("separator"),
            "sheet": parameters.get("sheet"),
            "table": parameters.get("table"),
            "header_row": parameters.get("header_row"),
        }
        plan = lease.execution.plan
        assert plan
        config = ProcessingConfig.model_validate(plan.content["config"])
        try:
            return self.analyzer.source_facts(original, request, config, timeout)
        except ApplicationError as error:
            return SourceFacts(
                format="other",
                size_bytes=len(original),
                problems=[f"No se pudieron leer los datos del original ({error.code})."],
            )

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "inspection":
            raise ApplicationError("INPUT_MISMATCH", "Entrada de inspección no válida.", 409)
        plan = lease.execution.plan
        assert plan
        given = plan.content["input"]
        profile = DatasetProfile.model_validate_json(self.objects.read(source.content))
        table = self.objects.read(reference(given["table"]))
        quality = (
            QualityReport.model_validate_json(self.objects.read(reference(given["quality"])))
            if given.get("quality")
            else None
        )
        kind = file_format(str(given.get("read_operation") or ""), given.get("origin"))
        origin = given.get("origin") or {}
        origin_note = (
            f"Tabla «{origin.get('table')}» copiada de SQL Server ({origin.get('rule')})."
            if origin.get("kind") == "sqlserver"
            else f"Tabla «{origin.get('table')}» extraída del PDF ({origin.get('rule')})."
            if origin.get("kind") == "pdf"
            else None
        )
        result: Inspection = inspect(
            table,
            [UUID(str(c["id"])) for c in given["table"].get("columns", [])],
            profile,
            quality,
            PolarsPreview().source_reading(table),
            self.facts(lease, given, kind, timeout),
            FileMeta(
                file_name=str(given["file_name"]),
                uploaded_at=datetime.fromisoformat(str(given["uploaded_at"])),
                sha256=str(given["version_content_sha256"]),
                format=kind,
                selection_rule=given.get("selection_rule"),
                origin=origin_note,
            ),
            InspectionScope(
                execution_id=lease.execution_id,
                version_id=lease.version_id,
                table_sha256=str(given["table"]["sha256"]),
                profile_sha256=source.content.sha256,
                computed_at=datetime.now(UTC),
            ),
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/inspection.json", result.model_dump_json().encode())
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "inspection",
                    "inspection",
                    content,
                    "application/json",
                    result.summary.rows,
                    result.summary.columns,
                )
            ]
        )


class InspectionAccess:
    """Lectura de la inspección y registro de correcciones; nunca recalcula."""

    def __init__(
        self,
        db: Session,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        annotations: SQLColumnAnnotations,
    ) -> None:
        self.db, self.datasets, self.executions = db, datasets, executions
        self.objects, self.annotations = objects, annotations

    def run(self, owner: UUID, version: UUID) -> Execution | None:
        self.datasets.get(owner, version)
        runs = [r for r in self.executions.for_version(owner, version) if r.kind == "inspection"]
        return runs[0] if runs else None

    def result(self, owner: UUID, run: Execution) -> Inspection | None:
        if run.state != "succeeded":
            return None
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "inspection"
        )
        result = Inspection.model_validate_json(self.objects.read(artifact.content))
        if result.scope.execution_id != run.id:
            raise ApplicationError(
                "INTEGRITY_ERROR", "La inspección no corresponde a esta versión.", 409
            )
        return result

    def importing(self, owner: UUID, version: UUID) -> Execution | None:
        """La carga de la versión mientras no ha terminado (aún no hay inspección encolada)."""
        runs = self.executions.for_version(owner, version)
        return next(
            (r for r in runs if r.kind == "csv_import" and r.state in {"queued", "running"}),
            None,
        )

    def view(self, owner: UUID, version: UUID) -> InspectionView:
        run = self.run(owner, version)
        if run is None:
            if self.importing(owner, version) is not None:
                return InspectionView(state="queued")
            return InspectionView(
                state="unavailable",
                reason="Esta versión se procesó antes de la pestaña Dataset (Fase 22) o su "
                "carga no terminó: sube el archivo de nuevo para inspeccionarlo.",
            )
        if run.state in {"queued", "running"}:
            return InspectionView(state=run.state, execution_id=run.id)
        result = self.result(owner, run)
        if result is None:
            return InspectionView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        assert run.plan
        source = str(run.plan.content["input"]["source_key"])
        entries = dictionary(
            result, self.annotations.for_source(owner, run.project_id, source), version
        )
        return InspectionView(
            state="ready",
            execution_id=run.id,
            inspection=result,
            dictionary=entries,
            groups=groups(entries),
        )

    def annotate(self, owner: UUID, version: UUID, request: AnnotationRequest) -> InspectionView:
        """Corrección opcional: se guarda como metadato de la fuente; no recalcula nada."""
        run = self.run(owner, version)
        result = self.result(owner, run) if run else None
        if run is None or result is None:
            raise ApplicationError(
                "INSPECTION_NOT_READY", "La inspección todavía no está lista.", 409
            )
        column = next((c for c in result.columns if c.id == request.column_id), None)
        if column is None:
            raise ApplicationError("UNKNOWN_COLUMN", "La columna no existe en esta versión.", 404)
        validate_annotation(request, column)
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        assert run.plan
        self.annotations.add(
            owner,
            run.project_id,
            version,
            str(run.plan.content["input"]["source_key"]),
            column.name,
            request,
        )
        self.db.commit()
        return self.view(owner, version)
