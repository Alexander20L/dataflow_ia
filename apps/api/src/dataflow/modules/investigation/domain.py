"""Reglas puras de la investigación (`investigation-v1`): qué seguir y qué propuesta es válida.

Sin frameworks, proveedor ni base de datos. Una propuesta sólo se acepta si usa la medida del
plan, una agrupación aceptada por el plan y un mes, año o grupo presentes en los hallazgos.
"""

from typing import get_args

from dataflow.modules.analytics.contracts import (
    AutomaticAnalysis,
    AutomaticInsight,
    FollowUpKind,
    FollowUpQuery,
)
from dataflow.modules.investigation.contracts import Finding, RawProposal

KINDS: dict[FollowUpKind, str] = {
    "month_by_group": "En un mes con dato (month), qué grupos de una dimensión se apartan de su "
    "mediana mensual. Requiere dimension y month (AAAA-MM).",
    "change_by_group": "Reparto de la variación interanual de un año (year) entre los grupos de "
    "una dimensión, sólo con meses comparables. Requiere dimension y year.",
    "group_evolution": "Evolución mensual de un grupo (group) de una dimensión y su peso en el "
    "total. Requiere dimension y group.",
}
MAX_RULE_DIMENSIONS = 2


class Catalog:
    """Lo que se puede investigar en esta carga, derivado del plan y de los hallazgos."""

    def __init__(self, analysis: AutomaticAnalysis) -> None:
        plan = analysis.plan
        self.measure = plan.measure
        self.dimensions = [
            item.dimension for item in plan.accepted if item.kind == "breakdown" and item.dimension
        ]
        self.omitted = {
            item.dimension: item.reason
            for item in plan.omitted
            if item.kind == "breakdown" and item.dimension
        }
        insights = {insight.id: insight for insight in analysis.insights}
        evolution = insights.get("evolution:summary")
        self.months = (
            [point.label for point in evolution.chart.points]
            if evolution and evolution.chart
            else []
        )
        self.years = sorted(
            int(insight.id.split(":")[1])
            for insight in analysis.insights
            if insight.kind == "year_over_year" and insight.id.split(":")[1].isdigit()
        )
        self.groups: dict[str, list[str]] = {}
        for dimension in self.dimensions:
            summary = insights.get(f"breakdown:{dimension}:summary")
            if summary and summary.chart:
                self.groups[dimension] = [point.label for point in summary.chart.points]
        self.insights = analysis.insights

    def findings(self) -> list[Finding]:
        return [
            Finding(id=insight.id, title=insight.title, statement=insight.statement)
            for insight in self.insights
        ]


def anomaly_month(insight: AutomaticInsight) -> str | None:
    if insight.kind != "anomalies":
        return None
    month = insight.id.split(":", 1)[1]
    return month if len(month) == 7 and month[:4].isdigit() else None


def rule_queries(catalog: Catalog) -> list[tuple[FollowUpQuery, str]]:
    """Seguimientos fijos de los hallazgos (iteración 1), en orden de prioridad."""
    if not catalog.measure or not catalog.dimensions or not catalog.months:
        return []
    measure = catalog.measure
    dimensions = catalog.dimensions[:MAX_RULE_DIMENSIONS]
    found: list[tuple[FollowUpQuery, str]] = []
    for insight in catalog.insights:
        month = anomaly_month(insight)
        if month is None:
            continue
        for dimension in dimensions:
            found.append(
                (
                    FollowUpQuery(
                        kind="month_by_group", measure=measure, dimension=dimension, month=month
                    ),
                    f"Mes atípico {month}: qué grupos de {dimension} se apartan de su nivel "
                    "habitual.",
                )
            )
    for year in catalog.years:
        for dimension in dimensions:
            found.append(
                (
                    FollowUpQuery(
                        kind="change_by_group", measure=measure, dimension=dimension, year=year
                    ),
                    f"Variación interanual de {year}: qué grupos de {dimension} la explican.",
                )
            )
    first = catalog.dimensions[0]
    groups = catalog.groups.get(first, [])
    if groups:
        found.append(
            (
                FollowUpQuery(
                    kind="group_evolution", measure=measure, dimension=first, group=groups[0]
                ),
                f"Grupo principal de {first}: cómo evolucionó {groups[0]} mes a mes.",
            )
        )
    return found


def validate(
    raw: RawProposal, catalog: Catalog, done: set[str]
) -> tuple[FollowUpQuery | None, str | None]:
    """Convierte una propuesta en consulta del catálogo o explica por qué se rechaza."""
    if raw.kind not in get_args(FollowUpKind):
        return None, f"«{raw.kind}» no es un tipo de investigación del catálogo."
    if not catalog.measure:
        return None, "No hay una medida sumable que investigar."
    dimension = raw.dimension or ""
    if dimension not in catalog.dimensions:
        if dimension in catalog.omitted:
            return None, f"{dimension} no se usa para agrupar: {catalog.omitted[dimension]}"
        return None, f"«{dimension}» no es una agrupación válida del plan."
    if not catalog.months:
        return None, "No hay eje temporal: no se pueden seguir meses ni evoluciones."
    fields = {"month": raw.month, "year": raw.year, "group": raw.group}
    needed = {"month_by_group": "month", "change_by_group": "year", "group_evolution": "group"}[
        raw.kind
    ]
    if fields[needed] in (None, ""):
        return None, f"Falta el campo «{needed}»."
    if any(value not in (None, "") for name, value in fields.items() if name != needed):
        return None, f"Sólo se admite «{needed}» para este tipo."
    if needed == "month" and raw.month not in catalog.months:
        return None, f"El mes «{raw.month}» no tiene datos."
    if needed == "year" and raw.year not in catalog.years:
        return None, f"No hay comparación interanual válida para {raw.year}."
    if needed == "group" and raw.group not in catalog.groups.get(dimension, []):
        return None, f"«{raw.group}» no está entre los grupos principales de {dimension}."
    query = FollowUpQuery.model_validate(
        {
            "kind": raw.kind,
            "measure": catalog.measure,
            "dimension": dimension,
            needed: fields[needed],
        }
    )
    if query.key in done:
        return None, "Ya se investigó."
    return query, None
