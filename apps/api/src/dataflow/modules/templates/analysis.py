"""Dashboard automático de cada molde (Fase 11E): métricas, consultas y tarjetas como datos
puros. Reutiliza analytics (métricas, `analytics.query@2`/`@3`, evidencia por cifra) y la
persistencia de dashboards; aquí sólo se describe qué calcular y cómo mostrarlo.

Reglas: orden estable de tarjetas; nada de «sin datos» como cero (lo garantiza analytics); no se
mezclan monedas y unidades en una consulta (`UNIT_MISMATCH`); el inventario usa el **último
corte** de cada periodo y nunca suma cortes entre fechas.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from dataflow.modules.templates.contracts import MappingContent

ANALYSIS_VERSION = "template-analysis@1"


@dataclass(frozen=True)
class MetricSpec:
    name: str
    draft: dict[str, Any]  # MetricDraft con IDs de columna


@dataclass(frozen=True)
class CardSpec:
    name: str
    title: str
    view: str  # kpi | line | bar | table
    size: str  # small | medium | large
    metric: int = 0  # índice de la métrica de la consulta que se dibuja


@dataclass(frozen=True)
class QuerySpec:
    name: str
    version: int  # 2 o 3 (analytics.query)
    metrics: list[str]  # nombres de MetricSpec
    parameters: dict[str, Any]  # sin «metrics»; «metric:x» se sustituye por su revisión
    cards: list[CardSpec] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisSpec:
    template: str
    title: str
    metrics: list[MetricSpec]
    queries: list[QuerySpec]


def ranking(metric: str, top: int, direction: str = "desc") -> dict[str, Any]:
    return {"metric_revision_id": f"metric:{metric}", "direction": direction, "top_n": top}


def analysis_spec(content: MappingContent, ids: dict[str, UUID]) -> AnalysisSpec | None:
    """`ids`: nombre de columna → ID en la tabla que se analiza. None para el molde genérico."""
    role = {item.role: ids[item.column] for item in content.roles if item.column in ids}
    names = {item.role: item.column for item in content.roles}
    if content.template == "sales@1":
        date, amount, dimension = role["date"], role["amount"], role["dimension"]
        base = {"measure_column_id": str(amount), "time_column_id": str(date)}
        return AnalysisSpec(
            template="sales@1",
            title="Ventas · automático",
            metrics=[
                MetricSpec("total", {**base, "label": "Ventas totales", "aggregation": "sum"}),
                MetricSpec("count", {**base, "label": "Operaciones", "aggregation": "count"}),
                MetricSpec("ticket", {**base, "label": "Ticket promedio", "aggregation": "avg"}),
            ],
            queries=[
                QuerySpec(
                    "kpis",
                    2,
                    ["total", "count", "ticket"],
                    {},
                    [
                        CardSpec("kpi_total", "Ventas totales", "kpi", "small", 0),
                        CardSpec("kpi_count", "Operaciones", "kpi", "small", 1),
                        CardSpec("kpi_ticket", "Ticket promedio", "kpi", "small", 2),
                    ],
                ),
                QuerySpec(
                    "monthly",
                    2,
                    ["total"],
                    {"time_grain": "month"},
                    [CardSpec("line_month", "Ventas por mes", "line", "large")],
                ),
                QuerySpec(
                    "top",
                    2,
                    ["total"],
                    {
                        "dimensions": [str(dimension)],
                        "ranking": ranking("total", 10),
                        "share_of_total": ["metric:total"],
                    },
                    [CardSpec("bar_top", f"Top 10 por {names['dimension']}", "bar", "medium")],
                ),
                QuerySpec(
                    "detail",
                    2,
                    ["total", "count"],
                    {"dimensions": [str(dimension)], "ranking": ranking("total", 20)},
                    [
                        CardSpec(
                            "table_detail", f"Detalle por {names['dimension']}", "table", "large"
                        )
                    ],
                ),
            ],
        )
    if content.template == "inventory@1":
        product, quantity, cut = role["product"], role["quantity"], role["cut_date"]
        snapshot = {"time_column_id": str(cut), "semi_additive": "last_snapshot"}
        metrics = [
            MetricSpec(
                "units",
                {
                    **snapshot,
                    "label": "Unidades en inventario",
                    "measure_column_id": str(quantity),
                    "aggregation": "sum",
                },
            ),
            MetricSpec(
                "products",
                {
                    "label": "Productos",
                    "measure_column_id": str(product),
                    "aggregation": "count_distinct",
                    "time_column_id": str(cut),
                },
            ),
        ]
        queries = [
            QuerySpec(
                "kpis_units",
                3,
                ["units", "products"],
                {},
                [
                    CardSpec("kpi_units", "Unidades en inventario", "kpi", "small", 0),
                    CardSpec("kpi_products", "Productos", "kpi", "small", 1),
                ],
            )
        ]
        ranked = "units"
        if "unit_cost" in role:
            ranked = "value"
            metrics.append(
                MetricSpec(
                    "value",
                    {
                        **snapshot,
                        "label": "Valor del inventario",
                        "measure_column_id": str(quantity),
                        "second_measure_column_id": str(role["unit_cost"]),
                        "aggregation": "sum_product",
                    },
                )
            )
            # Moneda e unidad no se mezclan en una consulta: el valor va en la suya.
            queries.append(
                QuerySpec(
                    "kpi_value",
                    3,
                    ["value"],
                    {},
                    [CardSpec("kpi_value", "Valor del inventario", "kpi", "small", 0)],
                )
            )
        queries.append(
            QuerySpec(
                "top_products",
                3,
                [ranked],
                {"dimensions": [str(product)], "ranking": ranking(ranked, 10)},
                [CardSpec("bar_products", f"Top 10 {names['product']}", "bar", "medium")],
            )
        )
        detail = role.get("location", product)
        queries.append(
            QuerySpec(
                "detail",
                3,
                ["units"],
                {"dimensions": [str(detail)], "ranking": ranking("units", 20, "asc")},
                [
                    CardSpec(
                        "table_detail",
                        f"Menor stock por {names.get('location', names['product'])}",
                        "table",
                        "large",
                    )
                ],
            )
        )
        return AnalysisSpec("inventory@1", "Inventario · automático", metrics, queries)
    return None


def resolve(parameters: dict[str, Any], revisions: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Sustituye «metric:x» por la revisión creada (`{revision_id, content_sha256}`)."""

    def value(item: Any) -> Any:
        if isinstance(item, str) and item.startswith("metric:"):
            return revisions[item.removeprefix("metric:")]["revision_id"]
        if isinstance(item, dict):
            return {k: value(v) for k, v in item.items()}
        if isinstance(item, list):
            return [value(v) for v in item]
        return item

    return {k: value(v) for k, v in parameters.items()}
