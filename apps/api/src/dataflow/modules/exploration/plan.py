"""Reglas puras de la investigación (`investigation-v2`, Fase 25, ADR-043): plan, árbol y
evaluación de cada resultado.

Sin Polars, SQL ni IA. El plan sale de la comprensión (medidas, dimensiones agrupables, periodo y
relaciones confirmadas); cada investigación nombra su pregunta, motivo, hipótesis, columnas,
método, resultado esperado, prioridad y dependencias. La clasificación (`relevance-v1`) usa sólo
las cifras del motor: magnitud del efecto, calidad (registros considerados), consistencia
(tamaño) y evidencia (método). La IA no clasifica: su juicio sólo puede rebajar un resultado.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.exploration.contracts import (
    Classification,
    Criterion,
    ExploreProposal,
    ExploreQuery,
    ExploreResult,
    InvestigationNode,
    RawQuery,
)
from dataflow.modules.exploration.domain import Catalog, clean_reason, rule_queries

RELEVANCE = "relevance-v1"
MIN_ROWS = 30  # por debajo, un resultado no es consistente
MIN_COVERAGE = Decimal("0.5")  # por debajo, la calidad de los datos rebaja el resultado
ORDER: list[Classification] = ["relevant", "secondary", "descriptive"]
CLASSES: dict[Classification, str] = {
    "relevant": "Hallazgo relevante",
    "secondary": "Hallazgo secundario",
    "descriptive": "Resultado descriptivo",
    "inconclusive": "Resultado no concluyente",
    "discarded": "Hipótesis descartada",
}
METHODS = {
    "aggregate": "Agregación por grupos",
    "crosstab": "Tabla cruzada",
    "ratio": "Cociente de sumas",
    "top": "Ranking de grupos",
    "correlation_by_group": "Correlación de Spearman por grupo",
    "evolution": "Serie temporal mensual",
    "period_change": "Comparación de periodos",
    "outliers": "Valores atípicos (regla de Tukey)",
}
AGGREGATION_WORDS = {"sum": "suma", "mean": "promedio", "median": "mediana", "count": "conteo"}


@dataclass(frozen=True)
class Draft:
    """Una investigación propuesta (por reglas o por la IA), todavía sin validar."""

    raw: RawQuery
    origin: str
    question: str
    motive: str
    hypothesis: str
    expected: str
    priority: int = 2
    depends_on: list[int] = field(default_factory=list)  # posiciones en la lista del plan


def number(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        found = Decimal(value)
    except InvalidOperation:
        return None
    return found if found.is_finite() else None


def percent(value: Decimal) -> str:
    return format((value * 100).quantize(Decimal("0.1")), "f")


def method_name(query: ExploreQuery) -> str:
    base = METHODS[query.kind]
    if query.aggregation and query.kind not in {"crosstab"}:
        return f"{base} ({AGGREGATION_WORDS[query.aggregation]})"
    return base


def query_columns(query: ExploreQuery | RawQuery) -> list[str]:
    names = [*query.dimensions, query.measure, query.measure_b, query.filter_column]
    return list(dict.fromkeys(n for n in names if n))


def primary_measure(comprehension: Comprehension, catalog: Catalog) -> str | None:
    """La medida principal: aditiva y monetaria si la hay, si no aditiva, si no la primera."""
    info = {m.column: m for m in comprehension.measures}
    ranked = sorted(
        catalog.measures,
        key=lambda name: (
            name not in catalog.additive,
            not (info[name].monetary if name in info else False),
            info[name].derived if name in info else False,
        ),
    )
    return ranked[0] if ranked else None


def aggregation_for(measure: str, catalog: Catalog) -> str:
    return "sum" if measure in catalog.additive else "mean"


def dimensions_for(catalog: Catalog) -> list[str]:
    return [d for d in catalog.dimensions if d in catalog.groupable]


def rule_plan(comprehension: Comprehension, catalog: Catalog) -> list[Draft]:
    """El plan por reglas, en orden de prioridad. Sin periodo no hay investigaciones temporales;
    sin medidas, sólo repartos de registros."""
    drafts: list[Draft] = []
    measure = primary_measure(comprehension, catalog)
    dimensions = dimensions_for(catalog)
    aggregation = aggregation_for(measure, catalog) if measure else "count"
    what = f"{measure}" if measure else "los registros"
    if catalog.period is not None:
        columns = " y ".join(catalog.period[1])
        drafts.append(
            Draft(
                RawQuery(kind="evolution", measure=measure, aggregation=aggregation),
                "rule",
                f"¿Cómo evoluciona {what} mes a mes?",
                f"Hay un periodo ({columns}): conviene ver la tendencia antes que los repartos.",
                f"{what} cambia a lo largo del tiempo.",
                "Una serie mensual con su tendencia y sus picos.",
                1,
            )
        )
        if catalog.periods >= 6:
            drafts.append(
                Draft(
                    RawQuery(
                        kind="period_change", measure=measure, aggregation=aggregation, limit=3
                    ),
                    "rule",
                    f"¿Cambió {what} en los últimos tres meses frente a los tres anteriores?",
                    "Un cambio reciente es lo primero que conviene explicar.",
                    f"{what} de los últimos meses es distinto del de los anteriores.",
                    "Las dos ventanas comparadas, sus importes y la variación.",
                    2,
                    [0],
                )
            )
    for position, dimension in enumerate(dimensions[:2]):
        if measure:
            drafts.append(
                Draft(
                    RawQuery(
                        kind="top",
                        measure=measure,
                        dimensions=[dimension],
                        aggregation=aggregation,
                        limit=10,
                    ),
                    "rule",
                    f"¿Qué {dimension} concentra más {measure}?",
                    f"{dimension} es una dimensión agrupable y {measure} la medida principal.",
                    f"{measure} se concentra en pocos grupos de {dimension}.",
                    f"Un ranking de {dimension} por {measure} con el peso de cada grupo.",
                    1 if position == 0 else 2,
                )
            )
        else:
            drafts.append(
                Draft(
                    RawQuery(kind="aggregate", dimensions=[dimension], aggregation="count"),
                    "rule",
                    f"¿Cómo se reparten los registros por {dimension}?",
                    "No hay medidas numéricas: se describe el reparto de los registros.",
                    f"Los registros no se reparten por igual entre los grupos de {dimension}.",
                    f"El número de registros de cada {dimension}.",
                    2,
                )
            )
    for raw, motive in rule_queries(comprehension, catalog):
        names = query_columns(raw)
        drafts.append(
            Draft(
                raw,
                "rule",
                f"¿Cómo se relacionan {' y '.join(names)}?",
                motive,
                "La relación confirmada por los datos se aprecia al agrupar.",
                "Las cifras de cada grupo para comparar la relación.",
                2,
            )
        )
    if measure:
        drafts.append(
            Draft(
                RawQuery(kind="outliers", measure=measure),
                "rule",
                f"¿Hay valores inusuales de {measure}?",
                "Los valores extremos pueden distorsionar sumas y promedios.",
                f"Algunos registros de {measure} se apartan mucho del resto.",
                "Cuántos valores quedan fuera de la regla de Tukey.",
                3,
            )
        )
    return drafts


def ai_draft(raw: RawQuery, columns: Sequence[str]) -> Draft:
    """Una propuesta de la IA como investigación. Los textos con cifras propias se retiran."""
    allowed = [*columns, *query_columns(raw)]

    def clean(text: str, fallback: str) -> str:
        return clean_reason(text, allowed) or fallback

    motive = clean(raw.motive, "Propuesta de la IA.")
    return Draft(
        raw,
        "ai",
        clean(raw.question, motive),
        motive,
        clean(raw.hypothesis, "Sin hipótesis declarada."),
        clean(raw.expected, "Sin resultado esperado declarado."),
        raw.priority if raw.priority in {1, 2, 3} else 2,
        list(raw.depends_on),
    )


def node(
    identifier: str,
    draft: Draft,
    query: ExploreQuery | None,
    reason: str | None,
    parent: str | None = None,
    depends_on: list[str] | None = None,
) -> InvestigationNode:
    used = query or draft.raw
    return InvestigationNode(
        id=identifier,
        parent=parent,
        depth=identifier.count("."),
        origin="ai" if draft.origin == "ai" else "rule",
        question=draft.question,
        motive=draft.motive,
        hypothesis=draft.hypothesis,
        expected=draft.expected,
        columns=query_columns(used),
        method=method_name(query) if query else METHODS.get(draft.raw.kind, draft.raw.kind),
        priority=draft.priority if draft.priority in {1, 2, 3} else 2,
        depends_on=depends_on or [],
        query=(query.model_dump(mode="json", exclude_none=True) if query else None)
        or draft.raw.model_dump(
            mode="json",
            exclude_none=True,
            include={
                "kind",
                "measure",
                "measure_b",
                "dimensions",
                "aggregation",
                "filter_column",
                "filter_value",
                "limit",
            },
        ),
        key=query.key if query else None,
        status="pending" if query else "rejected",
        reason=reason,
        filters=[f"{used.filter_column} = {used.filter_value}"] if used.filter_column else [],
        classification="discarded" if query is None else None,
        decision="finish" if query is None else None,
        decision_reason="Hipótesis descartada antes de calcular: " + (reason or "no es válida.")
        if query is None
        else None,
    )


# --- Evaluación (`relevance-v1`) -----------------------------------------------------------------


def main_values(result: ExploreResult, index: int = -1) -> list[tuple[str, Decimal]]:
    found = []
    for row in result.rows:
        if not row.figures:
            continue
        value = number(row.figures[index].value)
        if value is not None:
            found.append((" · ".join(row.groups) or "Total", value))
    return found


def spread(values: list[tuple[str, Decimal]]) -> tuple[Decimal, str, str] | None:
    """Diferencia entre el grupo más alto y el más bajo respecto al promedio de los grupos."""
    if len(values) < 2:
        return None
    high = max(values, key=lambda item: item[1])
    low = min(values, key=lambda item: item[1])
    mean = sum((v for _, v in values), Decimal(0)) / len(values)
    if mean == 0:
        return None
    return (high[1] - low[1]) / abs(mean), high[0], low[0]


def magnitude(query: ExploreQuery, result: ExploreResult) -> tuple[Classification, str]:
    """Clase por la magnitud del efecto y el texto que la justifica (cifras del motor)."""
    kind = query.kind
    if kind in {"aggregate", "top"} and query.aggregation in {"sum", "count"}:
        values = [(g, v) for g, v in main_values(result) if v > 0]
        total = sum((v for _, v in values), Decimal(0))
        groups = len(values)
        if groups < 2 or total == 0:
            return "inconclusive", "Hay menos de dos grupos con valor: no se puede comparar."
        leader, top = values[0]
        share = top / total
        even = Decimal(1) / groups
        ratio = share / even
        scope = f"entre los {groups} primeros" if kind == "top" else f"entre {groups} grupos"
        text = (
            f"{leader} reúne el {percent(share)} % del total {scope}; con un reparto parejo "
            f"sería el {percent(even)} %."
        )
        if ratio >= 2 and query.aggregation == "sum":
            return "relevant", text
        if ratio >= Decimal("1.3"):
            return "secondary", text
        return "descriptive", text + " El reparto es bastante parejo."
    if kind in {"aggregate", "top", "ratio"}:
        if not query.dimensions:
            return "descriptive", "Una sola cifra para el total: describe, no compara."
        found = spread(main_values(result))
        if found is None:
            return "inconclusive", "No hay al menos dos grupos con un valor comparable."
        gap, high, low = found
        text = (
            f"Entre el grupo más alto ({high}) y el más bajo ({low}) hay una diferencia del "
            f"{percent(gap)} % respecto al promedio de los grupos."
        )
        if gap >= Decimal("0.5"):
            return "relevant", text
        if gap >= Decimal("0.15"):
            return "secondary", text
        return "discarded", text + " Los grupos tienen valores parecidos."
    if kind == "crosstab":
        return "descriptive", f"Tabla cruzada de {result.total_groups} combinaciones."
    if kind == "correlation_by_group":
        values = main_values(result)
        if not values:
            return "inconclusive", "Ningún grupo tiene filas suficientes para la correlación."
        group, rho = max(values, key=lambda item: abs(item[1]))
        text = f"La correlación más fuerte es la de {group} (Spearman {rho})."
        if abs(rho) >= Decimal("0.5"):
            return "relevant", text
        if abs(rho) >= Decimal("0.3"):
            return "secondary", text
        return "discarded", text + " La asociación es débil en todos los grupos."
    if kind == "evolution":
        series = main_values(result)
        if len(series) < 3:
            return "inconclusive", "Hacen falta al menos tres meses con valor para una tendencia."
        (first_month, first), (last_month, last) = series[0], series[-1]
        if first == 0:
            return "descriptive", f"La serie empieza en cero ({first_month})."
        change = (last - first) / abs(first)
        text = (
            f"De {first_month} a {last_month} la serie cambia un {percent(change)} % "
            f"({len(series)} meses)."
        )
        if abs(change) >= Decimal("0.2"):
            return "relevant", text
        if abs(change) >= Decimal("0.05"):
            return "secondary", text
        return "descriptive", text + " La serie es estable."
    if kind == "period_change":
        values = main_values(result)  # «Variación %»
        if not values:
            return "inconclusive", "No hay una variación comparable entre las dos ventanas."
        group, change = (
            values[0] if not query.dimensions else max(values, key=lambda item: abs(item[1]))
        )
        where = "" if not query.dimensions else f" (mayor en {group})"
        text = f"La variación entre las dos ventanas es del {change} %{where}."
        if abs(change) >= 10:
            return "relevant", text
        if abs(change) >= 3:
            return "secondary", text
        return "discarded", text + " No hay un cambio apreciable."
    if kind == "outliers":
        counted = [
            (number(row.figures[4].value), row.rows)
            for row in result.rows
            if len(row.figures) >= 6 and row.figures[4].value is not None
        ]
        if not counted:
            return "inconclusive", "Ningún grupo tiene al menos cuatro valores."
        atypical = sum((c or Decimal(0) for c, _ in counted), Decimal(0))
        rows = sum(r for _, r in counted)
        share = atypical / rows if rows else Decimal(0)
        text = f"{atypical} de {rows} valores ({percent(share)} %) quedan fuera de la regla."
        if share >= Decimal("0.05"):
            return "relevant", text
        if atypical > 0:
            return "secondary", text
        return "discarded", text + " No hay valores atípicos."
    return "descriptive", "Resultado descriptivo."


def lower(classification: Classification) -> Classification:
    if classification in ORDER and classification != "descriptive":
        return ORDER[ORDER.index(classification) + 1]
    return classification


def evaluate(
    query: ExploreQuery, result: ExploreResult, total_rows: int
) -> tuple[Classification, list[Criterion], list[str]]:
    """Clase, criterios y limitaciones de un resultado calculado."""
    classification, text = magnitude(query, result)
    criteria = [Criterion(name="magnitude", assessment=text)]
    limitations: list[str] = []
    considered = result.covered_rows
    if query.filter_column:
        quality = (
            f"Se consideraron {considered} registros con {query.filter_column} = "
            f"{query.filter_value} y valor en las columnas usadas."
        )
    else:
        quality = f"Se consideraron {considered} de {total_rows} registros."
        missing = total_rows - considered
        if missing > 0:
            limitations.append(
                f"Se excluyeron {missing} registros sin valor en las columnas usadas "
                "(o sin periodo reconocible)."
            )
            if total_rows and Decimal(considered) / total_rows < MIN_COVERAGE:
                classification = lower(classification)
                quality += " Menos de la mitad: la calidad de los datos rebaja el resultado."
    criteria.append(Criterion(name="quality", assessment=quality))
    if considered < MIN_ROWS and classification in {"relevant", "secondary"}:
        criteria.append(
            Criterion(
                name="consistency",
                assessment=f"Pocos registros ({considered}): el resultado puede no ser estable.",
            )
        )
        classification = lower(classification)
    else:
        criteria.append(
            Criterion(
                name="consistency",
                assessment=f"{result.total_groups} grupos o puntos con {considered} registros.",
            )
        )
    criteria.append(Criterion(name="evidence", assessment=result.method))
    if result.truncated:
        limitations.append(f"Se guardan {len(result.rows)} de {result.total_groups} grupos.")
    if query.kind in {"aggregate", "top", "ratio", "crosstab", "correlation_by_group"}:
        limitations.append("Una diferencia entre grupos o una correlación no es una causa.")
    return classification, criteria, limitations


def unanswerable(reason: str) -> tuple[Classification, list[Criterion]]:
    return "inconclusive", [Criterion(name="evidence", assessment=reason)]


# --- Investigaciones secundarias (árbol) --------------------------------------------------------


def rule_children(
    item: InvestigationNode, query: ExploreQuery, result: ExploreResult, catalog: Catalog
) -> list[Draft]:
    """Preguntas secundarias de un resultado interesante, en orden de prioridad."""
    if not result.rows or not result.rows[0].groups:
        leader = None
    else:
        leader = result.rows[0].groups[0]
    dimensions = dimensions_for(catalog)
    drafts: list[Draft] = []
    measure, aggregation = query.measure, query.aggregation
    if query.kind in {"aggregate", "top"} and len(query.dimensions) == 1 and leader:
        dimension = query.dimensions[0]
        if measure and aggregation in {"sum", "mean", "median"}:
            others = [
                m
                for m in catalog.measures
                if m != measure and (aggregation != "sum" or m in catalog.additive)
            ]
            if others:
                other = others[0]
                drafts.append(
                    Draft(
                        RawQuery(
                            kind="aggregate",
                            measure=other,
                            dimensions=[dimension],
                            aggregation=aggregation_for(other, catalog),
                        ),
                        "rule",
                        f"¿{leader} también destaca en {other}?",
                        f"{leader} lidera en {measure}: ver si es por volumen o por valor.",
                        f"El grupo con más {measure} también lidera en {other}.",
                        f"{other} de cada {dimension}.",
                        2,
                    )
                )
        if catalog.period is not None:
            drafts.append(
                Draft(
                    RawQuery(
                        kind="evolution",
                        measure=measure,
                        aggregation=aggregation or "count",
                        filter_column=dimension,
                        filter_value=leader,
                    ),
                    "rule",
                    f"¿Cómo evolucionó {measure or 'el número de registros'} en {leader}?",
                    f"{leader} es el grupo principal de {dimension}.",
                    f"El peso de {leader} cambia con el tiempo.",
                    f"La serie mensual de {leader}.",
                    2,
                )
            )
        for other in dimensions:
            if other in {dimension, query.filter_column}:
                continue
            drafts.append(
                Draft(
                    RawQuery(
                        kind="aggregate",
                        measure=measure,
                        dimensions=[other],
                        aggregation=aggregation or "count",
                        filter_column=dimension,
                        filter_value=leader,
                    ),
                    "rule",
                    f"¿Cómo se reparte {measure or 'el número de registros'} de {leader} "
                    f"según {other}?",
                    f"Ver si la concentración en {leader} afecta a todas las {other}.",
                    f"Dentro de {leader}, {other} no se reparte por igual.",
                    f"{measure or 'Registros'} de {leader} por {other}.",
                    3,
                )
            )
            break
    elif query.kind == "evolution" and not query.dimensions:
        for dimension in dimensions:
            if dimension == query.filter_column or catalog.periods < 6:
                continue
            drafts.append(
                Draft(
                    RawQuery(
                        kind="period_change",
                        measure=measure,
                        dimensions=[dimension],
                        aggregation=aggregation,
                        filter_column=query.filter_column,
                        filter_value=query.filter_value,
                        limit=3,
                    ),
                    "rule",
                    f"¿Qué {dimension} explica el cambio reciente?",
                    "La serie cambia: ver qué grupos lo explican.",
                    f"El cambio se concentra en algunos grupos de {dimension}.",
                    f"La variación de cada {dimension} entre las dos ventanas.",
                    2,
                )
            )
            break
    elif query.kind == "period_change":
        if not query.dimensions:
            for dimension in dimensions:
                if dimension == query.filter_column:
                    continue
                drafts.append(
                    Draft(
                        RawQuery(
                            kind="period_change",
                            measure=measure,
                            dimensions=[dimension],
                            aggregation=aggregation,
                            limit=query.limit,
                        ),
                        "rule",
                        f"¿El cambio afecta a todos los grupos de {dimension}?",
                        "Hay un cambio entre las dos ventanas.",
                        f"El cambio se concentra en algunos grupos de {dimension}.",
                        f"La variación de cada {dimension}.",
                        2,
                    )
                )
                break
        elif leader:
            drafts.append(
                Draft(
                    RawQuery(
                        kind="evolution",
                        measure=measure,
                        aggregation=aggregation,
                        filter_column=query.dimensions[0],
                        filter_value=leader,
                    ),
                    "rule",
                    f"¿En qué meses se concentra el cambio de {leader}?",
                    f"{leader} es el grupo con mayor variación.",
                    "El cambio se concentra en determinados meses.",
                    f"La serie mensual de {leader}.",
                    2,
                )
            )
    elif query.kind == "outliers" and not query.dimensions and measure:
        for dimension in dimensions:
            drafts.append(
                Draft(
                    RawQuery(kind="outliers", measure=measure, dimensions=[dimension]),
                    "rule",
                    f"¿Se concentran los valores atípicos de {measure} en algún {dimension}?",
                    "Hay valores atípicos: ver dónde aparecen.",
                    f"Los valores atípicos se concentran en algunos grupos de {dimension}.",
                    f"Los valores atípicos de cada {dimension}.",
                    3,
                )
            )
            break
    return drafts


def proposals(nodes: Sequence[InvestigationNode]) -> list[ExploreProposal]:
    """Las investigaciones como propuestas de `explore-v1` (lo que leen el dashboard y el
    informe)."""
    return [
        ExploreProposal(
            origin=item.origin,
            query=dict(item.query),
            motive=item.question,
            status="rejected" if item.status == "rejected" else "accepted",
            reason=item.reason if item.status == "rejected" else None,
            key=item.key if item.status != "rejected" else None,
        )
        for item in nodes
    ]


def projected(item: InvestigationNode, result: ExploreResult) -> ExploreResult:
    """El resultado con su relevancia para el dashboard y el informe: relevantes y secundarios
    se muestran; descriptivos sin juicio; no concluyentes y descartados, no."""
    classification = item.classification
    relevant = (
        True
        if classification in {"relevant", "secondary"}
        else None
        if classification == "descriptive"
        else False
    )
    reason = item.interpretation or (item.criteria[0].assessment if item.criteria else None)
    label = CLASSES[classification] if classification else None
    return result.model_copy(
        update={
            "relevant": relevant,
            "judged_by": "ai" if item.interpretation else "rules",
            "reason": f"{label}. {reason}" if label and reason else reason,
        }
    )
