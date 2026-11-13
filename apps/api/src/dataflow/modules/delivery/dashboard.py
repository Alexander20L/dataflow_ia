"""Dashboard adaptado a los datos (Fase 21, ADR-038, reglas `dashboard-design-v1`; Fase 26,
ADR-044, `dashboard-design-v2`).

Reglas puras: qué gráficos admite cada elemento publicado según su forma, cómo se valida el
diseño que propone la IA, el diseño por reglas cuando no hay IA y cómo se aplican las marcas
«sí va / no va» del usuario. El diseño nunca lleva cifras: cada gráfico señala un elemento
publicado (hallazgo o resultado de la exploración) y la interfaz pone sus datos.

Fase 26: qué calcula el propio dashboard (indicadores, histogramas, dispersión y los valores
que se pueden filtrar) como consultas del lenguaje cerrado que el motor calcula sobre todas las
filas; cómo se arman los indicadores con su unidad, periodo, comparación y procedencia; el
origen de cada gráfico; los filtros; y la validación de la versión personalizada.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from dataflow.modules.analytics.contracts import AutomaticEvidence, AutomaticInsight
from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.copilot.contracts import DisenoIA
from dataflow.modules.curation.contracts import (
    MAX_CUSTOM_WIDGETS,
    CustomSection,
    DashboardCustomization,
)
from dataflow.modules.delivery.contracts import (
    MAX_FILTER_VALUES,
    MAX_PIE_SLICES,
    MAX_SECTIONS,
    MAX_WIDGETS,
    Arrangement,
    Dashboard,
    DashboardFilterRequest,
    DashboardItem,
    DashboardSection,
    DashboardWidget,
    DesignDecision,
    DimensionFilter,
    FilterOptions,
    Indicator,
    IndicatorComparison,
    Trace,
    WidgetType,
)
from dataflow.modules.exploration.contracts import (
    Exploration,
    ExploreQuery,
    ExploreResult,
    InvestigationNode,
)

WIDGETS: dict[str, str] = {
    "kpi": "Indicador: una cifra publicada destacada",
    "bar": "Barras: una cifra por grupo",
    "line": "Líneas: una serie en el tiempo",
    "heatmap": "Mapa de calor: una cifra por cada par de grupos de dos dimensiones",
    "pie": "Circular: partes de un total que se puede sumar (de 2 a 6, sin negativos)",
    "table": "Tabla o tarjeta con el texto del hallazgo y sus cifras",
    "histogram": "Histograma: cuántos registros caen en cada intervalo de una medida",
    "scatter": "Dispersión: pares de dos medidas numéricas",
}
INCOMPATIBLE: dict[str, str] = {
    "kpi": "Un indicador necesita una cifra publicada de ese elemento.",
    "bar": "Un gráfico de barras necesita una cifra por grupo (al menos dos grupos).",
    "line": "Un gráfico de líneas necesita una serie en el tiempo.",
    "heatmap": "Un mapa de calor necesita dos dimensiones y una sola cifra.",
    "pie": (
        "Un gráfico circular necesita partes de un total que se puede sumar (de 2 a "
        f"{MAX_PIE_SLICES}, sin negativos)."
    ),
    "table": "Este elemento no se puede mostrar.",
    "histogram": "Un histograma necesita la distribución de una medida.",
    "scatter": "Un gráfico de dispersión necesita pares de dos medidas.",
}
KPI_COUNT = 4
MAX_HEATMAP_CELLS = 200  # más celdas no se leen en un mapa de calor
MAX_INDICATORS = 6
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def insight_key(insight: AutomaticInsight) -> str:
    return f"insight:{insight.id}"


def result_key(result: ExploreResult) -> str:
    return f"exploration:{result.key}"


def positive(values: Iterable[str | None]) -> bool:
    return all(value is not None and not value.startswith("-") for value in values)


def insight_item(insight: AutomaticInsight) -> DashboardItem:
    widgets: list[WidgetType] = []
    if insight.figures:
        widgets.append("kpi")
    chart = insight.chart
    points = chart.points if chart else []
    if chart is not None and len(points) >= 2:
        widgets.append("bar")
        if chart.type == "line":
            widgets.append("line")
        if (
            insight.kind == "breakdown"
            and chart.unit in {"number", "count"}
            and len(points) <= MAX_PIE_SLICES
            and positive(p.value for p in points)
        ):
            widgets.append("pie")
    widgets.append("table")
    return DashboardItem(
        id=insight_key(insight),
        origin="insight",
        title=insight.title,
        kind=insight.kind,
        widgets=widgets,
        figures=[figure.evidence_id for figure in insight.figures],
    )


def result_item(result: ExploreResult) -> DashboardItem:
    query = result.query
    dimensions = len(query.dimensions)
    single = bool(result.rows) and all(len(row.figures) == 1 for row in result.rows)
    widgets: list[WidgetType] = []
    figures: list[str] = []
    if dimensions == 0 and len(result.rows) == 1 and result.rows[0].figures:
        widgets.append("kpi")
        figures = [f.evidence_id for f in result.rows[0].figures]
    if dimensions == 1 and single and len(result.rows) >= 2:
        widgets.append("bar")
        if (
            query.kind == "aggregate"
            and query.aggregation in {"sum", "count"}
            and result.total_groups <= MAX_PIE_SLICES
            and positive(row.figures[0].value for row in result.rows)
        ):
            widgets.append("pie")
    if dimensions == 2 and single and result.total_groups <= MAX_HEATMAP_CELLS:
        widgets.append("heatmap")
    # Fase 25: la evolución mensual (`explore-v2`) es una serie en orden cronológico.
    if query.kind == "evolution" and single and len(result.rows) >= 2:
        widgets.extend(["line", "bar"])
    # Fase 26: histograma y dispersión (los calcula el dashboard).
    if query.kind == "distribution" and len(result.rows) >= 1:
        widgets = ["histogram", "bar"]
    if query.kind == "scatter" and len(result.rows) >= 2:
        widgets = ["scatter"]
    widgets.append("table")
    return DashboardItem(
        id=result_key(result),
        origin="exploration",
        title=result.title,
        kind=query.kind,
        widgets=widgets,
        figures=figures,
        groups=result.total_groups,
        filterable=True,
    )


def catalog(insights: list[AutomaticInsight], exploration: Exploration) -> list[DashboardItem]:
    """Hallazgos del análisis y resultados relevantes de la exploración, en su orden."""
    return [insight_item(i) for i in insights] + [
        result_item(r) for r in exploration.results if r.relevant
    ]


def safe_text(text: str | None, vocabulary: Iterable[str]) -> str | None:
    """El texto de la IA sin cifras propias: cada número debe aparecer en un nombre publicado
    (títulos de los elementos, que incluyen columnas y grupos). Si no, se descarta."""
    if text is None:
        return None
    cleaned = " ".join(text.split())[:200]
    if not cleaned:
        return None
    known = list(vocabulary)
    for number in NUMBER.findall(cleaned):
        if not any(number in word for word in known):
            return None
    return cleaned


def default_widget(item: DashboardItem) -> WidgetType:
    for preferred in ("line", "heatmap", "histogram", "scatter", "bar"):
        if preferred in item.widgets:
            return preferred
    return "table"


def shown(sections: list[DashboardSection]) -> set[str]:
    """Elementos que el diseño muestra con algo más que un indicador."""
    return {w.item for s in sections for w in s.widgets if w.type != "kpi"}


def complete(sections: list[DashboardSection], items: list[DashboardItem]) -> None:
    """La IA ordena y elige gráficos, pero no puede ocultar hallazgos: lo que no colocó va al
    final con su gráfico por defecto. Sólo el usuario descarta."""
    present = shown(sections)
    # Fase 26: lo que calcula el propio dashboard no es un hallazgo y puede no mostrarse.
    missing = [item for item in items if item.id not in present and item.origin != "computed"]
    if missing:
        sections.append(
            DashboardSection(
                title="Otros hallazgos",
                intro="Elementos publicados que el diseño no colocó.",
                widgets=[
                    DashboardWidget(type=default_widget(i), item=i.id, title=i.title)
                    for i in missing
                ],
            )
        )


def rules_design(
    insights: list[AutomaticInsight], items: list[DashboardItem]
) -> list[DashboardSection]:
    by_id = {item.id: item for item in items}
    ordered = sorted(insights, key=lambda insight: -insight.importance)
    kpis = [
        DashboardWidget(
            type="kpi",
            item=insight_key(i),
            title=i.figures[0].label,
            evidence_id=i.figures[0].evidence_id,
        )
        for i in ordered
        if i.figures
    ][:KPI_COUNT]
    sections: list[DashboardSection] = []
    if kpis:
        sections.append(DashboardSection(title="Indicadores clave", widgets=kpis))
    findings = [by_id[insight_key(i)] for i in ordered]
    if findings:
        sections.append(
            DashboardSection(
                title="Hallazgos principales",
                intro="Ordenados por importancia.",
                widgets=[
                    DashboardWidget(type=default_widget(i), item=i.id, title=i.title)
                    for i in findings
                ],
            )
        )
    explored = [item for item in items if item.origin == "exploration"]
    if explored:
        sections.append(
            DashboardSection(
                title="Exploración guiada",
                intro="Consultas relevantes calculadas sobre todas las filas.",
                widgets=[
                    DashboardWidget(type=default_widget(i), item=i.id, title=i.title)
                    for i in explored
                ],
            )
        )
    return sections


def validate_design(
    design: DisenoIA, items: list[DashboardItem]
) -> tuple[str | None, list[DashboardSection], list[DesignDecision]]:
    """Valida el diseño de la IA elemento a elemento; devuelve el título, las secciones
    aceptadas (completadas con lo que faltase) y cada decisión con su motivo."""
    by_id = {item.id: item for item in items}
    vocabulary = [item.title for item in items]
    decisions: list[DesignDecision] = []
    sections: list[DashboardSection] = []
    seen: set[tuple[str, str, str | None]] = set()
    count = 0
    for raw in design.secciones[:MAX_SECTIONS]:
        widgets: list[DashboardWidget] = []
        for element in raw.elementos:
            kind, identifier = element.grafico, element.elemento

            def reject(reason: str, kind: str = kind, identifier: str = identifier) -> None:
                decisions.append(
                    DesignDecision(item=identifier, type=kind, status="rejected", reason=reason)
                )

            item = by_id.get(identifier)
            if kind not in WIDGETS:
                reject("No es un gráfico del catálogo.")
                continue
            if item is None:
                reject("No es un elemento publicado.")
                continue
            if kind not in item.widgets:
                reject(INCOMPATIBLE[kind])
                continue
            evidence = None
            if kind == "kpi":
                evidence = element.cifra or (item.figures[0] if item.figures else None)
                if evidence not in item.figures:
                    reject(INCOMPATIBLE["kpi"])
                    continue
            if (identifier, kind, evidence) in seen:
                reject("Repetido.")
                continue
            if count >= MAX_WIDGETS:
                reject("Se alcanzó el máximo de elementos del dashboard.")
                continue
            seen.add((identifier, kind, evidence))
            count += 1
            widgets.append(
                DashboardWidget(
                    type=kind,
                    item=identifier,
                    title=safe_text(element.titulo, vocabulary) or item.title,
                    evidence_id=evidence,
                )
            )
            decisions.append(DesignDecision(item=identifier, type=kind, status="accepted"))
        if widgets:
            sections.append(
                DashboardSection(
                    title=safe_text(raw.titulo, vocabulary) or "Hallazgos",
                    intro=safe_text(raw.descripcion, vocabulary),
                    widgets=widgets,
                )
            )
    if sections:
        complete(sections, items)
    return safe_text(design.titulo, vocabulary), sections, decisions


def arrange(dashboard: Dashboard, verdicts: dict[str, str]) -> Arrangement:
    """Aplica las marcas: los fijados («keep») suben a «Fijados por ti» y los descartados
    («drop») salen del dashboard; el resto conserva el orden del diseño."""
    order: list[str] = []
    for section in dashboard.sections:
        for widget in section.widgets:
            if widget.item not in order:
                order.append(widget.item)
    pinned = [item for item in order if verdicts.get(item) == "keep"]
    hidden = [item for item in order if verdicts.get(item) == "drop"]
    moved = set(pinned) | set(hidden)
    sections: list[DashboardSection] = []
    if pinned:
        widgets = [w for s in dashboard.sections for w in s.widgets if w.item in pinned]
        widgets.sort(key=lambda w: pinned.index(w.item))
        sections.append(DashboardSection(title="Fijados por ti", widgets=widgets))
    for section in dashboard.sections:
        rest = [w for w in section.widgets if w.item not in moved]
        if rest:
            sections.append(section.model_copy(update={"widgets": rest}))
    return Arrangement(sections=sections, pinned=pinned, hidden=hidden)


def finding_order(
    dashboard: Dashboard | None, verdicts: dict[str, str]
) -> tuple[list[str], set[str], set[str]]:
    """Orden de los elementos para el informe: fijados, después el orden del dashboard; y los
    conjuntos de fijados y descartados."""
    if dashboard is None:
        return [], set(), set()
    arranged = arrange(dashboard, verdicts)
    order: list[str] = []
    for section in arranged.sections:
        for widget in section.widgets:
            if widget.item not in order:
                order.append(widget.item)
    return order, set(arranged.pinned), set(arranged.hidden)


# --- Fase 26 (`dashboard-design-v2`, ADR-044) ---------------------------------------------------

OPERATIONS = {
    "aggregate": "Agregación",
    "crosstab": "Tabla cruzada",
    "ratio": "Cociente",
    "top": "Ranking",
    "correlation_by_group": "Correlación por grupo",
    "evolution": "Serie temporal mensual",
    "period_change": "Comparación de periodos",
    "outliers": "Valores atípicos",
    "distribution": "Histograma",
    "scatter": "Dispersión",
}
AGGREGATION_WORDS = {"sum": "suma", "mean": "promedio", "median": "mediana", "count": "conteo"}
CLASS_ORDER = {"relevant": 0, "secondary": 1, "descriptive": 2, "inconclusive": 3, "discarded": 4}
MAX_DISTRIBUTIONS = 3
MAX_SCATTERS = 2
MAX_FILTER_DIMENSIONS = 3
PARTIAL = {
    "paused": "la pausaste",
    "cancelled": "la cancelaste",
    "max_seconds": "llegó al límite de tiempo",
}


def computed_key(query: ExploreQuery) -> str:
    return f"computed:{query.key}"


@dataclass(frozen=True)
class DashboardPlan:
    """Lo que calcula el dashboard sobre todas las filas: indicadores (totales, ranking y
    comparación con el mes anterior), la evolución de la medida principal, histogramas, pares de
    medidas asociadas y los valores de cada dimensión que se puede filtrar."""

    count: ExploreQuery
    totals: list[ExploreQuery]
    changes: dict[str, ExploreQuery]  # clave de la consulta total -> comparación de periodos
    top: ExploreQuery | None
    evolution: ExploreQuery | None
    distributions: list[ExploreQuery]
    scatters: list[ExploreQuery]
    filters: list[ExploreQuery]  # conteo por dimensión: los valores que se ofrecen

    def queries(self) -> list[ExploreQuery]:
        found: dict[str, ExploreQuery] = {}
        for query in [
            self.count,
            *self.totals,
            *self.changes.values(),
            *([self.top] if self.top else []),
            *([self.evolution] if self.evolution else []),
            *self.distributions,
            *self.scatters,
            *self.filters,
        ]:
            found.setdefault(query.key, query)
        return list(found.values())


def dashboard_plan(comprehension: Comprehension) -> DashboardPlan:
    """Las consultas del dashboard, por reglas, a partir de la comprensión: sólo se suman las
    medidas aditivas y sólo hay evolución y comparación si hay un periodo."""
    ratio = {s.column for s in comprehension.scales if s.scale == "ratio"}
    measures = [m for m in comprehension.measures if m.column in ratio]
    measures.sort(key=lambda m: (not m.monetary, m.derived))
    measures = measures[:3]
    temporal = comprehension.period is not None and comprehension.period.periods >= 2
    count = ExploreQuery(kind="aggregate", aggregation="count")
    totals = [
        ExploreQuery(
            kind="aggregate",
            measure=m.column,
            aggregation="sum" if m.aggregation == "sum" else "mean",
        )
        for m in measures
    ]
    changes: dict[str, ExploreQuery] = {}
    if temporal:
        for base in [count, *totals]:
            changes[base.key] = ExploreQuery(
                kind="period_change", measure=base.measure, aggregation=base.aggregation, limit=1
            )
    main = totals[0] if totals else count
    groupable = [d.column for d in comprehension.dimensions if d.groupable]
    if not groupable:
        groupable = [s.column for s in comprehension.scales if s.scale in {"nominal", "ordinal"}]
    excluded = {
        frozenset(r.columns) for r in comprehension.relationships if r.verdict == "not_relevant"
    }
    top = (
        ExploreQuery(
            kind="top",
            measure=main.measure,
            aggregation=main.aggregation,
            dimensions=[groupable[0]],
            limit=1,
        )
        if groupable
        else None
    )
    evolution = (
        ExploreQuery(kind="evolution", measure=main.measure, aggregation=main.aggregation)
        if temporal
        else None
    )
    scatters: list[ExploreQuery] = []
    for association in comprehension.associations:
        a, b = association.columns
        if (
            association.measure in {"pearson", "spearman"}
            and association.strength in {"moderate", "strong"}
            and {a, b} <= ratio
            and frozenset((a, b)) not in excluded
            and len(scatters) < MAX_SCATTERS
        ):
            scatters.append(ExploreQuery(kind="scatter", measure=a, measure_b=b))
    return DashboardPlan(
        count=count,
        totals=totals,
        changes=changes,
        top=top,
        evolution=evolution,
        distributions=[
            ExploreQuery(kind="distribution", measure=m.column)
            for m in measures[:MAX_DISTRIBUTIONS]
        ],
        scatters=scatters,
        filters=[
            ExploreQuery(kind="aggregate", aggregation="count", dimensions=[column])
            for column in groupable[:MAX_FILTER_DIMENSIONS]
        ],
    )


def computed_trace(
    result: ExploreResult,
    total_rows: int | None,
    period_columns: list[str],
    filters: list[str],
) -> Trace:
    query = result.query
    temporal = query.kind in {"evolution", "period_change"}
    return Trace(
        source="dashboard",
        operation=OPERATIONS.get(query.kind, query.kind),
        columns=[
            *(period_columns if temporal else []),
            *query.dimensions,
            *[m for m in (query.measure, query.measure_b) if m],
        ],
        measure=query.measure,
        grouping=["mes"] if query.kind == "evolution" else list(query.dimensions),
        aggregation=AGGREGATION_WORDS.get(query.aggregation or ""),
        period_columns=period_columns if temporal else [],
        rows=result.covered_rows,
        total_rows=total_rows,
        filters=filters,
        method=result.method,
    )


def node_trace(result: ExploreResult, node: InvestigationNode | None, filters: list[str]) -> Trace:
    query = result.query
    rows = result.covered_rows
    if node is not None and node.rows_considered is not None:
        rows = node.rows_considered
    return Trace(
        source="investigation",
        investigation=node.id if node else None,
        question=node.question if node else None,
        operation=node.method if node else OPERATIONS.get(query.kind, query.kind),
        columns=list(node.columns) if node else list(query.dimensions),
        measure=query.measure,
        grouping=["mes"] if query.kind == "evolution" else list(query.dimensions),
        aggregation=AGGREGATION_WORDS.get(query.aggregation or ""),
        rows=rows,
        total_rows=node.total_rows if node else None,
        filters=[*(node.filters if node else []), *filters],
        method=result.method,
    )


def insight_trace(insight: AutomaticInsight, evidence: Mapping[str, AutomaticEvidence]) -> Trace:
    methods = [evidence[f.evidence_id].method for f in insight.figures if f.evidence_id in evidence]
    return Trace(
        source="analysis",
        operation=insight.kind,
        method=methods[0] if methods else insight.coverage,
    )


def first_figure(result: ExploreResult | None) -> tuple[str, str] | None:
    """(valor, evidencia) de la primera cifra de la primera fila del resultado."""
    if result is None or not result.rows or not result.rows[0].figures:
        return None
    figure = result.rows[0].figures[0]
    return (figure.value, figure.evidence_id) if figure.value is not None else None


def comparison(result: ExploreResult | None) -> IndicatorComparison | None:
    """Último mes frente al anterior (una consulta `period_change` de un mes por ventana)."""
    if result is None or not result.rows or len(result.rows[0].figures) != 4:
        return None
    previous, current, change, percent = result.rows[0].figures
    months = [label.rsplit("(", 1)[-1].rstrip(")") for label in (previous.label, current.label)]
    return IndicatorComparison(
        label=f"{months[1]} frente a {months[0]}",
        previous=previous.value,
        current=current.value,
        change=change.value,
        change_percent=percent.value,
        evidence_id=change.evidence_id,
    )


def build_indicators(
    comprehension: Comprehension,
    plan: DashboardPlan,
    results: Mapping[str, ExploreResult],
    total_rows: int | None,
    reference: str,
    filters: list[str],
) -> list[Indicator]:
    """Indicadores del resumen ejecutivo con las cifras del motor: registros, total (o promedio)
    de cada medida principal, el grupo con mayor valor y el mes con mayor valor. La unidad sólo
    si la comprensión la declaró; la comparación sólo si hay dos meses con datos."""
    units = {m.column: m.unit for m in comprehension.measures}
    period_columns = list(comprehension.period.columns) if comprehension.period else []
    found: list[Indicator] = []

    def add(
        query: ExploreQuery,
        name: str,
        value: tuple[str, str],
        highlight: str | None = None,
        compared: IndicatorComparison | None = None,
    ) -> None:
        found.append(
            Indicator(
                id=f"{computed_key(query)}#{len(found)}",
                item=computed_key(query),
                name=name,
                value=value[0],
                highlight=highlight,
                unit=units.get(query.measure) if query.measure else None,
                reference=reference,
                comparison=compared,
                evidence_id=value[1],
                trace=computed_trace(results[query.key], total_rows, period_columns, filters),
            )
        )

    for query in [plan.count, *plan.totals]:
        figure = first_figure(results.get(query.key))
        if figure is None:
            continue
        change = plan.changes.get(query.key)
        name = (
            "Registros"
            if query.aggregation == "count"
            else f"{AGGREGATION_WORDS[query.aggregation or 'sum'].capitalize()} de {query.measure}"
        )
        add(query, name, figure, compared=comparison(results.get(change.key) if change else None))
    main = plan.totals[0] if plan.totals else plan.count
    what = (
        "registros"
        if main.aggregation == "count"
        else f"{AGGREGATION_WORDS[main.aggregation or 'sum']} de {main.measure}"
    )
    if plan.top is not None:
        top = results.get(plan.top.key)
        figure = first_figure(top)
        if top is not None and figure is not None:
            add(
                plan.top,
                f"{plan.top.dimensions[0]} con mayor {what}",
                figure,
                highlight=top.rows[0].groups[0],
            )
    if plan.evolution is not None:
        series = results.get(plan.evolution.key)
        points = [
            (row.groups[0], row.figures[0])
            for row in (series.rows if series else [])
            if row.figures and row.figures[0].value is not None
        ]
        if len(points) >= 2:
            month, best = max(points, key=lambda p: (Decimal(p[1].value or "0"), p[0]))
            add(
                plan.evolution,
                f"Mes con mayor {what}",
                (best.value or "", best.evidence_id),
                highlight=month,
            )
    return found[:MAX_INDICATORS]


def filter_options(
    comprehension: Comprehension, plan: DashboardPlan, results: Mapping[str, ExploreResult]
) -> FilterOptions:
    months: list[str] = []
    if plan.evolution is not None and plan.evolution.key in results:
        months = [row.groups[0] for row in results[plan.evolution.key].rows]
    dimensions = []
    for query in plan.filters:
        result = results.get(query.key)
        if result is None:
            continue
        values = [row.groups[0] for row in result.rows[:MAX_FILTER_VALUES]]
        dimensions.append(
            DimensionFilter(
                column=query.dimensions[0],
                values=values,
                more=max(0, result.total_groups - len(values)),
            )
        )
    period_columns = list(comprehension.period.columns) if comprehension.period else []
    return FilterOptions(
        months=months,
        period_columns=period_columns if months else [],
        dimensions=dimensions,
    )


def catalog_v2(
    insights: list[AutomaticInsight],
    evidence: Mapping[str, AutomaticEvidence],
    exploration: Exploration,
    computed: list[ExploreResult],
    indicators: list[Indicator],
    total_rows: int | None,
    period_columns: list[str],
) -> list[DashboardItem]:
    """Elementos del dashboard v2 con su origen: lo que calcula el dashboard (con las
    evidencias de sus indicadores), los resultados relevantes o secundarios de la investigación
    en el orden de su clase y prioridad, y los hallazgos del análisis automático."""
    nodes = {n.key: n for n in exploration.nodes if n.key}
    kpis: dict[str, list[str]] = {}
    for indicator in indicators:
        kpis.setdefault(indicator.item, []).append(indicator.evidence_id)
    items: list[DashboardItem] = []
    for result in computed:
        if result.query.kind == "period_change" or (
            result.query.kind == "aggregate" and result.query.dimensions
        ):
            continue  # comparaciones y valores de los filtros: sólo dentro de los indicadores
        item = result_item(result)
        figures = kpis.get(computed_key(result.query), [])
        widgets = list(item.widgets)
        if figures and "kpi" not in widgets:
            widgets.insert(0, "kpi")
        items.append(
            item.model_copy(
                update={
                    "id": computed_key(result.query),
                    "origin": "computed",
                    "widgets": widgets,
                    "figures": figures or item.figures,
                    "trace": computed_trace(result, total_rows, period_columns, []),
                }
            )
        )

    def rank(result: ExploreResult) -> tuple[int, int]:
        node = nodes.get(result.key)
        if node is None:
            return (1, 2)
        return (CLASS_ORDER.get(node.classification or "", 1), node.priority)

    for result in sorted((r for r in exploration.results if r.relevant), key=rank):
        node = nodes.get(result.key)
        items.append(
            result_item(result).model_copy(
                update={
                    "classification": node.classification if node else None,
                    "trace": node_trace(result, node, []),
                }
            )
        )
    for insight in insights:
        items.append(
            insight_item(insight).model_copy(update={"trace": insight_trace(insight, evidence)})
        )
    return items


def widgets_for(items: list[DashboardItem]) -> list[DashboardWidget]:
    return [DashboardWidget(type=default_widget(i), item=i.id, title=i.title) for i in items]


def rules_design_v2(
    insights: list[AutomaticInsight], items: list[DashboardItem], indicators: list[Indicator]
) -> list[DashboardSection]:
    """Sin IA: indicadores, evolución, hallazgos por importancia (relevantes de la
    investigación, después los del análisis), secundarios y distribuciones y relaciones."""
    by_id = {item.id: item for item in items}
    sections: list[DashboardSection] = []
    kpis = [
        DashboardWidget(type="kpi", item=i.item, title=i.name, evidence_id=i.evidence_id)
        for i in indicators
    ]
    if kpis:
        sections.append(DashboardSection(title="Indicadores clave", widgets=kpis))
    evolution = [i for i in items if i.origin == "computed" and i.kind == "evolution"]
    if evolution:
        sections.append(
            DashboardSection(
                title="Evolución",
                intro="Serie mensual calculada sobre todas las filas con periodo.",
                widgets=widgets_for(evolution),
            )
        )
    relevant = [i for i in items if i.origin == "exploration" and i.classification != "secondary"]
    ordered = [by_id[insight_key(i)] for i in sorted(insights, key=lambda i: -i.importance)]
    if relevant or ordered:
        sections.append(
            DashboardSection(
                title="Hallazgos principales",
                intro="Ordenados por importancia: primero los relevantes de la investigación.",
                widgets=widgets_for(relevant + ordered),
            )
        )
    secondary = [i for i in items if i.origin == "exploration" and i.classification == "secondary"]
    if secondary:
        sections.append(
            DashboardSection(title="Hallazgos secundarios", widgets=widgets_for(secondary))
        )
    shapes = [i for i in items if i.origin == "computed" and i.kind in {"distribution", "scatter"}]
    if shapes:
        sections.append(
            DashboardSection(
                title="Distribuciones y relaciones",
                intro="Cómo se reparten las medidas y cómo se relacionan entre sí.",
                widgets=widgets_for(shapes),
            )
        )
    return sections[:MAX_SECTIONS]


def partial_notice(exploration: Exploration) -> str | None:
    reason = PARTIAL.get(exploration.stopped or "")
    if reason is None:
        return None
    return (
        f"Resultados parciales: la investigación se detuvo antes de terminar ({reason}). "
        "Se muestra lo que se llegó a calcular."
    )


def sufficiency_notice(items: list[DashboardItem]) -> str | None:
    if any(item.origin != "computed" for item in items):
        return None
    if items:
        return (
            "No hay hallazgos suficientes: la investigación no encontró resultados relevantes, "
            "así que sólo se muestran indicadores y distribuciones calculados sobre todas las "
            "filas. No se inventan visualizaciones."
        )
    return "No hay datos suficientes para construir un dashboard: no se inventan visualizaciones."


# --- Filtros ---------------------------------------------------------------------------------


def filter_labels(request: DashboardFilterRequest) -> list[str]:
    labels: list[str] = []
    if request.period_from or request.period_to:
        labels.append(
            f"Periodo: {request.period_from or 'inicio'} a {request.period_to or 'último mes'}"
        )
    for category in request.categories:
        labels.append(f"{category.column}: {', '.join(category.values)}")
    return labels


def check_filters(request: DashboardFilterRequest, options: FilterOptions) -> str | None:
    """Motivo por el que los filtros no se pueden aplicar (o None)."""
    if (request.period_from or request.period_to) and not options.months:
        return "La tabla no tiene periodo: no se puede filtrar por meses."
    if request.period_from and request.period_to and request.period_from > request.period_to:
        return "El inicio del periodo es posterior a su final."
    allowed = {d.column for d in options.dimensions}
    columns = [c.column for c in request.categories]
    if len(set(columns)) != len(columns):
        return "Cada dimensión se filtra una sola vez."
    for column in columns:
        if column not in allowed:
            return f"«{column}» no es una dimensión que se pueda filtrar."
    return None


def reference_label(request: DashboardFilterRequest | None, months: list[str]) -> str:
    if request is not None and (request.period_from or request.period_to):
        start = request.period_from or (months[0] if months else "inicio")
        end = request.period_to or (months[-1] if months else "último mes")
        return f"{start} a {end}"
    if months:
        return f"{months[0]} a {months[-1]}"
    return "Todo el dataset"


# --- Versión personalizada ---------------------------------------------------------------------


def layout_errors(sections: list[CustomSection], items: list[DashboardItem]) -> list[str]:
    """Qué no es válido en la versión personalizada: cada gráfico debe señalar un elemento del
    dashboard automático con un gráfico compatible (un indicador, una de sus cifras)."""
    by_id = {item.id: item for item in items}
    errors: list[str] = []
    seen: set[tuple[str, str, str | None]] = set()
    count = 0
    for section in sections:
        for widget in section.widgets:
            item = by_id.get(widget.item)
            if item is None:
                errors.append(f"«{widget.item}» no está en el dashboard.")
                continue
            if widget.type not in item.widgets:
                errors.append(f"{item.title}: {INCOMPATIBLE.get(widget.type, 'gráfico no válido')}")
                continue
            if widget.type == "kpi" and widget.evidence_id not in item.figures:
                errors.append(f"{item.title}: {INCOMPATIBLE['kpi']}")
                continue
            if widget.type != "kpi" and widget.evidence_id is not None:
                errors.append(f"{item.title}: sólo un indicador lleva una cifra.")
                continue
            key = (widget.item, widget.type, widget.evidence_id)
            if key in seen:
                errors.append(f"{item.title}: repetido.")
                continue
            seen.add(key)
            count += 1
    if count > MAX_CUSTOM_WIDGETS:
        errors.append(f"Como mucho {MAX_CUSTOM_WIDGETS} gráficos.")
    return errors


def current_layout(
    custom: DashboardCustomization | None, items: list[DashboardItem]
) -> tuple[DashboardCustomization | None, int]:
    """La versión personalizada sin los gráficos que ya no están en el dashboard (si se volvió
    a generar) y cuántos se quitaron."""
    if custom is None:
        return None, 0
    by_id = {item.id: item for item in items}
    dropped = 0
    sections: list[CustomSection] = []
    for section in custom.sections:
        widgets = []
        for widget in section.widgets:
            item = by_id.get(widget.item)
            if (
                item is not None
                and widget.type in item.widgets
                and (widget.type != "kpi" or widget.evidence_id in item.figures)
            ):
                widgets.append(widget)
            else:
                dropped += 1
        if widgets:
            sections.append(section.model_copy(update={"widgets": widgets}))
    return custom.model_copy(update={"sections": sections}), dropped
