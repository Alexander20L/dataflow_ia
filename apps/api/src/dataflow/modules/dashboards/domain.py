"""Reglas puras de dashboards: forma de cada tarjeta, su estado y los filtros aplicables."""

from uuid import UUID

from dataflow.modules.dashboards.contracts import (
    CARD_OPERATION,
    Card,
    CardStatus,
    ExecutionFacts,
    FilterApplicability,
    GlobalFilter,
    PlanFacts,
)


def query_shape(plan: PlanFacts) -> tuple[list[UUID], str | None, int]:
    """Dimensiones, agrupación temporal y número de métricas de la consulta del plan."""
    parameters = plan.parameters
    dimensions = [UUID(str(d)) for d in parameters.get("dimensions") or []]
    return dimensions, parameters.get("time_grain"), len(parameters.get("metrics") or [])


def card_problems(card: Card, plan: PlanFacts) -> list[str]:
    """Una tarjeta sólo muestra `analytics.query@2` y su forma debe encajar con la consulta:
    KPI de una sola fila, líneas con agrupación temporal y barras con un único eje."""
    if plan.operations != [CARD_OPERATION]:
        return ["La tarjeta debe mostrar un análisis de un solo paso (analytics.query@2)."]
    dimensions, grain, metrics = query_shape(plan)
    problems = []
    if int(card.metric[1:]) >= metrics:
        problems.append(f"La consulta no tiene la métrica «{card.metric}».")
    if card.view == "kpi" and (dimensions or grain):
        problems.append(
            "Un KPI necesita un resultado de una sola fila (sin dimensiones ni tiempo)."
        )
    if card.view == "line" and not grain:
        problems.append("Un gráfico de líneas necesita agrupar por tiempo.")
    if card.view == "bar" and len(dimensions) + (1 if grain else 0) != 1:
        problems.append("Un gráfico de barras necesita una sola dimensión o sólo el periodo.")
    return problems


def card_status(plan: PlanFacts, execution: ExecutionFacts | None) -> tuple[CardStatus, str | None]:
    """Estado de una tarjeta. Un error de una tarjeta nunca rompe las demás."""
    if not plan.valid:
        semantic = [m for code, m in plan.problems if code == "SEMANTIC_REQUIREMENT_MISSING"]
        if semantic:
            return "semantic_requirement_missing", semantic[0]
        return "invalid_plan", plan.problems[0][1] if plan.problems else None
    if execution is None:
        return "not_executed", "Actualiza el dashboard para calcular esta tarjeta."
    if execution.state in {"queued", "running"}:
        return "pending", None
    if execution.state != "succeeded":
        return "failed", execution.error_message or "La ejecución no terminó."
    if not execution.result_rows:
        return "insufficient_data", "El análisis no tiene filas con los datos de esta versión."
    return "ready", None


def filter_applicability(filters: list[GlobalFilter], plan: PlanFacts) -> list[FilterApplicability]:
    """Un filtro global sólo se aplica si la consulta agrupa por esa dimensión."""
    dimensions = set(query_shape(plan)[0])
    return [
        FilterApplicability(column_id=f.column_id, applicable=f.column_id in dimensions)
        for f in filters
    ]
