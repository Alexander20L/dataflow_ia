"""Reglas puras de informes: estado de un bloque de datos y análisis admitidos."""

from dataflow.modules.dashboards.contracts import ExecutionFacts, PlanFacts
from dataflow.modules.reports.contracts import BlockStatus

ANALYSIS_OPERATIONS = ({"analytics.query@1"}, {"analytics.query@2"})


def analysis_problem(plan: PlanFacts) -> str | None:
    """Un bloque de análisis muestra un plan de un solo paso de `analytics.query`."""
    if len(plan.operations) != 1 or set(plan.operations) not in ANALYSIS_OPERATIONS:
        return "El bloque debe mostrar un análisis de un solo paso (analytics.query)."
    return None


def block_status(
    plan: PlanFacts, execution: ExecutionFacts | None
) -> tuple[BlockStatus, str | None]:
    """Estado de un bloque de datos. Un bloque con error nunca impide el resto del informe."""
    if not plan.valid:
        semantic = [m for code, m in plan.problems if code == "SEMANTIC_REQUIREMENT_MISSING"]
        if semantic:
            return "semantic_requirement_missing", semantic[0]
        return "invalid_plan", plan.problems[0][1] if plan.problems else None
    if execution is None:
        return "not_executed", "Actualiza los bloques para calcular este análisis."
    if execution.state in {"queued", "running"}:
        return "pending", None
    if execution.state != "succeeded":
        return "failed", execution.error_message or "La ejecución no terminó."
    if not execution.result_rows:
        return "insufficient_data", "El análisis no tiene filas con los datos de esta versión."
    return "ready", None
