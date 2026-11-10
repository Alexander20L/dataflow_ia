"""Entrega (Fase 17, ADR-034): informe automático en PDF y progreso por etapas.

Al publicarse una investigación se encola un trabajo `automatic_report` cuyo input fija la
investigación, el análisis y la calidad de esa carga (ids, claves y hashes). El trabajo sólo
reordena lo publicado (`delivery.report@1`); no calcula cifras ni llama a la IA.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from dataflow.modules.analytics.contracts import AutomaticAnalysis
from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.curation.public import SQLFindingFeedback
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.delivery.contracts import (
    Dashboard,
    Progress,
    ReportSource,
    ReportView,
    RunSummary,
)
from dataflow.modules.delivery.public import build_report, progress, render_pdf
from dataflow.modules.executions.public import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Executions,
    Lease,
    PlanRevision,
    PlanStepSpec,
    ProcessingConfig,
    StepInput,
    StepResult,
)
from dataflow.modules.exploration.contracts import Exploration
from dataflow.modules.ingestion.contracts import SourceReview
from dataflow.modules.investigation.contracts import Investigation
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.quality.contracts import QualityReport
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

STEP = "delivery.report"


def stored(item: Artifact) -> dict[str, object]:
    return {
        "artifact_id": str(item.id),
        "key": item.content.key,
        "sha256": item.content.sha256,
        "byte_size": item.content.byte_size,
    }


def enqueue_report(
    executions: Executions,
    datasets: Datasets,
    lease: Lease,
    investigation: Artifact,
    config: ProcessingConfig,
    review: SourceReview | None = None,
) -> None:
    """Encola el informe de una investigación recién publicada (misma transacción). `review`
    (Fase 18): lectura del archivo y cambios de estructura, fijados en el plan."""
    run = lease.execution
    assert run.plan and run.input_artifact_id
    analysis = executions.artifact(lease.owner_id, run.input_artifact_id)
    quality = next(
        (
            a
            for a in executions.artifacts(lease.owner_id, analysis.execution_id)
            if a.kind == "quality"
        ),
        None,
    )
    version = datasets.get(lease.owner_id, lease.version_id)
    # Fase 19: la comprensión de la carga, si ya terminó (se encola antes que la investigación).
    comprehension = next(
        (
            a
            for run in executions.for_version(lease.owner_id, lease.version_id)
            if run.kind == "comprehension" and run.state == "succeeded"
            for a in executions.artifacts(lease.owner_id, run.id)
            if a.kind == "comprehension"
        ),
        None,
    )
    key = uuid5(lease.execution_id, "automatic-report@1")
    fingerprint = digest(
        "automatic_report_request",
        {
            "investigation_id": str(investigation.id),
            "investigation_sha256": investigation.content.sha256,
            "analysis_sha256": analysis.content.sha256,
            "quality_sha256": quality.content.sha256 if quality else None,
            "operation": f"{STEP}@1",
            **({"review": review.model_dump(mode="json")} if review else {}),
            **({"comprehension_sha256": comprehension.content.sha256} if comprehension else {}),
        },
    )
    if executions.find_request(
        lease.owner_id, run.project_id, "automatic_report", key, fingerprint
    ):
        return
    content = {
        "objective": None,
        "input": {
            "kind": "investigation",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "version_number": version.number,
            "file_name": version.file_name,
            "artifact_id": str(investigation.id),
            "artifact_sha256": investigation.content.sha256,
            "producer_execution_id": str(investigation.execution_id),
            "analysis": stored(analysis),
            "analysis_execution_id": str(analysis.execution_id),
            "quality": stored(quality) if quality else None,
            **({"review": review.model_dump(mode="json")} if review else {}),
            **({"comprehension": stored(comprehension)} if comprehension else {}),
        },
        "steps": [
            {
                "id": "report",
                "operation": STEP,
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {},
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
        investigation.id,
        investigation.content.sha256,
        kind="automatic_report",
    )


def reference(item: dict[str, object]) -> StoredObject:
    return StoredObject(str(item["key"]), str(item["sha256"]), int(str(item["byte_size"])))


class ReportInput:
    """Comprueba que la investigación, el análisis y la calidad fijados son los de la carga."""

    def __init__(
        self, datasets: Datasets, executions: Executions, projects: ProjectPermissions
    ) -> None:
        self.datasets, self.executions, self.projects = datasets, executions, projects

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        self.projects.require(run.owner_id, run.project_id, writable=True)
        version = self.datasets.get(run.owner_id, run.version_id)
        source = run.plan.content["input"]
        investigation = self.executions.artifact(run.owner_id, run.input_artifact_id)
        analysis = self.executions.artifact(
            run.owner_id, UUID(str(source["analysis"]["artifact_id"]))
        )
        quality = (
            self.executions.artifact(run.owner_id, UUID(str(source["quality"]["artifact_id"])))
            if source.get("quality")
            else None
        )
        if (
            investigation.kind != "investigation"
            or analysis.kind != "automatic_analysis"
            or (quality is not None and quality.kind != "quality")
            or investigation.version_id != version.id
            or analysis.version_id != version.id
            or str(version.id) != source.get("version_id")
            or version.content.sha256 != source.get("version_content_sha256")
            or str(investigation.id) != source.get("artifact_id")
            or investigation.content.sha256 != source.get("artifact_sha256")
            or investigation.content.sha256 != run.input_artifact_sha256
            or str(investigation.execution_id) != source.get("producer_execution_id")
            or analysis.content != reference(source["analysis"])
            or (quality is not None and quality.content != reference(source["quality"]))
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La investigación fijada para el informe no coincide.", 409
            )
        return StepInput("investigation", investigation.content, analysis.content.sha256)


class ReportStep:
    output_kind: ArtifactKind = "report_pdf"
    transforms_data = False

    def __init__(
        self,
        objects: ObjectStore,
        executions: Executions,
        feedback: SQLFindingFeedback | None = None,
    ) -> None:
        self.objects, self.executions, self.feedback = objects, executions, feedback

    def dashboard(self, lease: Lease) -> tuple[Dashboard, str] | None:
        """Fase 21: el dashboard terminado de la versión (se reclama antes que el informe)."""
        for run in self.executions.for_version(lease.owner_id, lease.version_id):
            if run.kind == "dashboard" and run.state == "succeeded":
                artifact = next(
                    a
                    for a in self.executions.artifacts(lease.owner_id, run.id)
                    if a.kind == "dashboard"
                )
                return (
                    Dashboard.model_validate_json(self.objects.read(artifact.content)),
                    artifact.content.sha256,
                )
        return None

    def marks(self, lease: Lease) -> tuple[dict[str, str], str | None]:
        """Fase 21: marcas «sí va / no va» vigentes al generar el informe y su hash."""
        if self.feedback is None:
            return {}, None
        found = self.feedback.for_version(lease.owner_id, lease.version_id)
        if not found:
            return {}, None
        marks = sorted([f.item, f.verdict] for f in found)
        return {f.item: f.verdict for f in found}, digest("finding_feedback", {"marks": marks})

    def exploration(self, lease: Lease) -> tuple[Exploration, str] | None:
        """Fase 20: la exploración terminada de la versión (se reclama antes que el informe)."""
        for run in self.executions.for_version(lease.owner_id, lease.version_id):
            if run.kind == "exploration" and run.state == "succeeded":
                artifact = next(
                    a
                    for a in self.executions.artifacts(lease.owner_id, run.id)
                    if a.kind == "exploration"
                )
                return (
                    Exploration.model_validate_json(self.objects.read(artifact.content)),
                    artifact.content.sha256,
                )
        return None

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        plan = lease.execution.plan
        if source.kind != "investigation" or plan is None:
            raise ApplicationError("INPUT_MISMATCH", "El informe necesita una investigación.", 409)
        given = plan.content["input"]
        investigation = Investigation.model_validate_json(self.objects.read(source.content))
        analysis_ref = reference(given["analysis"])
        analysis = AutomaticAnalysis.model_validate_json(self.objects.read(analysis_ref))
        if (
            investigation.scope.analysis_sha256 != analysis_ref.sha256
            or investigation.scope.version_id != lease.version_id
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La investigación no es la de este análisis.", 409
            )
        quality = (
            QualityReport.model_validate_json(self.objects.read(reference(given["quality"])))
            if given.get("quality")
            else None
        )
        explored = self.exploration(lease)
        designed = self.dashboard(lease)
        verdicts, marks_sha256 = self.marks(lease) if designed else ({}, None)
        document = build_report(
            ReportSource(
                project_id=lease.execution.project_id,
                version_id=lease.version_id,
                version_number=int(given["version_number"]),
                file_name=str(given["file_name"]),
                analysis_execution_id=UUID(str(given["analysis_execution_id"])),
                analysis_sha256=analysis_ref.sha256,
                investigation_execution_id=investigation.scope.execution_id,
                investigation_sha256=source.content.sha256,
                quality_sha256=str(given["quality"]["sha256"]) if given.get("quality") else None,
                exploration_sha256=explored[1] if explored else None,
                dashboard_sha256=designed[1] if designed else None,
                feedback_sha256=marks_sha256,
            ),
            analysis,
            investigation,
            quality,
            datetime.now(UTC).replace(microsecond=0),
            SourceReview.model_validate(given["review"]) if given.get("review") else None,
            Comprehension.model_validate_json(self.objects.read(reference(given["comprehension"])))
            if given.get("comprehension")
            else None,
            explored[0] if explored else None,
            designed[0] if designed else None,
            verdicts,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/report.pdf", render_pdf(document))
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "report_pdf",
                    "report_pdf",
                    content,
                    "application/pdf",
                    len(document.evidence_ids),
                    len(document.sections),
                )
            ]
        )


def report_name(file_name: str, number: int) -> str:
    stem = file_name.rsplit(".", 1)[0] or "datos"
    return f"informe-{stem}-v{number}.pdf"


class DeliveryAccess:
    """Lectura del informe y del progreso de una versión; nunca recalcula."""

    def __init__(self, datasets: Datasets, executions: Executions, objects: ObjectStore) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects

    def progress(self, owner: UUID, version: UUID) -> Progress:
        self.datasets.get(owner, version)
        runs = [
            RunSummary(
                id=run.id,
                kind=run.kind,
                state=run.state,
                error_code=run.error_code,
                finished_at=run.finished_at,
            )
            for run in self.executions.for_version(owner, version)
        ]
        return progress(version, runs)

    def ready(self, owner: UUID, version: UUID) -> tuple[ReportView, Artifact | None]:
        item = self.datasets.get(owner, version)
        runs = [
            r for r in self.executions.for_version(owner, version) if r.kind == "automatic_report"
        ]
        if not runs:
            raise ApplicationError(
                "REPORT_NOT_AVAILABLE",
                "Esta versión no tiene informe automático: se procesó antes de la Fase 17 o "
                "su investigación no terminó.",
                404,
            )
        # Fase 21: mientras se genera una versión nueva (tras una marca) se sirve la última
        # terminada e indica que se está actualizando.
        newest = runs[0]
        done = next((r for r in runs if r.state == "succeeded"), None)
        updating = newest.state in {"queued", "running"} and done is not None
        run = done if updating and done is not None else newest
        if run.state in {"queued", "running"}:
            return ReportView(state=run.state, execution_id=run.id), None
        if run.state != "succeeded":
            return (
                ReportView(
                    state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
                ),
                None,
            )
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "report_pdf"
        )
        return (
            ReportView(
                state="ready",
                execution_id=run.id,
                file_name=report_name(item.file_name, item.number),
                byte_size=artifact.content.byte_size,
                sha256=artifact.content.sha256,
                generated_at=run.finished_at,
                evidence_count=artifact.row_count,
                updating=updating,
            ),
            artifact,
        )

    def report(self, owner: UUID, version: UUID) -> ReportView:
        return self.ready(owner, version)[0]

    def pdf(self, owner: UUID, version: UUID) -> tuple[bytes, str]:
        view, artifact = self.ready(owner, version)
        if artifact is None or view.file_name is None:
            raise ApplicationError("REPORT_NOT_READY", "El informe todavía no está listo.", 409)
        return self.objects.read(artifact.content), view.file_name
