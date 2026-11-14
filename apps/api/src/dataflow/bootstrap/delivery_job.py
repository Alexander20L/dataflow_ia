"""Entrega (Fase 17, ADR-034): informe automático en PDF y progreso por etapas.

Al publicarse una investigación se encola un trabajo `automatic_report` cuyo input fija la
investigación, el análisis y la calidad de esa carga (ids, claves y hashes). El trabajo sólo
reordena lo publicado (`delivery.report@1`); no calcula cifras ni llama a la IA.

Fase 27 (ADR-045): las cargas nuevas encolan el informe v2 (`delivery.report@2`) al publicarse
el dashboard. Su artefacto es el documento (`report_document`) y el PDF se dibuja de él al
descargarlo. La revisión humana (pendiente, aprobado, rechazado) se guarda como las marcas del
dashboard y una versión nueva del informe se genera cuando el usuario lo pide.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.dashboard_job import request_report_update
from dataflow.modules.analytics.contracts import AutomaticAnalysis
from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.comprehension.domain import with_user_meanings
from dataflow.modules.comprehension.infrastructure import SQLMeaningRepository
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.contracts import CallRecord
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.copilot.investigation import Figure
from dataflow.modules.copilot.report import (
    NARRATIVE_ID,
    NARRATIVE_VERSION,
    write_narrative,
)
from dataflow.modules.curation.public import SQLFindingFeedback
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.delivery.contracts import (
    Dashboard,
    Progress,
    ReportDocument,
    ReportHistory,
    ReportReview,
    ReportSource,
    ReportVersion,
    ReportView,
    ReviewRequest,
    RunSummary,
)
from dataflow.modules.delivery.public import (
    build_report,
    build_report_v2,
    principal_figures,
    progress,
    render_pdf,
    review_items,
    selection_digest_items,
)
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
from dataflow.modules.exploration.contracts import Exploration
from dataflow.modules.ingestion.contracts import SourceReview
from dataflow.modules.inspection.contracts import Inspection
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
        meanings: SQLMeaningRepository | None = None,
    ) -> None:
        self.objects, self.executions, self.feedback = objects, executions, feedback
        self.meanings = meanings

    def described(
        self, lease: Lease, comprehension: Comprehension
    ) -> tuple[Comprehension, str | None]:
        """Fase 24B: la comprensión con los significados vigentes del usuario (escritos,
        confirmados o marcados como desconocidos) y su hash; lo calculado no cambia."""
        if self.meanings is None:
            return comprehension, None
        run = next(
            (
                r
                for r in self.executions.for_version(lease.owner_id, lease.version_id)
                if r.id == comprehension.scope.execution_id
            ),
            None,
        )
        source = run.plan.content["input"].get("source_key") if run and run.plan else None
        if not source:
            return comprehension, None
        user = self.meanings.for_source(lease.owner_id, lease.execution.project_id, str(source))
        if not user:
            return comprehension, None
        applied = sorted(
            [column, text or "", confirmed, unknown]
            for column, (text, confirmed, unknown) in user.items()
        )
        return (
            comprehension.model_copy(
                update={"meanings": with_user_meanings(comprehension.meanings, user)}
            ),
            digest("column_meanings", {"meanings": applied}),
        )

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
        comprehension, meanings_sha256 = (
            self.described(
                lease,
                Comprehension.model_validate_json(
                    self.objects.read(reference(given["comprehension"]))
                ),
            )
            if given.get("comprehension")
            else (None, None)
        )
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
                meanings_sha256=meanings_sha256,
            ),
            analysis,
            investigation,
            quality,
            datetime.now(UTC).replace(microsecond=0),
            SourceReview.model_validate(given["review"]) if given.get("review") else None,
            comprehension,
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


# --- Fase 27 (ADR-045): informe v2 (`delivery.report@2`, `automatic-report-v2`) -------------

INPUT_V2: Final = "report_v2"  # tipo de entrada del plan (el dashboard ya usa «dashboard»)


def published_artifact(
    executions: Executions, owner: UUID, version: UUID, run_kind: str, kind: str
) -> Artifact | None:
    """Último artefacto `kind` de una ejecución `run_kind` terminada de la versión."""
    for run in executions.for_version(owner, version):
        if run.kind == run_kind and run.state == "succeeded":
            return next((a for a in executions.artifacts(owner, run.id) if a.kind == kind), None)
    return None


def enqueue_report_v2(
    executions: Executions,
    datasets: Datasets,
    lease: Lease,
    dashboard: Artifact,
    config: ProcessingConfig,
    review: SourceReview | None = None,
) -> None:
    """Encola la primera versión del informe v2 al publicarse el dashboard de una carga (Fase
    27: ya no espera a la investigación de la Fase 16)."""
    run = lease.execution
    analysis = published_artifact(
        executions, lease.owner_id, lease.version_id, "csv_import", "automatic_analysis"
    ) or published_artifact(
        executions, lease.owner_id, lease.version_id, "table_analysis", "automatic_analysis"
    )
    if analysis is None:
        return
    quality = next(
        (
            a
            for a in executions.artifacts(lease.owner_id, analysis.execution_id)
            if a.kind == "quality"
        ),
        None,
    )
    version = datasets.get(lease.owner_id, lease.version_id)
    given = run.plan.content["input"] if run.plan else {}
    key = uuid5(lease.execution_id, "automatic-report@2")
    fingerprint = digest(
        "automatic_report_request",
        {
            "dashboard_sha256": dashboard.content.sha256,
            "analysis_sha256": analysis.content.sha256,
            "operation": f"{STEP}@2",
        },
    )
    if executions.find_request(
        lease.owner_id, run.project_id, "automatic_report", key, fingerprint
    ):
        return
    content = {
        "objective": None,
        "input": {
            "kind": INPUT_V2,
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "version_number": version.number,
            "file_name": version.file_name,
            "artifact_id": str(dashboard.id),
            "artifact_sha256": dashboard.content.sha256,
            "producer_execution_id": str(dashboard.execution_id),
            "analysis": stored(analysis),
            "analysis_execution_id": str(analysis.execution_id),
            "quality": stored(quality) if quality else None,
            **({"comprehension": given["comprehension"]} if "comprehension" in given else {}),
            **({"review": review.model_dump(mode="json")} if review else {}),
            "trigger": "load",
        },
        "steps": [
            {
                "id": "report",
                "operation": STEP,
                "version": 2,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {},
            }
        ],
        # Llamada facturable (narrativa): un solo intento.
        "config": config.model_copy(update={"max_attempts": 1}).model_dump(),
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
        dashboard.id,
        dashboard.content.sha256,
        kind="automatic_report",
    )


class ReportInputV2:
    """Comprueba que el dashboard y el análisis fijados son los de la carga."""

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
        dashboard = self.executions.artifact(run.owner_id, run.input_artifact_id)
        analysis = self.executions.artifact(
            run.owner_id, UUID(str(source["analysis"]["artifact_id"]))
        )
        if (
            dashboard.kind != "dashboard"
            or analysis.kind != "automatic_analysis"
            or {dashboard.version_id, analysis.version_id} != {version.id}
            or str(version.id) != source.get("version_id")
            or version.content.sha256 != source.get("version_content_sha256")
            or dashboard.content.sha256 != run.input_artifact_sha256
            or analysis.content != reference(source["analysis"])
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "Lo fijado para el informe no coincide con la carga.", 409
            )
        return StepInput(INPUT_V2, dashboard.content, analysis.content.sha256)


class ReportStepV2(ReportStep):
    """`delivery.report@2`: arma el documento del informe v2 (sin cifras propias) y, si la IA
    está disponible, le pide el resumen, las conclusiones y las recomendaciones. El PDF se
    dibuja a partir del documento al descargarlo."""

    output_kind: ArtifactKind = "report_document"

    def __init__(
        self,
        objects: ObjectStore,
        executions: Executions,
        copilot: CopilotService,
        feedback: SQLFindingFeedback | None = None,
        meanings: SQLMeaningRepository | None = None,
    ) -> None:
        super().__init__(objects, executions, feedback, meanings)
        self.copilot = copilot
        self.prepared: dict[UUID, str | None] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        reason = None
        try:
            self.copilot.available(lease.owner_id, lease.execution.project_id)
        except ApplicationError as error:
            reason = (
                error.code
                if error.code != "COPILOT_UNAVAILABLE"
                else (self.copilot.config.unavailable or "disabled")
            )
        self.prepared[lease.attempt_id] = reason

    def inspection(self, lease: Lease) -> tuple[Inspection, str] | None:
        artifact = published_artifact(
            self.executions, lease.owner_id, lease.version_id, "inspection", "inspection"
        )
        if artifact is None:
            return None
        return (
            Inspection.model_validate_json(self.objects.read(artifact.content)),
            artifact.content.sha256,
        )

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        plan = lease.execution.plan
        if source.kind != INPUT_V2 or plan is None or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "El informe necesita su dashboard.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        given = plan.content["input"]
        analysis_ref = reference(given["analysis"])
        analysis = AutomaticAnalysis.model_validate_json(self.objects.read(analysis_ref))
        quality = (
            QualityReport.model_validate_json(self.objects.read(reference(given["quality"])))
            if given.get("quality")
            else None
        )
        explored = self.exploration(lease)
        designed = self.dashboard(lease)
        inspected = self.inspection(lease)
        verdicts, marks_sha256 = self.marks(lease)
        comprehension, meanings_sha256 = (
            self.described(
                lease,
                Comprehension.model_validate_json(
                    self.objects.read(reference(given["comprehension"]))
                ),
            )
            if given.get("comprehension")
            else (None, None)
        )
        exploration = explored[0] if explored else None
        dashboard = designed[0] if designed else None
        items = review_items(analysis, exploration, verdicts)
        narrative = None
        reason: str | None = unavailable or "disabled"
        calls: list[dict[str, object]] = []
        provider = self.copilot.provider
        if provider is not None and unavailable is None:
            findings, values = principal_figures(items, analysis, exploration, dashboard)
            indicator_ids = {i.evidence_id for i in dashboard.indicators} if dashboard else set()
            result_ids = (
                {f.evidence_id for r in exploration.results for row in r.rows for f in row.figures}
                if exploration
                else set()
            )
            figures = [
                Figure(
                    evidence_id=evidence,
                    label=label,
                    value=value,
                    unit=unit,
                    execution_id=(
                        dashboard.scope.execution_id
                        if dashboard is not None and evidence in indicator_ids
                        else exploration.scope.execution_id
                        if exploration is not None and evidence in result_ids
                        else analysis.scope.execution_id
                    ),
                )
                for evidence, label, value, unit in values
            ]
            narrative, call, error = write_narrative(
                provider, findings, figures, [], self.copilot.config.max_output_tokens
            )
            if call is not None:
                calls.append(call.model_dump(mode="json"))
            reason = error
        document = build_report_v2(
            ReportSource(
                project_id=lease.execution.project_id,
                version_id=lease.version_id,
                version_number=int(given["version_number"]),
                file_name=str(given["file_name"]),
                analysis_execution_id=UUID(str(given["analysis_execution_id"])),
                analysis_sha256=analysis_ref.sha256,
                quality_sha256=str(given["quality"]["sha256"]) if given.get("quality") else None,
                exploration_sha256=explored[1] if explored else None,
                dashboard_sha256=designed[1] if designed else None,
                feedback_sha256=marks_sha256,
                meanings_sha256=meanings_sha256,
                execution_id=lease.execution_id,
                exploration_execution_id=exploration.scope.execution_id if exploration else None,
                dashboard_execution_id=dashboard.scope.execution_id if dashboard else None,
                inspection_sha256=inspected[1] if inspected else None,
            ),
            datetime.now(UTC).replace(microsecond=0),
            analysis,
            quality,
            inspected[0] if inspected else None,
            comprehension,
            exploration,
            dashboard,
            verdicts,
            narrative,
            reason,
            SourceReview.model_validate(given["review"]) if given.get("review") else None,
            calls,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/report.json", document.model_dump_json().encode())
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "report_document",
                    "report_document",
                    content,
                    "application/json",
                    len(document.evidence_ids),
                    len(document.sections),
                )
            ]
        )


def record_report_calls(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    """Registra la llamada de la narrativa del informe v2 en el consumo de la IA."""
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    document = ReportDocument.model_validate_json(objects.read(output.content))
    if document.source.execution_id != lease.execution_id:
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "El informe no corresponde a su ejecución.", 409
        )
    repository = SQLCopilotRepository(db)
    for item in document.calls:
        call: dict[str, Any] = dict(item)
        repository.log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="report_narrative",
                provider=str(call["provider"]),
                model=str(call["model"]),
                parameters=dict(call["parameters"]),
                prompt_id=NARRATIVE_ID,
                prompt_version=NARRATIVE_VERSION,
                context_sha256=str(call["context_sha256"]),
                input_tokens=int(call["input_tokens"]),
                output_tokens=int(call["output_tokens"]),
                cache_read_tokens=int(call["cache_read_tokens"]),
                cache_write_tokens=int(call["cache_write_tokens"]),
                cost_usd=Decimal(str(call["cost_usd"])) if call.get("cost_usd") else None,
                latency_ms=int(call["latency_ms"]),
                outcome=str(call["outcome"]),  # type: ignore[arg-type]
                validation={
                    "report": str(lease.execution_id),
                    "narrative_by": document.narrative_by,
                },
                error_code=call.get("error_code"),
            )
        )


def report_name(file_name: str, number: int) -> str:
    stem = file_name.rsplit(".", 1)[0] or "datos"
    return f"informe-{stem}-v{number}.pdf"


class DeliveryAccess:
    """Lectura del informe y del progreso de una versión; nunca recalcula."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        db: Session | None = None,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.db = db

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
            # Fase 27: el informe se encola al publicarse el dashboard; mientras la cadena
            # anterior sigue en marcha, está en cola (no es un 404).
            if any(
                r.kind in {"comprehension", "exploration", "dashboard"}
                and r.state in {"queued", "running"}
                for r in self.executions.for_version(owner, version)
            ):
                return (
                    ReportView(state="queued", reason="Esperando la investigación y el dashboard."),
                    None,
                )
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
        return self.described(owner, item.file_name, item.number, runs, run, updating)

    def described(
        self,
        owner: UUID,
        file_name: str,
        number: int,
        runs: list[Execution],
        run: Execution,
        updating: bool = False,
    ) -> tuple[ReportView, Artifact | None]:
        """Vista de una versión terminada del informe. Fase 27: con su número y, en los
        informes v2, el documento para la vista previa."""
        artifact = next(
            a
            for a in self.executions.artifacts(owner, run.id)
            if a.kind in {"report_pdf", "report_document"}
        )
        document = (
            ReportDocument.model_validate_json(self.objects.read(artifact.content))
            if artifact.kind == "report_document"
            else None
        )
        return (
            ReportView(
                state="ready",
                execution_id=run.id,
                file_name=report_name(file_name, number),
                byte_size=artifact.content.byte_size,
                sha256=artifact.content.sha256,
                generated_at=run.finished_at,
                evidence_count=artifact.row_count,
                updating=updating,
                number=len(runs) - runs.index(run),
                document=document,
            ),
            artifact,
        )

    def report(self, owner: UUID, version: UUID) -> ReportView:
        return self.ready(owner, version)[0]

    def pdf(self, owner: UUID, version: UUID, execution: UUID | None = None) -> tuple[bytes, str]:
        view, artifact = (
            self.ready(owner, version) if execution is None else self.at(owner, version, execution)
        )
        if artifact is None or view.file_name is None:
            raise ApplicationError("REPORT_NOT_READY", "El informe todavía no está listo.", 409)
        if view.document is not None:
            # Fase 27: el PDF se dibuja del documento (reproducible para el mismo documento).
            name = (
                view.file_name
                if execution is None
                else view.file_name.replace(".pdf", f"-v{view.number}.pdf")
            )
            return render_pdf(view.document), name
        return self.objects.read(artifact.content), view.file_name

    # --- Fase 27: historial, revisión y versiones nuevas -----------------------------------

    def runs(self, owner: UUID, version: UUID) -> list[Execution]:
        self.datasets.get(owner, version)
        runs = [
            r for r in self.executions.for_version(owner, version) if r.kind == "automatic_report"
        ]
        if not runs:
            raise ApplicationError(
                "REPORT_NOT_AVAILABLE", "Esta versión no tiene informe automático.", 404
            )
        return runs

    def at(self, owner: UUID, version: UUID, execution: UUID) -> tuple[ReportView, Artifact | None]:
        """Una versión concreta del historial."""
        item = self.datasets.get(owner, version)
        runs = self.runs(owner, version)
        run = next((r for r in runs if r.id == execution), None)
        if run is None:
            raise ApplicationError("REPORT_NOT_FOUND", "Esa versión del informe no existe.", 404)
        if run.state != "succeeded":
            return (
                ReportView(
                    state=run.state if run.state in {"queued", "running"} else "failed",
                    execution_id=run.id,
                    reason=run.error_code,
                    number=len(runs) - runs.index(run),
                ),
                None,
            )
        return self.described(owner, item.file_name, item.number, runs, run)

    def history(self, owner: UUID, version: UUID) -> ReportHistory:
        runs = self.runs(owner, version)
        items = []
        for index, run in enumerate(runs):
            document = None
            if run.state == "succeeded":
                artifact = next(
                    (
                        a
                        for a in self.executions.artifacts(owner, run.id)
                        if a.kind == "report_document"
                    ),
                    None,
                )
                if artifact is not None:
                    document = ReportDocument.model_validate_json(
                        self.objects.read(artifact.content)
                    )
            given = run.plan.content["input"] if run.plan else {}
            items.append(
                ReportVersion(
                    number=len(runs) - index,
                    execution_id=run.id,
                    state=run.state,
                    trigger=str(
                        given.get("trigger") or ("load" if index == len(runs) - 1 else "update")
                    ),
                    created_at=run.created_at,
                    finished_at=run.finished_at,
                    rules_version=document.rules_version if document else None,
                    approved=sum(i.status == "approved" for i in document.review)
                    if document
                    else None,
                    principal=sum(i.principal for i in document.review) if document else None,
                )
            )
        return ReportHistory(items=items)

    def latest_document(self, owner: UUID, version: UUID) -> ReportDocument:
        for run in self.runs(owner, version):
            if run.state != "succeeded":
                continue
            artifact = next(
                (
                    a
                    for a in self.executions.artifacts(owner, run.id)
                    if a.kind == "report_document"
                ),
                None,
            )
            if artifact is None:
                break
            return ReportDocument.model_validate_json(self.objects.read(artifact.content))
        raise ApplicationError(
            "REPORT_V2_REQUIRED",
            "Este informe es anterior a la Fase 27: vuelve a investigar la versión para revisar "
            "sus hallazgos.",
            409,
        )

    def candidates(self, owner: UUID, version: UUID) -> ReportReview:
        """Hallazgos candidatos con la revisión vigente y si difiere de la del último informe."""
        document = self.latest_document(owner, version)
        if self.db is None:
            raise ApplicationError("REPORT_V2_REQUIRED", "Revisión no disponible.", 409)
        analysis = AutomaticAnalysis.model_validate_json(
            self.objects.read(self.analysis_ref(owner, document))
        )
        exploration = None
        if document.source.exploration_execution_id is not None:
            artifact = next(
                (
                    a
                    for a in self.executions.artifacts(
                        owner, document.source.exploration_execution_id
                    )
                    if a.kind == "exploration"
                ),
                None,
            )
            if artifact is not None:
                exploration = Exploration.model_validate_json(self.objects.read(artifact.content))
        verdicts = {
            f.item: f.verdict for f in SQLFindingFeedback(self.db).for_version(owner, version)
        }
        items = review_items(analysis, exploration, verdicts)
        return ReportReview(
            items=items,
            changed=selection_digest_items(items) != selection_digest_items(document.review),
        )

    def analysis_ref(self, owner: UUID, document: ReportDocument) -> StoredObject:
        artifact = next(
            a
            for a in self.executions.artifacts(owner, document.source.analysis_execution_id)
            if a.kind == "automatic_analysis"
        )
        return artifact.content

    def review(self, owner: UUID, version: UUID, request: ReviewRequest) -> ReportReview:
        """Aprueba, rechaza o deja pendiente un hallazgo (no genera el informe: eso lo pide el
        usuario con «Generar versión»)."""
        current = self.candidates(owner, version)
        if request.item not in {i.item for i in current.items}:
            raise ApplicationError(
                "FINDING_NOT_FOUND", "Ese hallazgo no es un candidato del informe.", 404
            )
        assert self.db is not None
        project = self.datasets.get(owner, version).project_id
        ProjectPermissions(self.db).require(owner, project, writable=True)
        verdict = {"approved": "keep", "rejected": "drop", "pending": "none"}[request.status]
        SQLFindingFeedback(self.db).add(owner, project, version, request.item, verdict)  # type: ignore[arg-type]
        self.db.commit()
        return self.candidates(owner, version)

    def generate(self, owner: UUID, version: UUID) -> ReportView:
        """Genera una versión nueva del informe con la selección vigente; la anterior se
        conserva. Sin cambios en la selección no se genera ninguna."""
        current = self.candidates(owner, version)
        runs = self.runs(owner, version)
        if runs[0].state in {"queued", "running"}:
            raise ApplicationError(
                "REPORT_GENERATING", "Ya se está generando una versión del informe.", 409
            )
        if not current.changed:
            raise ApplicationError(
                "REPORT_UP_TO_DATE",
                "El informe ya usa esta selección: cambia la revisión para generar otra versión.",
                409,
            )
        assert self.db is not None
        ProjectPermissions(self.db).require(owner, runs[0].project_id, writable=True)
        state = digest("report_selection", {"items": selection_digest_items(current.items)})
        request_report_update(self.executions, owner, version, f"selection:{state}")
        self.db.commit()
        return self.report(owner, version)
