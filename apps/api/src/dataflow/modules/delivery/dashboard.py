"""Dashboard adaptado a los datos (Fase 21, ADR-038, reglas `dashboard-design-v1`).

Reglas puras: qué gráficos admite cada elemento publicado según su forma, cómo se valida el
diseño que propone la IA, el diseño por reglas cuando no hay IA y cómo se aplican las marcas
«sí va / no va» del usuario. El diseño nunca lleva cifras: cada gráfico señala un elemento
publicado (hallazgo o resultado de la exploración) y la interfaz pone sus datos.
"""

import re
from collections.abc import Iterable

from dataflow.modules.analytics.contracts import AutomaticInsight
from dataflow.modules.copilot.contracts import DisenoIA
from dataflow.modules.delivery.contracts import (
    MAX_PIE_SLICES,
    MAX_SECTIONS,
    MAX_WIDGETS,
    Arrangement,
    Dashboard,
    DashboardItem,
    DashboardSection,
    DashboardWidget,
    DesignDecision,
    WidgetType,
)
from dataflow.modules.exploration.contracts import Exploration, ExploreResult

WIDGETS: dict[str, str] = {
    "kpi": "Indicador: una cifra publicada destacada",
    "bar": "Barras: una cifra por grupo",
    "line": "Líneas: una serie en el tiempo",
    "heatmap": "Mapa de calor: una cifra por cada par de grupos de dos dimensiones",
    "pie": "Circular: partes de un total que se puede sumar (de 2 a 6, sin negativos)",
    "table": "Tabla o tarjeta con el texto del hallazgo y sus cifras",
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
}
KPI_COUNT = 4
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
    if dimensions == 2 and single:
        widgets.append("heatmap")
    # Fase 25: la evolución mensual (`explore-v2`) es una serie en orden cronológico.
    if query.kind == "evolution" and single and len(result.rows) >= 2:
        widgets.extend(["line", "bar"])
    widgets.append("table")
    return DashboardItem(
        id=result_key(result),
        origin="exploration",
        title=result.title,
        kind=query.kind,
        widgets=widgets,
        figures=figures,
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
    for preferred in ("line", "heatmap", "bar"):
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
    missing = [item for item in items if item.id not in present]
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
