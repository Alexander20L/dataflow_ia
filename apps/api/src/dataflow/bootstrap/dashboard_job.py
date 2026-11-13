"""Dashboard adaptado a los datos (Fase 21, ADR-038): une la cola, lo publicado y la IA.

Al publicarse la exploración de una carga se encola un trabajo `dashboard` que fija la
exploración, el análisis automático y la comprensión. La IA diseña secciones, orden y tipo de
gráfico sin ver cifras; Python valida el diseño y, sin IA, lo hacen las reglas. Las marcas
«sí va / no va» del usuario (tabla `finding_feedback`) no cambian el dashboard publicado: se
aplican al leerlo y encolan una versión nueva del informe.

Fase 26 (ADR-044, `delivery.dashboard@2`): el trabajo calcula además, con el motor exacto de la
exploración y sobre todas las filas, los indicadores, la evolución, los histogramas y los pares
de medidas; guarda el origen de cada elemento. Los filtros recalculan al momento los elementos
que dependen de ellos (sin guardar nada) y la versión personalizada se guarda en revisiones
(`dashboard_customizations`) sin tocar la automática.
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
from dataflow.modules.curation.public import (
    DashboardCustomizationRequest,
    FindingFeedbackRequest,
    SQLDashboardCustomizations,
    SQLFindingFeedback,
)
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.delivery.contracts import (
    Dashboard,
    DashboardFilterRequest,
    DashboardFilterResult,
    DashboardItem,
    DashboardScope,
    DashboardSection,
    DashboardView,
    DesignDecision,
    FilteredItem,
    FilterOptions,
    Indicator,
)
from dataflow.modules.delivery.dashboard import (
    WIDGETS,
    arrange,
    build_indicators,
    catalog,
    catalog_v2,
    check_filters,
    computed_key,
    current_layout,
    dashboard_plan,
    filter_labels,
    filter_options,
    insight_key,
    layout_errors,
    partial_notice,
    reference_label,
    result_key,
    rules_design,
    rules_design_v2,
    sufficiency_notice,
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
from dataflow.modules.exploration.contracts import Exploration, ExploreQuery, ExploreResult
from dataflow.modules.exploration.public import compute, row_count, subset
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

STEP = "delivery.dashboard"
VERSION = 2  # Fase 26: indicadores, filtros, origen y versión personalizada


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
    key = uuid5(lease.execution_id, f"dashboard@{VERSION}")
    fingerprint = digest(
        "dashboard_request",
        {
            "exploration_sha256": exploration.content.sha256,
            "analysis_sha256": analysis.content.sha256,
            "operation": f"{STEP}@{VERSION}",
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
            # Fase 26: la tabla publicada que leyó la investigación (indicadores y filtros).
            **({"table": given["table"]} if "table" in given else {}),
        },
        "steps": [
            {
                "id": "dashboard",
                "operation": STEP,
                "version": VERSION,
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


def period_of(comprehension: Comprehension) -> tuple[str, list[str]] | None:
    period = comprehension.period
    return (period.kind, list(period.columns)) if period and period.periods >= 2 else None


class Parts:
    """Lo que calcula el dashboard v2 (Fase 26) y sus elementos con su origen."""

    def __init__(
        self,
        items: list[DashboardItem],
        indicators: list[Indicator],
        computed: list[ExploreResult],
        options: FilterOptions,
        total_rows: int,
    ) -> None:
        self.items, self.indicators, self.computed = items, indicators, computed
        self.options, self.total_rows = options, total_rows


def computed_parts(
    execution: str,
    table: bytes,
    comprehension: Comprehension,
    exploration: Exploration,
    analysis: AutomaticAnalysis,
) -> Parts:
    """Calcula con el motor exacto, sobre todas las filas, las consultas del dashboard (las
    que no se pueden calcular se omiten) y arma indicadores, filtros y elementos."""
    plan = dashboard_plan(comprehension)
    period = period_of(comprehension)
    results: dict[str, ExploreResult] = {}
    for query in plan.queries():
        found = compute(table, query, execution, period)
        if isinstance(found, ExploreResult):
            results[query.key] = found
    total = row_count(table)
    options = filter_options(comprehension, plan, results)
    indicators = build_indicators(
        comprehension, plan, results, total, reference_label(None, options.months), []
    )
    computed = list(results.values())
    items = catalog_v2(
        analysis.insights,
        {e.evidence_id: e for e in analysis.evidence},
        exploration,
        computed,
        indicators,
        total,
        options.period_columns,
    )
    return Parts(items, indicators, computed, options, total)


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
        extra = None
        if step.version >= 2 and "table" in given:
            extra = computed_parts(
                str(lease.execution_id),
                self.objects.read(reference(given["table"])),
                comprehension,
                exploration,
                analysis,
            )
            items = extra.items
        else:
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
            sections = (
                rules_design_v2(analysis.insights, items, extra.indicators)
                if extra
                else rules_design(analysis.insights, items)
            )
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
            **(
                {
                    "operation": f"{STEP}@2",
                    "rules_version": "dashboard-design-v2",
                    "items": items,
                    "indicators": extra.indicators,
                    "computed": extra.computed,
                    "filters": extra.options,
                    "total_rows": extra.total_rows,
                    "partial": partial_notice(exploration),
                    "notice": sufficiency_notice(items),
                }
                if extra
                else {}
            ),
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
    if content["input"].get("kind") == "report_v2":
        # Fase 27: el historial dice qué pidió cada versión («selection», «dashboard»…).
        content = {**content, "input": {**content["input"], "trigger": trigger.split(":")[0]}}
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


def report_is_v2(executions: Executions, owner: UUID, version: UUID) -> bool:
    runs = [r for r in executions.for_version(owner, version) if r.kind == "automatic_report"]
    return (
        bool(runs)
        and runs[0].plan is not None
        and (runs[0].plan.content["input"].get("kind") == "report_v2")
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
        self.customizations = SQLDashboardCustomizations(db)

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
        # Fase 26: la versión personalizada puede mostrar cualquier elemento del dashboard.
        used = {w.item for s in dashboard.sections for w in s.widgets} | {
            i.id for i in dashboard.items
        }
        feedback = self.feedback.for_version(owner, version)
        custom, dropped = (
            current_layout(self.customizations.latest(owner, version), dashboard.items)
            if dashboard.rules_version == "dashboard-design-v2"
            else (None, 0)
        )
        return DashboardView(
            state="ready",
            execution_id=run.id,
            dashboard=dashboard,
            arrangement=arrange(dashboard, {f.item: f.verdict for f in feedback}),
            insights=[i for i in analysis.insights if insight_key(i) in used],
            results=[r for r in exploration.results if result_key(r) in used],
            feedback=[f for f in feedback if f.item in used],
            custom=custom,
            custom_dropped=dropped,
        )

    def ready(self, owner: UUID, version: UUID) -> tuple[Execution, Dashboard]:
        """El dashboard v2 listo (Fase 26: filtros y versión personalizada)."""
        run = self.run(owner, version)
        found = self.result(owner, run)
        if found is None:
            raise ApplicationError(
                "DASHBOARD_NOT_READY", "El dashboard todavía no está listo.", 409
            )
        dashboard = found[0]
        if dashboard.rules_version != "dashboard-design-v2":
            raise ApplicationError(
                "DASHBOARD_V2_REQUIRED",
                "Este dashboard es anterior a la Fase 26: vuelve a investigar la versión para "
                "poder filtrarlo y personalizarlo.",
                409,
            )
        return run, dashboard

    def filter(
        self, owner: UUID, version: UUID, request: DashboardFilterRequest
    ) -> DashboardFilterResult:
        """Recalcula con el motor exacto, sobre todas las filas que cumplen los filtros, los
        elementos que dependen de ellos y los indicadores. No guarda nada: las evidencias se
        derivan de los filtros y se pueden reproducir."""
        run, dashboard = self.ready(owner, version)
        assert run.plan
        given = run.plan.content["input"]
        options = dashboard.filters
        if options is None or "table" not in given:
            raise ApplicationError(
                "DASHBOARD_V2_REQUIRED", "Este dashboard no se puede filtrar.", 409
            )
        reason = check_filters(request, options)
        if reason:
            raise ApplicationError("DASHBOARD_FILTER_INVALID", reason, 422)
        comprehension = Comprehension.model_validate_json(
            self.objects.read(reference(given["comprehension"]))
        )
        explored = self.executions.artifact(owner, UUID(given["artifact_id"]))
        exploration = Exploration.model_validate_json(self.objects.read(explored.content))
        table = self.objects.read(reference(given["table"]))
        period = period_of(comprehension)
        content, rows, total = subset(
            table,
            period,
            request.period_from,
            request.period_to,
            {c.column: c.values for c in request.categories},
        )
        labels = filter_labels(request)
        fingerprint = digest("dashboard_filter", request.model_dump(mode="json"))
        execution = f"{run.id}:filtro:{fingerprint}"
        queries = {computed_key(r.query): r.query for r in dashboard.computed} | {
            result_key(r): r.query for r in exploration.results
        }
        results: dict[str, ExploreResult] = {}

        def calculate(query: ExploreQuery) -> ExploreResult | str:
            if rows == 0:
                return "Ningún registro cumple los filtros."
            if query.key not in results:
                found = compute(content, query, execution, period)
                if isinstance(found, str):
                    return found
                results[query.key] = found
            return results[query.key]

        items: list[FilteredItem] = []
        for item in dashboard.items:
            query = queries.get(item.id)
            if not item.filterable or query is None:
                items.append(
                    FilteredItem(
                        item=item.id,
                        reason="Hallazgo del análisis automático: muestra el dataset completo "
                        "y no se recalcula con filtros.",
                    )
                )
                continue
            found = calculate(query)
            items.append(
                FilteredItem(item=item.id, result=found)
                if isinstance(found, ExploreResult)
                else FilteredItem(item=item.id, reason=found)
            )
        plan = dashboard_plan(comprehension)
        for query in plan.queries():
            calculate(query)
        indicators = build_indicators(
            comprehension,
            plan,
            results,
            total,
            reference_label(request, options.months),
            labels,
        )
        return DashboardFilterResult(
            filters=labels, rows=rows, total_rows=total, items=items, indicators=indicators
        )

    def customize(
        self, owner: UUID, version: UUID, request: DashboardCustomizationRequest
    ) -> DashboardView:
        """Guarda la versión personalizada como una revisión nueva; la automática no cambia."""
        run, dashboard = self.ready(owner, version)
        errors = layout_errors(list(request.sections), dashboard.items)
        if errors:
            raise ApplicationError("DASHBOARD_LAYOUT_INVALID", " ".join(errors[:5]), 422)
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        self.customizations.add(
            owner, run.project_id, version, run.id, request.expected_revision, request.sections
        )
        self.db.commit()
        return self.view(owner, version)

    def judge(self, owner: UUID, version: UUID, request: FindingFeedbackRequest) -> DashboardView:
        """Marca opcional: no recalcula; encola una versión nueva del informe con ese orden."""
        run = self.run(owner, version)
        found = self.result(owner, run)
        if found is None:
            raise ApplicationError(
                "DASHBOARD_NOT_READY", "El dashboard todavía no está listo.", 409
            )
        dashboard, artifact = found
        if request.item not in {w.item for s in dashboard.sections for w in s.widgets} | {
            i.id for i in dashboard.items
        }:
            raise ApplicationError(
                "FINDING_NOT_FOUND", "Ese elemento no está en el dashboard.", 404
            )
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        self.feedback.add(owner, run.project_id, version, request.item, request.verdict)
        marks = sorted([f.item, f.verdict] for f in self.feedback.for_version(owner, version))
        state = digest("finding_feedback", {"dashboard": artifact.content.sha256, "marks": marks})
        # Fase 27: con el informe v2 las marcas son la revisión de los hallazgos y la versión
        # nueva la pide el usuario («Generar versión»); con el v1 se regenera como antes.
        if not report_is_v2(self.executions, owner, version):
            request_report_update(self.executions, owner, version, f"feedback:{state}")
        self.db.commit()
        return self.view(owner, version)
