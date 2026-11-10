"""Dashboard adaptado a los datos (Fase 21, ADR-038): une la cola, lo publicado y la IA.

Al publicarse la exploración de una carga se encola un trabajo `dashboard` que fija la
exploración, el análisis automático y la comprensión. La IA diseña secciones, orden y tipo de
gráfico sin ver cifras; Python valida el diseño y, sin IA, lo hacen las reglas. Las marcas
«sí va / no va» del usuario (tabla `finding_feedback`) no cambian el dashboard publicado: se
aplican al leerlo y encolan una versión nueva del informe.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.modules.analytics.contracts import AutomaticAnalysis
from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.contracts import CallRecord
from dataflow.modules.copilot.dashboard import (
    DESIGN_ID,
    DESIGN_VERSION,
    design_context,
    design_dashboard,
)
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.curation.public import FindingFeedbackRequest, SQLFindingFeedback
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.delivery.contracts import (
    Dashboard,
    DashboardScope,
    DashboardSection,
    DashboardView,
    DesignDecision,
)
from dataflow.modules.delivery.dashboard import (
    WIDGETS,
    arrange,
    catalog,
    insight_key,
    result_key,
    rules_design,
    validate_design,
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
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

STEP = "delivery.dashboard"


def stored(item: Artifact) -> dict[str, object]:
    return {
        "artifact_id": str(item.id),
        "key": item.content.key,
        "sha256": item.content.sha256,
        "byte_size": item.content.byte_size,
    }


def reference(item: dict[str, Any]) -> StoredObject:
    return StoredObject(str(item["key"]), str(item["sha256"]), int(item["byte_size"]))


def published(executions: Executions, owner: UUID, version: UUID, kind: str) -> Artifact | None:
    """Último artefacto `kind` de una ejecución terminada de la versión."""
    for run in executions.for_version(owner, version):
        if run.state != "succeeded":
            continue
        for artifact in executions.artifacts(owner, run.id):
            if artifact.kind == kind:
                return artifact
    return None


def enqueue_dashboard(
    executions: Executions,
    lease: Lease,
    exploration: Artifact,
    config: ProcessingConfig,
) -> None:
    run = lease.execution
    assert run.plan and run.input_artifact_id
    given = run.plan.content["input"]
    analysis = published(executions, lease.owner_id, lease.version_id, "automatic_analysis")
    if analysis is None:
        return
    comprehension = executions.artifact(lease.owner_id, run.input_artifact_id)
    key = uuid5(lease.execution_id, "dashboard@1")
    fingerprint = digest(
        "dashboard_request",
        {
            "exploration_sha256": exploration.content.sha256,
            "analysis_sha256": analysis.content.sha256,
            "operation": f"{STEP}@1",
        },
    )
    if executions.find_request(lease.owner_id, run.project_id, "dashboard", key, fingerprint):
        return
    content = {
        "objective": None,
        "input": {
            "kind": "dashboard",
            "alias": "source",
            "version_id": given["version_id"],
            "version_content_sha256": given["version_content_sha256"],
            "artifact_id": str(exploration.id),
            "artifact_sha256": exploration.content.sha256,
            "producer_execution_id": str(exploration.execution_id),
            "analysis": stored(analysis),
            "comprehension": stored(comprehension),
        },
        "steps": [
            {
                "id": "dashboard",
                "operation": STEP,
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {},
            }
        ],
        # Llamada facturable: un solo intento.
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
        exploration.id,
        exploration.content.sha256,
        kind="dashboard",
    )


class DashboardInput:
    """Comprueba que la exploración, el análisis y la comprensión fijados son los de la carga."""

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
        exploration = self.executions.artifact(run.owner_id, run.input_artifact_id)
        analysis = self.executions.artifact(run.owner_id, UUID(given["analysis"]["artifact_id"]))
        comprehension = self.executions.artifact(
            run.owner_id, UUID(given["comprehension"]["artifact_id"])
        )
        if (
            exploration.kind != "exploration"
            or analysis.kind != "automatic_analysis"
            or comprehension.kind != "comprehension"
            or {exploration.version_id, analysis.version_id, comprehension.version_id}
            != {version.id}
            or str(version.id) != given.get("version_id")
            or version.content.sha256 != given.get("version_content_sha256")
            or exploration.content.sha256 != run.input_artifact_sha256
            or analysis.content != reference(given["analysis"])
            or comprehension.content != reference(given["comprehension"])
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "Lo fijado para el dashboard no coincide con la carga.", 409
            )
        return StepInput("dashboard", exploration.content, analysis.content.sha256)


class DashboardStep:
    output_kind: ArtifactKind = "dashboard"
    transforms_data = False

    def __init__(self, objects: ObjectStore, copilot: CopilotService) -> None:
        self.objects, self.copilot = objects, copilot
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

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "dashboard" or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó el dashboard.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        plan = lease.execution.plan
        assert plan
        given = plan.content["input"]
        exploration = Exploration.model_validate_json(self.objects.read(source.content))
        analysis_ref = reference(given["analysis"])
        analysis = AutomaticAnalysis.model_validate_json(self.objects.read(analysis_ref))
        comprehension = Comprehension.model_validate_json(
            self.objects.read(reference(given["comprehension"]))
        )
        items = catalog(analysis.insights, exploration)
        provider = self.copilot.provider
        calls: list[dict[str, object]] = []
        ai_state: str = "unavailable"
        ai_reason: str | None = unavailable or "disabled"
        title: str | None = None
        sections: list[DashboardSection] = []
        decisions: list[DesignDecision] = []
        if provider is not None and unavailable is None and items:
            output, call, error = design_dashboard(
                provider,
                design_context(
                    comprehension.domain,
                    comprehension.questions,
                    [item.model_dump(mode="json") for item in items],
                    WIDGETS,
                ),
                self.copilot.config.max_output_tokens,
            )
            if call is not None:
                calls.append(call.model_dump(mode="json"))
            if output is None:
                ai_state, ai_reason = "failed", error
            else:
                ai_state, ai_reason = "ready", None
                title, sections, decisions = validate_design(output, items)
        designed_by = "ai" if sections else "rules"
        if not sections:
            sections = rules_design(analysis.insights, items)
            if ai_state == "ready":
                ai_reason = "El diseño de la IA no tenía ningún elemento válido."
        dashboard = Dashboard(
            scope=DashboardScope(
                execution_id=lease.execution_id,
                version_id=lease.version_id,
                analysis_sha256=analysis_ref.sha256,
                exploration_sha256=source.content.sha256,
            ),
            designed_by=designed_by,
            ai_state=ai_state,
            ai_reason=ai_reason,
            title=title or "Dashboard del negocio",
            sections=sections,
            decisions=decisions,
            calls=calls,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/dashboard.json", dashboard.model_dump_json().encode())
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "dashboard",
                    "dashboard",
                    content,
                    "application/json",
                    sum(len(s.widgets) for s in sections),
                    len(sections),
                )
            ]
        )


def record_dashboard_calls(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    result = Dashboard.model_validate_json(objects.read(output.content))
    if (
        result.scope.execution_id != lease.execution_id
        or result.scope.exploration_sha256 != lease.execution.input_artifact_sha256
    ):
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "El dashboard no corresponde a su exploración.", 409
        )
    repository = SQLCopilotRepository(db)
    for item in result.calls:
        call: dict[str, Any] = dict(item)
        repository.log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="dashboard_design",
                provider=str(call["provider"]),
                model=str(call["model"]),
                parameters=dict(call["parameters"]),
                prompt_id=DESIGN_ID,
                prompt_version=DESIGN_VERSION,
                context_sha256=str(call["context_sha256"]),
                input_tokens=int(call["input_tokens"]),
                output_tokens=int(call["output_tokens"]),
                cache_read_tokens=int(call["cache_read_tokens"]),
                cache_write_tokens=int(call["cache_write_tokens"]),
                cost_usd=Decimal(str(call["cost_usd"])) if call.get("cost_usd") else None,
                latency_ms=int(call["latency_ms"]),
                outcome=str(call["outcome"]),  # type: ignore[arg-type]
                validation={
                    "dashboard": str(lease.execution_id),
                    "designed_by": result.designed_by,
                    "rejected": sum(d.status == "rejected" for d in result.decisions),
                },
                error_code=call.get("error_code"),
            )
        )


def request_report_update(executions: Executions, owner: UUID, version: UUID, trigger: str) -> None:
    """Encola una versión nueva del informe de la carga (Fase 21), que lee el dashboard y las
    marcas al generarse. No hace nada si aún no hay informe (el primero ya los leerá) o si hay
    una versión esperando en la cola. El informe anterior se conserva."""
    runs = [r for r in executions.for_version(owner, version) if r.kind == "automatic_report"]
    if not runs or runs[0].state == "queued":
        return
    base = runs[0]
    assert base.plan and base.input_artifact_id and base.input_artifact_sha256
    content = base.plan.content
    key = uuid5(version, f"automatic-report-update:{len(runs)}:{trigger}")
    fingerprint = digest(
        "automatic_report_update",
        {"base_sha256": base.plan.content_sha256, "trigger": trigger, "count": len(runs)},
    )
    if executions.find_request(owner, base.project_id, "automatic_report", key, fingerprint):
        return
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
    executions.enqueue_followup(
        owner,
        base.project_id,
        version,
        key,
        fingerprint,
        plan,
        str(uuid5(version, trigger)),  # correlación (36 caracteres)
        base.input_artifact_id,
        base.input_artifact_sha256,
        kind="automatic_report",
    )


class DashboardAccess:
    """Lectura del dashboard y registro de marcas; nunca recalcula ni llama a la IA."""

    def __init__(
        self,
        db: Session,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        feedback: SQLFindingFeedback,
    ) -> None:
        self.db, self.datasets, self.executions = db, datasets, executions
        self.objects, self.feedback = objects, feedback

    def run(self, owner: UUID, version: UUID) -> Execution:
        self.datasets.get(owner, version)
        runs = [r for r in self.executions.for_version(owner, version) if r.kind == "dashboard"]
        if not runs:
            raise ApplicationError(
                "DASHBOARD_NOT_AVAILABLE",
                "Esta versión no tiene dashboard adaptado: se procesó antes de la Fase 21 o su "
                "exploración no terminó.",
                404,
            )
        return runs[0]

    def waiting(self, owner: UUID, version: UUID) -> bool:
        """El dashboard aún no tiene trabajo porque la comprensión o la exploración de la carga
        siguen en marcha (se encola al publicarse la exploración)."""
        return any(
            r.kind in {"comprehension", "exploration"} and r.state in {"queued", "running"}
            for r in self.executions.for_version(owner, version)
        )

    def result(self, owner: UUID, run: Execution) -> tuple[Dashboard, Artifact] | None:
        if run.state != "succeeded":
            return None
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "dashboard"
        )
        found = Dashboard.model_validate_json(self.objects.read(artifact.content))
        if found.scope.execution_id != run.id:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El dashboard no corresponde a esta versión.", 409
            )
        return found, artifact

    def view(self, owner: UUID, version: UUID) -> DashboardView:
        try:
            run = self.run(owner, version)
        except ApplicationError as error:
            if error.code == "DASHBOARD_NOT_AVAILABLE" and self.waiting(owner, version):
                return DashboardView(state="queued", reason="Esperando la exploración guiada.")
            raise
        if run.state in {"queued", "running"}:
            return DashboardView(state=run.state, execution_id=run.id)
        found = self.result(owner, run)
        if found is None:
            return DashboardView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        dashboard = found[0]
        assert run.plan
        given = run.plan.content["input"]
        analysis = AutomaticAnalysis.model_validate_json(
            self.objects.read(reference(given["analysis"]))
        )
        explored = self.executions.artifact(owner, UUID(given["artifact_id"]))
        exploration = Exploration.model_validate_json(self.objects.read(explored.content))
        used = {w.item for s in dashboard.sections for w in s.widgets}
        feedback = self.feedback.for_version(owner, version)
        return DashboardView(
            state="ready",
            execution_id=run.id,
            dashboard=dashboard,
            arrangement=arrange(dashboard, {f.item: f.verdict for f in feedback}),
            insights=[i for i in analysis.insights if insight_key(i) in used],
            results=[r for r in exploration.results if result_key(r) in used],
            feedback=[f for f in feedback if f.item in used],
        )

    def judge(self, owner: UUID, version: UUID, request: FindingFeedbackRequest) -> DashboardView:
        """Marca opcional: no recalcula; encola una versión nueva del informe con ese orden."""
        run = self.run(owner, version)
        found = self.result(owner, run)
        if found is None:
            raise ApplicationError(
                "DASHBOARD_NOT_READY", "El dashboard todavía no está listo.", 409
            )
        dashboard, artifact = found
        if request.item not in {w.item for s in dashboard.sections for w in s.widgets}:
            raise ApplicationError(
                "FINDING_NOT_FOUND", "Ese elemento no está en el dashboard.", 404
            )
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        self.feedback.add(owner, run.project_id, version, request.item, request.verdict)
        marks = sorted([f.item, f.verdict] for f in self.feedback.for_version(owner, version))
        state = digest("finding_feedback", {"dashboard": artifact.content.sha256, "marks": marks})
        request_report_update(self.executions, owner, version, f"feedback:{state}")
        self.db.commit()
        return self.view(owner, version)
