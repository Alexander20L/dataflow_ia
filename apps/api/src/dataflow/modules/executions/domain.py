from typing import Any

from dataflow.modules.executions.contracts import InputKind, PlanStepSpec, RunState
from dataflow.platform.errors import ApplicationError


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
