from typing import Any

from dataflow.modules.executions.contracts import InputKind, PlanStepSpec, RunState
from dataflow.platform.errors import ApplicationError

# Cola de trabajos (Fase 13C): ninguna carga se rechaza por haber otra en curso. Se admiten
# hasta PENDING_LIMIT trabajos pendientes por propietario (protección frente a abusos) y el
# worker ejecuta a la vez como máximo RUNNING_LIMIT por propietario y una sola importación
# por proyecto; el resto espera en cola en orden de llegada.
PENDING_LIMIT = 50
RUNNING_LIMIT = 3
# Fase 16: trabajos de fondo que se reclaman después de cualquier otro en cola (Fase 17: y el
# informe automático).
BACKGROUND_KINDS: frozenset[str] = frozenset({"investigation", "automatic_report"})


def failure_state(attempts: int, maximum: int, retryable: bool) -> RunState:
    return "queued" if retryable and attempts < maximum else "failed"


def legacy_state(state: RunState) -> str:
    return "processing" if state == "running" else state


def plan_input_kind(content: dict[str, Any]) -> InputKind:
    kind = content.get("input", {}).get("kind")
    if kind == "source":
        return "source"
    if kind == "table":
        return "table"
    if kind == "report":
        return "report"
    if kind == "overview":
        return "overview"
    if kind == "automatic":
        return "automatic"
    if kind == "investigation":
        return "investigation"
    raise ApplicationError("INPUT_MISMATCH", "El plan no declara un input admitido.", 409)


def plan_steps(content: dict[str, Any]) -> list[PlanStepSpec]:
    """Adaptador común: los planes 0.5 (csv_import/table_analysis) y los de usuario comparten
    formato de pasos. Rechaza en ejecución referencias que la validación previa ya excluye."""
    steps: list[PlanStepSpec] = []
    seen: set[str] = set()
    for raw in content.get("steps", []):
        source = raw["input"]
        if source["kind"] == "input" and source.get("alias") == "source":
            input_step = None
        elif source["kind"] == "step" and source.get("step_id") in seen:
            input_step = str(source["step_id"])
        else:
            raise ApplicationError(
                "INVALID_STEP_REFERENCE", "El plan contiene una referencia de paso no válida.", 409
            )
        if raw["id"] in seen:
            raise ApplicationError("INVALID_STEP_REFERENCE", "Identificador de paso repetido.", 409)
        seen.add(raw["id"])
        steps.append(
            PlanStepSpec(
                str(raw["id"]),
                str(raw["operation"]),
                int(raw["version"]),
                input_step,
                dict(raw.get("parameters", {})),
            )
        )
    if not steps:
        raise ApplicationError("EMPTY_PLAN", "El plan no contiene pasos.", 409)
    return steps
