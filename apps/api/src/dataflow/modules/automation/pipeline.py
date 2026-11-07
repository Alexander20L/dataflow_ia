"""Orquestación durable del pipeline automático (Fase 11C).

Pasos: propose → preview → approve → apply → diagnose → quality_rules → select. `ingest` y
`profile_quality` los hace la importación antes de crear el pipeline. Cada paso llama a un caso
de uso existente con una clave idempotente derivada del pipeline, así que repetir un paso (otro
worker, una caída entre encolar y registrar, el reconciliador) devuelve lo mismo y no duplica
planes, vistas previas, aprobaciones ni versiones. Sin reintentos automáticos: un fallo o un
bloqueo deja el pipeline en `needs_review` con motivos.
"""

from typing import Any
from uuid import UUID, uuid5

from dataflow.modules.automation.pipeline_contracts import (
    TERMINAL,
    AutomationRunPage,
    AutomationRunView,
    PipelinePort,
    PipelineRun,
    RunRepository,
)
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork

WAITING = {"queued", "running"}
MAX_TRANSITIONS = 12  # sin bucles: un avance recorre como mucho la secuencia completa

MESSAGES = {
    "INPUT_TABLE_MISSING": "La versión no tiene una tabla publicada.",
    "PLAN_INVALID": "El plan de limpieza propuesto no es válido.",
    "PREVIEW_FAILED": "La vista previa de la limpieza falló.",
    "APPLY_FAILED": "La aplicación de la limpieza falló.",
    "DIAGNOSTIC_FAILED": "El diagnóstico de la versión derivada falló.",
    "RULES_FAILED": "La evaluación de las reglas de calidad falló.",
    "SELECT_FAILED": "No se pudo activar la versión resultante como fuente.",
    "EXECUTION_CANCELLED": "Una ejecución del pipeline se canceló.",
    "STEP_ERROR": "Un paso del pipeline no se pudo completar.",
}


def reason(code: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, "message": MESSAGES[code], **detail}


class PipelineService:
    def __init__(self, runs: RunRepository, port: PipelinePort, uow: UnitOfWork) -> None:
        self.runs, self.port, self.uow = runs, port, uow

    # --- consulta y control ---

    def get(self, owner: UUID, run: UUID) -> AutomationRunView:
        return self.runs.view(owner, run)

    def page(self, owner: UUID, project: UUID, limit: int, offset: int) -> AutomationRunPage:
        return self.runs.page(owner, project, limit, offset)

    def for_version(self, owner: UUID, version: UUID) -> AutomationRunView | None:
        return self.runs.for_version(owner, version)

    def attention(self, owner: UUID, limit: int = 20) -> list[AutomationRunView]:
        """Pipelines en `needs_review` o `failed`: la bandeja de avisos."""
        return self.runs.attention(owner, limit)

    def cancel(self, owner: UUID, run_id: UUID) -> AutomationRunView:
        self.runs.view(owner, run_id)  # 404 si no es del propietario
        if not self.runs.try_lock(run_id):
            raise ApplicationError(
                "AUTOMATION_RUN_BUSY", "El pipeline está avanzando; vuelve a intentarlo.", 409
            )
        try:
            run = self.runs.load(run_id)
            assert run
            if run.state in TERMINAL:
                return self.runs.view(owner, run_id)
            for execution in (run.preview_execution_id, run.apply_execution_id):
                if execution:
                    state, _ = self.port.execution_state(owner, execution)
                    if state == "queued":
                        self.port.cancel_execution(owner, execution)
            run.state = "cancelled"
            self.runs.save(run)
            self.runs.log(run.id, run.step, "cancelled", {"by": str(owner)})
            self.uow.commit()
            return self.runs.view(owner, run_id)
        except Exception:
            self.uow.rollback()
            raise
        finally:
            self.runs.unlock(run_id)

    # --- avance ---

    def reconcile(self, limit: int = 20) -> int:
        """Avanza los pipelines en curso (también los detenidos por una caída). Idempotente."""
        advanced = 0
        for run_id in self.runs.running_ids(limit):
            if self.advance(run_id):
                advanced += 1
        return advanced

    def advance(self, run_id: UUID) -> bool:
        """Avanza hasta que el pipeline espera una ejecución o termina. Devuelve True sólo si
        cambió algo (así el worker duerme mientras un pipeline espera)."""
        if not self.runs.try_lock(run_id):
            return False  # otro worker lo está avanzando
        try:
            run = self.runs.load(run_id)
            if run is None or run.state != "running":
                self.uow.rollback()
                return False
            start = (
                run.state,
                run.step,
                run.preview_execution_id,
                run.apply_execution_id,
                run.rules_execution_id,
            )
            for _ in range(MAX_TRANSITIONS):
                before = (run.state, run.step)
                try:
                    self.step(run)
                except ApplicationError as error:
                    # Un caso de uso rechazó el paso: se detiene con el motivo, sin reintentar.
                    self.uow.rollback()
                    self.stop(run, "needs_review", [reason("STEP_ERROR", measured=error.code)])
                self.runs.save(run)
                self.uow.commit()
                if run.state != "running" or (run.state, run.step) == before:
                    break
            end = (
                run.state,
                run.step,
                run.preview_execution_id,
                run.apply_execution_id,
                run.rules_execution_id,
            )
            return end != start
        except Exception:
            self.uow.rollback()
            raise
        finally:
            self.runs.unlock(run_id)

    def stop(self, run: PipelineRun, state: str, reasons: list[dict[str, Any]]) -> None:
        run.state, run.reasons = state, reasons
        self.runs.log(
            run.id, run.step, "blocked" if state == "needs_review" else state, {"reasons": reasons}
        )

    def move(self, run: PipelineRun, step: str, detail: dict[str, Any] | None = None) -> None:
        self.runs.log(run.id, run.step, "succeeded", detail or {})
        run.step = step

    def wait_for(self, run: PipelineRun, execution: UUID, failure: str) -> bool | None:
        """True si terminó bien, None si sigue en curso, False si se detuvo el pipeline."""
        state, error = self.port.execution_state(run.owner_id, execution)
        if state in WAITING:
            return None
        if state == "succeeded":
            return True
        code = "EXECUTION_CANCELLED" if state == "cancelled" else failure
        self.stop(run, "needs_review", [reason(code, measured=error)])
        return False

    def step(self, run: PipelineRun) -> None:
        owner = run.owner_id
        if run.step == "propose":
            table = self.port.table_of(owner, run.version_id)
            if table is None:
                self.stop(run, "failed", [reason("INPUT_TABLE_MISSING")])
                return
            steps, semantic = self.port.proposal(owner, table[0])
            if not steps:
                run.result_version_id = run.version_id
                self.move(run, "select", {"proposal": "nothing_to_clean"})
                return
            plan = self.port.create_plan(
                owner,
                run.project_id,
                table[0],
                table[1],
                steps,
                semantic,
                uuid5(run.id, "plan"),
            )
            run.plan_revision_id = plan.revision_id
            if not plan.valid:
                self.stop(
                    run, "needs_review", [reason("PLAN_INVALID", measured=", ".join(plan.problems))]
                )
                return
            self.move(run, "preview", {"plan_revision_id": str(plan.revision_id)})
        elif run.step == "preview":
            assert run.plan_revision_id
            if run.preview_execution_id is None:
                run.preview_execution_id = self.port.start_preview(
                    owner, run.plan_revision_id, uuid5(run.id, "preview")
                )
                self.runs.log(
                    run.id, "preview", "started", {"execution_id": str(run.preview_execution_id)}
                )
            if self.wait_for(run, run.preview_execution_id, "PREVIEW_FAILED"):
                self.move(run, "approve")
        elif run.step == "approve":
            assert run.preview_execution_id
            result = self.port.approve(
                owner, run.preview_execution_id, run.policy_revision_id, run.id
            )
            if not result.approved:
                self.stop(run, "needs_review", result.reasons)
                return
            run.approval_id = result.approval_id
            self.move(run, "apply", {"approval_id": str(result.approval_id)})
        elif run.step == "apply":
            assert run.approval_id
            if run.apply_execution_id is None:
                run.apply_execution_id = self.port.start_apply(owner, run.approval_id)
                self.runs.log(
                    run.id, "apply", "started", {"execution_id": str(run.apply_execution_id)}
                )
            if self.wait_for(run, run.apply_execution_id, "APPLY_FAILED"):
                run.derived_version_id = self.port.derived_version(run.apply_execution_id)
                self.move(run, "diagnose", {"derived_version_id": str(run.derived_version_id)})
        elif run.step == "diagnose":
            assert run.derived_version_id
            state = self.port.version_state(owner, run.derived_version_id)
            if state is None or state in WAITING:
                return
            if state != "succeeded":
                self.stop(run, "needs_review", [reason("DIAGNOSTIC_FAILED", measured=state)])
                return
            run.result_version_id = run.derived_version_id
            self.move(run, "quality_rules")
        elif run.step == "quality_rules":
            assert run.result_version_id
            if not self.port.evaluate_rules(owner, run.policy_revision_id):
                self.move(run, "select", {"quality_rules": "disabled_by_policy"})
                return
            table = self.port.table_of(owner, run.result_version_id)
            ruleset = self.port.applicable_ruleset(owner, table[0]) if table else None
            if table is None or ruleset is None:
                # Aviso, no bloquea: sin conjunto aplicable no hay reglas que evaluar.
                self.move(run, "select", {"quality_rules": "RULESET_NOT_APPLICABLE"})
                return
            if run.rules_execution_id is None:
                run.rules_execution_id = self.port.start_rules(
                    owner, run.project_id, table[0], table[1], ruleset, uuid5(run.id, "rules")
                )
                self.runs.log(
                    run.id,
                    "quality_rules",
                    "started",
                    {"execution_id": str(run.rules_execution_id)},
                )
            if self.wait_for(run, run.rules_execution_id, "RULES_FAILED"):
                self.move(run, "select")
        elif run.step == "select":
            assert run.result_version_id
            try:
                self.port.select_source(owner, run.project_id, run.result_version_id)
            except ApplicationError as error:
                self.stop(run, "needs_review", [reason("SELECT_FAILED", measured=error.code)])
                return
            self.move(run, "done", {"result_version_id": str(run.result_version_id)})
            run.state = "completed"
