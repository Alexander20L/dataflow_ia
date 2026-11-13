"""Informe v2 (Fase 27, ADR-045, `automatic-report-v2`): reglas puras de qué va en el informe.

Estructura de la especificación: resumen ejecutivo, descripción del dataset, calidad y
metodología, hallazgos principales, investigaciones realizadas, conclusiones y recomendaciones,
y un anexo de evidencias. No calcula: reutiliza lo publicado por Dataset (inspección),
Comprensión, Investigación y Dashboard y copia sus cifras canónicas con su `evidence_id`.

Revisión humana (5.7): cada hallazgo candidato está pendiente, aprobado o rechazado (las marcas
del dashboard: «keep» = aprobado, «drop» = rechazado). Si hay alguno aprobado, sólo los
aprobados son principales; si no se revisó nada, lo son los relevantes de la investigación,
marcados «Sin revisar». Un rechazado nunca es principal. Sin hallazgos, el informe lo dice y no
inventa conclusiones.
"""

from collections.abc import Mapping
from datetime import datetime

from dataflow.modules.analytics.contracts import AutomaticAnalysis, AutomaticInsight
from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.copilot.contracts import ReportNarrative, Segment
from dataflow.modules.delivery.contracts import (
    Dashboard,
    ReportBlock,
    ReportChart,
    ReportDocument,
    ReportSection,
    ReportSource,
    ReportTable,
    ReviewItem,
    ReviewStatus,
)
from dataflow.modules.delivery.dashboard import insight_key, result_key
from dataflow.modules.delivery.domain import (
    MAX_CHART_POINTS,
    cited,
    es,
    insight_block,
    quality_section,
    reading_section,
    segments,
    short,
    structure_section,
)
from dataflow.modules.exploration.contracts import (
    Exploration,
    ExploreResult,
    InvestigationNode,
)
from dataflow.modules.ingestion.contracts import SourceReview
from dataflow.modules.inspection.contracts import Inspection
from dataflow.modules.quality.contracts import QualityReport

RULES = "automatic-report-v2"
OPERATION = "delivery.report@2"
STATUS: dict[str, ReviewStatus] = {"keep": "approved", "drop": "rejected"}
STATUS_LABEL = {"approved": "Aprobado por ti", "pending": "Sin revisar", "rejected": "Rechazado"}
CLASSES = {
    "relevant": "Hallazgo relevante",
    "secondary": "Hallazgo secundario",
    "descriptive": "Resultado descriptivo",
    "inconclusive": "No concluyente",
    "discarded": "Hipótesis descartada",
}
DECISIONS = {"deepen": "Profundizar", "finish": "Terminar"}
FORMATS = {
    "csv": "CSV",
    "xlsx": "Libro de Excel",
    "pdf": "Tablas de un PDF",
    "sqlserver": "Tabla de SQL Server",
    "other": "Otro",
}
INSIGHT_IMPORTANCE = 50  # sin revisión ni resultados relevantes: hallazgos del análisis desde aquí
MAX_EVIDENCE_ROWS = 10
CAUTION = (
    "Las recomendaciones son opciones que podrías considerar a partir de los resultados; no "
    "son consecuencias inevitables ni se basan en una causa demostrada: una diferencia, una "
    "evolución o una asociación no prueban por qué ocurre."
)


# --- Revisión humana -----------------------------------------------------------------------------


def review_items(
    analysis: AutomaticAnalysis, exploration: Exploration | None, verdicts: Mapping[str, str]
) -> list[ReviewItem]:
    """Hallazgos candidatos con su revisión y si son principales (ver el docstring del módulo).
    Candidatos: los resultados relevantes o secundarios de la investigación y los hallazgos del
    análisis automático."""
    nodes = {n.key: n for n in exploration.nodes if n.key} if exploration else {}
    found: list[ReviewItem] = []
    for result in exploration.results if exploration else []:
        if not result.relevant:
            continue
        node = nodes.get(result.key)
        key = result_key(result)
        found.append(
            ReviewItem(
                item=key,
                title=result.title,
                origin="exploration",
                classification=node.classification if node else "relevant",
                status=STATUS.get(verdicts.get(key, ""), "pending"),
                principal=False,
            )
        )
    for insight in sorted(analysis.insights, key=lambda i: -i.importance):
        key = insight_key(insight)
        found.append(
            ReviewItem(
                item=key,
                title=insight.title,
                origin="insight",
                classification="relevant" if insight.importance >= INSIGHT_IMPORTANCE else None,
                status=STATUS.get(verdicts.get(key, ""), "pending"),
                principal=False,
            )
        )
    approved = [i for i in found if i.status == "approved"]
    if approved:
        chosen = {i.item for i in approved}
    else:
        relevant = [
            i for i in found if i.origin == "exploration" and i.classification == "relevant"
        ]
        if not relevant:
            relevant = [
                i for i in found if i.origin == "insight" and i.classification == "relevant"
            ][:3]
        chosen = {i.item for i in relevant if i.status != "rejected"}
    return [i.model_copy(update={"principal": i.item in chosen}) for i in found]


def selection_digest_items(items: list[ReviewItem]) -> list[list[str]]:
    """Lo que identifica una selección: cada candidato con su estado (para saber si cambió)."""
    return sorted([i.item, i.status] for i in items)


# --- Cifras de los hallazgos -----------------------------------------------------------------


def result_figures(result: ExploreResult) -> list[tuple[str, str, str | None]]:
    """(evidencia, etiqueta, valor) de las primeras filas de un resultado."""
    figures = []
    for row in result.rows[:MAX_EVIDENCE_ROWS]:
        prefix = " · ".join(row.groups)
        for figure in row.figures:
            label = f"{figure.label} ({prefix})" if prefix else figure.label
            figures.append((figure.evidence_id, label, figure.value))
    return figures


def principal_figures(
    items: list[ReviewItem],
    analysis: AutomaticAnalysis,
    exploration: Exploration | None,
    dashboard: Dashboard | None,
) -> tuple[list[dict[str, object]], list[tuple[str, str, str | None, str]]]:
    """Lo que ve la IA para redactar: los hallazgos principales (título, clase y sus
    evidencias) y sus cifras (evidencia, etiqueta, valor, unidad), más los indicadores."""
    results = {result_key(r): r for r in exploration.results} if exploration else {}
    insights = {insight_key(i): i for i in analysis.insights}
    findings: list[dict[str, object]] = []
    figures: list[tuple[str, str, str | None, str]] = []
    for item in (i for i in items if i.principal):
        if item.item in results:
            values = result_figures(results[item.item])[:6]
            figures.extend((e, label, v, "number") for e, label, v in values)
        else:
            insight = insights[item.item]
            values = [(f.evidence_id, f.label, f.value) for f in insight.figures[:6]]
            figures.extend((f.evidence_id, f.label, f.value, f.unit) for f in insight.figures[:6])
        findings.append(
            {
                "title": item.title,
                "classification": item.classification,
                "evidence": [e for e, _, _ in values],
            }
        )
    for indicator in dashboard.indicators if dashboard else []:
        if indicator.value is not None:
            figures.append((indicator.evidence_id, indicator.name, indicator.value, "number"))
    return findings, figures


# --- Secciones -------------------------------------------------------------------------------


def value_text(value: str | None, unit: str | None = None) -> str:
    return es(value) + (f" {unit}" if unit and value is not None else "")


def summary_section(
    source: ReportSource,
    generated_at: datetime,
    comprehension: Comprehension | None,
    dashboard: Dashboard | None,
    principal: list[ReviewItem],
    narrative: ReportNarrative | None,
    conclusions: list[str],
) -> ReportSection:
    objective = (
        f"Describir el contenido de {source.file_name} e identificar, con cálculos exactos sobre "
        "todos sus registros, los resultados más relevantes para el negocio."
    )
    blocks = [
        ReportBlock(
            table=ReportTable(
                headers=["Dato", "Valor"],
                rows=[
                    ["Análisis", f"Informe automático de {source.file_name}"],
                    ["Archivo analizado", f"{source.file_name} (versión {source.version_number})"],
                    ["Fecha de generación", generated_at.strftime("%Y-%m-%d %H:%M UTC")],
                    ["Objetivo", objective],
                ],
            )
        )
    ]
    if comprehension is not None and comprehension.domain:
        blocks.append(
            ReportBlock(
                title="De qué trata el archivo",
                badge="Hipótesis de la IA",
                paragraphs=[comprehension.domain],
            )
        )
    if narrative is not None and narrative.summary:
        discoveries = [segments(narrative.summary)]
    elif principal:
        discoveries = [f"• {item.title}" for item in principal]
    else:
        discoveries = [
            "No se encontraron hallazgos relevantes con los métodos aplicados; el informe no "
            "presenta conclusiones que los datos no respalden."
        ]
    blocks.append(ReportBlock(title="Principales descubrimientos", paragraphs=discoveries))
    indicators = dashboard.indicators if dashboard else []
    if indicators:
        blocks.append(
            ReportBlock(
                title="Indicadores relevantes",
                table=ReportTable(
                    headers=["Indicador", "Valor", "Periodo", "Comparación", "Evidencia"],
                    rows=[
                        [
                            i.name + (f" ({i.highlight})" if i.highlight else ""),
                            value_text(i.value, i.unit),
                            i.reference,
                            (
                                f"{i.comparison.label}: {es(i.comparison.change)}"
                                + (
                                    f" ({es(i.comparison.change_percent, 'percent')})"
                                    if i.comparison.change_percent
                                    else ""
                                )
                            )
                            if i.comparison
                            else "sin base de comparación",
                            short(i.evidence_id),
                        ]
                        for i in indicators
                    ],
                ),
            )
        )
    blocks.append(
        ReportBlock(title="Conclusiones generales", paragraphs=[f"• {c}" for c in conclusions[:3]])
    )
    return ReportSection(
        id="summary",
        title="Resumen ejecutivo",
        intro="Para quien no conoce los detalles técnicos del archivo.",
        blocks=blocks,
    )


def dataset_section(
    inspection: Inspection | None, comprehension: Comprehension | None
) -> ReportSection:
    rows: list[list[str]] = []
    limitations: list[str] = []
    if inspection is not None:
        summary = inspection.summary
        rows += [
            ["Formato de origen", FORMATS.get(inspection.file.format, inspection.file.format)],
            ["Registros", es(str(summary.rows))],
            ["Columnas", es(str(summary.columns))],
        ]
        limitations += inspection.limitations
    if comprehension is not None:
        period = comprehension.period
        rows.append(
            [
                "Periodo cubierto",
                f"{period.first} a {period.last} ({period.periods} meses con datos)"
                if period and period.first and period.last
                else "No hay una columna temporal reconocida",
            ]
        )
        dimensions = [d.column for d in comprehension.dimensions if d.groupable]
        measures = [m.column for m in comprehension.measures]
        rows.append(["Principales dimensiones", ", ".join(dimensions[:8]) or "ninguna"])
        rows.append(["Principales medidas", ", ".join(measures[:8]) or "ninguna"])
        if comprehension.grain is not None:
            rows.append(["Cada fila representa", comprehension.grain.sentence])
        limitations += comprehension.limitations
    blocks = [ReportBlock(table=ReportTable(headers=["Dato", "Valor"], rows=rows))] if rows else []
    if comprehension is not None and comprehension.scales:
        meanings = {m.column: m for m in comprehension.meanings}
        blocks.append(
            ReportBlock(
                title="Descripción de las variables",
                table=ReportTable(
                    headers=["Columna", "Escala", "Significado"],
                    rows=[
                        [
                            scale.column,
                            scale.scale,
                            "Desconocida (marcada por ti)"
                            if scale.column in meanings and meanings[scale.column].unknown
                            else (
                                meanings[scale.column].meaning
                                + (" (tuyo)" if meanings[scale.column].source == "user" else "")
                                if scale.column in meanings
                                else "sin descripción"
                            ),
                        ]
                        for scale in comprehension.scales
                    ],
                ),
            )
        )
    unique = list(dict.fromkeys(limitations))
    if unique:
        blocks.append(
            ReportBlock(
                title="Limitaciones de la información", paragraphs=[f"• {t}" for t in unique]
            )
        )
    return ReportSection(
        id="dataset",
        title="Descripción del dataset",
        intro="Lo que ya calcularon las pestañas Dataset y Comprensión; no se vuelve a calcular.",
        blocks=blocks or [ReportBlock(paragraphs=["Sin descripción disponible."])],
    )


def methodology_section(
    inspection: Inspection | None,
    quality: QualityReport | None,
    exploration: Exploration | None,
) -> ReportSection:
    blocks: list[ReportBlock] = []
    if inspection is not None:
        summary = inspection.summary
        blocks.append(
            ReportBlock(
                title="Completitud y problemas de calidad",
                paragraphs=[
                    f"Completitud del archivo: {es(summary.completeness_percent, 'percent')} "
                    f"({es(str(summary.missing_cells))} celdas vacías de "
                    f"{es(str(summary.cells))}).",
                    f"Criterios: reglas {inspection.scope.rules} sobre todos los registros.",
                ],
                table=ReportTable(
                    headers=["Problema", "Dimensión", "Columnas", "Filas afectadas", "%"],
                    rows=[
                        [
                            f.title,
                            f.dimension,
                            ", ".join(f.columns[:4]),
                            es(str(f.affected_rows)),
                            es(f.percent, "percent"),
                        ]
                        for f in inspection.findings[:20]
                    ],
                )
                if inspection.findings
                else None,
            )
        )
        incomplete = [c for c in inspection.columns if c.nulls > 0]
        if incomplete:
            blocks.append(
                ReportBlock(
                    title="Variables con limitaciones",
                    table=ReportTable(
                        headers=["Columna", "Vacíos", "% vacíos"],
                        rows=[
                            [c.name, es(str(c.nulls)), es(c.null_percent, "percent")]
                            for c in sorted(incomplete, key=lambda c: -c.nulls)[:15]
                        ],
                    ),
                )
            )
    else:
        legacy = quality_section(quality)
        if legacy is not None:
            blocks.extend(legacy.blocks)
    computed = [
        n for n in (exploration.nodes if exploration else []) if n.status == "computed" and n.key
    ]
    results = {r.key: r for r in exploration.results} if exploration else {}
    methods = list(dict.fromkeys(results[n.key].method for n in computed if n.key in results))
    if methods:
        blocks.append(
            ReportBlock(title="Métodos aplicados", paragraphs=[f"• {m}" for m in methods])
        )
    if computed:
        blocks.append(
            ReportBlock(
                title="Transformaciones y filtros de cada investigación",
                paragraphs=[
                    "Ninguna investigación modifica el archivo: cada una lee la versión publicada "
                    "y declara los registros que consideró y lo que excluyó (por ejemplo, filas "
                    "sin valor en las columnas usadas)."
                ],
                table=ReportTable(
                    headers=["Investigación", "Operación", "Registros", "Filtros", "Exclusiones"],
                    rows=[
                        [
                            f"{n.id} · {n.question}",
                            n.method,
                            considered(n),
                            ", ".join(n.filters) or "ninguno",
                            "; ".join(n.limitations) or "ninguna",
                        ]
                        for n in computed
                    ],
                ),
            )
        )
    return ReportSection(
        id="methodology",
        title="Calidad de los datos y metodología",
        blocks=blocks or [ReportBlock(paragraphs=["Sin información de calidad."])],
    )


def considered(node: InvestigationNode) -> str:
    if node.rows_considered is None:
        return "sin dato"
    if node.total_rows:
        return f"{es(str(node.rows_considered))} de {es(str(node.total_rows))}"
    return es(str(node.rows_considered))


def result_chart(result: ExploreResult) -> ReportChart | None:
    query = result.query
    single = result.rows and all(len(r.figures) == 1 for r in result.rows)
    if not single or len(query.dimensions) > 1 or not 1 < len(result.rows) <= MAX_CHART_POINTS:
        return None
    if query.kind not in {"evolution", "aggregate", "top", "distribution"}:
        return None
    valued = [r for r in result.rows if r.figures[0].value is not None]
    if len(valued) < 2:
        return None
    return ReportChart(
        type="line" if query.kind == "evolution" else "bar",
        title=result.title,
        labels=[r.groups[0] if r.groups else "" for r in valued],
        values=[r.figures[0].value or "0" for r in valued],
    )


def finding_block(
    item: ReviewItem, result: ExploreResult, node: InvestigationNode | None
) -> ReportBlock:
    paragraphs = [f"Pregunta: {node.question}" if node else result.title]
    if node is not None and node.hypothesis:
        paragraphs.append(f"Hipótesis: {node.hypothesis}")
    paragraphs.append(
        "Interpretación: "
        + (
            node.interpretation
            if node is not None and node.interpretation
            else (result.reason or "El resultado describe los datos; no demuestra una causa.")
        )
    )
    criteria = {c.name: c.assessment for c in node.criteria} if node else {}
    importance = CLASSES.get(item.classification or "", "Sin clasificar")
    if "magnitude" in criteria:
        importance += f" · {criteria['magnitude']}"
    paragraphs.append(f"Importancia: {importance}")
    limits = list(node.limitations) if node else []
    if node is not None and node.rows_considered is not None:
        limits.insert(0, f"Registros considerados: {considered(node)}.")
    paragraphs.append(f"Método: {result.method}")
    if limits:
        paragraphs.append("Limitaciones: " + " ".join(limits))
    headers = [*result.columns[:-1]] if result.columns else ["Cifra"]
    rows = [
        [*row.groups, *(es(f.value) for f in row.figures)]
        for row in result.rows[:MAX_EVIDENCE_ROWS]
    ]
    evidence = ReportTable(
        headers=[*headers, "Evidencia"],
        rows=[
            [*cells, short(row.figures[0].evidence_id) if row.figures else ""]
            for cells, row in zip(rows, result.rows[:MAX_EVIDENCE_ROWS], strict=True)
        ],
    )
    if len(result.rows) > MAX_EVIDENCE_ROWS:
        paragraphs.append(
            f"Se muestran {MAX_EVIDENCE_ROWS} de {result.total_groups} filas del resultado."
        )
    return ReportBlock(
        title=result.title,
        badge=STATUS_LABEL[item.status],
        paragraphs=paragraphs,
        table=evidence,
        chart=result_chart(result),
    )


def insight_finding(item: ReviewItem, insight: AutomaticInsight) -> ReportBlock:
    block = insight_block(insight, STATUS_LABEL[item.status])
    importance = "Hallazgo relevante" if item.classification == "relevant" else "Hallazgo"
    return block.model_copy(
        update={
            "paragraphs": [
                *block.paragraphs,
                f"Importancia: {importance} del análisis automático "
                f"(importancia {insight.importance} de 100).",
                "Interpretación: el resultado describe los datos; no demuestra una causa.",
            ]
        }
    )


def findings_section(
    items: list[ReviewItem], analysis: AutomaticAnalysis, exploration: Exploration | None
) -> ReportSection:
    results = {result_key(r): r for r in exploration.results} if exploration else {}
    nodes = {n.key: n for n in exploration.nodes if n.key} if exploration else {}
    insights = {insight_key(i): i for i in analysis.insights}
    blocks = []
    for item in (i for i in items if i.principal):
        if item.item in results:
            result = results[item.item]
            blocks.append(finding_block(item, result, nodes.get(result.key)))
        elif item.item in insights:
            blocks.append(insight_finding(item, insights[item.item]))
    approved = any(i.status == "approved" for i in items)
    others = [i for i in items if not i.principal and i.status != "rejected"]
    if others:
        blocks.append(
            ReportBlock(
                title="Otros resultados (no principales)",
                table=ReportTable(
                    headers=["Resultado", "Clase", "Revisión"],
                    rows=[
                        [
                            i.title,
                            CLASSES.get(i.classification or "", "Hallazgo"),
                            STATUS_LABEL[i.status],
                        ]
                        for i in others[:30]
                    ],
                ),
            )
        )
    rejected = [i for i in items if i.status == "rejected"]
    if rejected:
        blocks.append(
            ReportBlock(
                title="Rechazados por ti",
                paragraphs=[f"• {i.title}" for i in rejected],
            )
        )
    intro = (
        "Sólo los hallazgos que aprobaste."
        if approved
        else "Aún no revisaste los hallazgos: se muestran los relevantes de la investigación, "
        "marcados «Sin revisar». Puedes aprobarlos o rechazarlos en la pestaña Informe."
    )
    if not any(i.principal for i in items):
        blocks.insert(
            0,
            ReportBlock(
                paragraphs=[
                    "No hay hallazgos principales: la investigación no encontró resultados "
                    "relevantes o todos se rechazaron. No se presentan conclusiones inventadas."
                ]
            ),
        )
    return ReportSection(id="findings", title="Hallazgos principales", intro=intro, blocks=blocks)


def investigations_section(exploration: Exploration | None) -> ReportSection | None:
    if exploration is None or not exploration.nodes:
        return None
    nodes = exploration.nodes

    def table(selected: list[InvestigationNode]) -> ReportTable:
        return ReportTable(
            headers=["Id", "Pregunta", "Hipótesis", "Método", "Resultado", "Decisión"],
            rows=[
                [
                    n.id,
                    n.question,
                    n.hypothesis or "—",
                    n.method,
                    CLASSES.get(n.classification or "", n.reason or n.status),
                    DECISIONS.get(n.decision or "", "—"),
                ]
                for n in selected
            ],
        )

    blocks = [
        ReportBlock(title="Plan de investigación", table=table([n for n in nodes if n.depth == 0]))
    ]
    secondary = [n for n in nodes if n.depth > 0]
    if secondary:
        blocks.append(ReportBlock(title="Investigaciones secundarias", table=table(secondary)))
    discarded = [n for n in nodes if n.classification == "discarded" or n.status == "rejected"]
    if discarded:
        blocks.append(
            ReportBlock(
                title="Hipótesis descartadas",
                paragraphs=[
                    f"• {n.question}: {n.decision_reason or n.reason or ''}" for n in discarded
                ],
            )
        )
    inconclusive = [n for n in nodes if n.classification == "inconclusive" or n.status == "failed"]
    if inconclusive:
        blocks.append(
            ReportBlock(
                title="Resultados no concluyentes",
                paragraphs=[
                    f"• {n.question}: {n.reason or 'sin resultado claro'}" for n in inconclusive
                ],
            )
        )
    stopped = {
        "completed": "terminó el plan y sus investigaciones secundarias",
        "max_nodes": "se detuvo al llegar al límite de investigaciones",
        "max_seconds": "se detuvo al llegar al límite de tiempo",
        "paused": "se pausó",
        "cancelled": "se canceló",
    }.get(exploration.stopped or "", "terminó")
    return ReportSection(
        id="investigations",
        title="Investigaciones realizadas",
        intro=(
            f"El sistema formuló {len(nodes)} preguntas y {stopped}. Cada cifra la calculó el "
            "motor sobre todos los registros; la IA sólo propuso preguntas y las juzgó."
        ),
        blocks=blocks,
    )


def rules_conclusions(
    items: list[ReviewItem], analysis: AutomaticAnalysis, exploration: Exploration | None
) -> tuple[list[str], list[str]]:
    """Conclusiones y recomendaciones por reglas: una conclusión por hallazgo principal con su
    cifra principal y recomendaciones sin causalidad según el tipo de resultado."""
    results = {result_key(r): r for r in exploration.results} if exploration else {}
    insights = {insight_key(i): i for i in analysis.insights}
    conclusions: list[str] = []
    recommendations: list[str] = []
    for item in (i for i in items if i.principal):
        if item.item in results:
            result = results[item.item]
            first = result.rows[0] if result.rows else None
            # La tasa (Fase 28) lleva la proporción primero; el resto, la cifra principal al final.
            position = 0 if result.query.kind == "rate" else -1
            figure = first.figures[position] if first and first.figures else None
            group = f" en {' · '.join(first.groups)}" if first and first.groups else ""
            conclusions.append(
                f"{result.title}: {figure.label}{group} = {es(figure.value)} "
                f"[{short(figure.evidence_id)}]."
                if figure
                else f"{result.title}."
            )
            kind = result.query.kind
            text = {
                "evolution": "Seguir la evolución mensual y revisar qué grupos explican los "
                "meses que se apartan.",
                "period_change": "Revisar qué grupos aportan más al cambio entre periodos antes "
                "de tomar decisiones.",
                "outliers": "Revisar los registros atípicos para confirmar si son errores o "
                "casos reales.",
                "correlation_by_group": "Validar con conocimiento del negocio la asociación "
                "encontrada: no implica una causa.",
                "rate": "Revisar los grupos con la tasa más alta y comprobar que tienen casos "
                "suficientes antes de actuar: una diferencia de tasas no explica su causa.",
            }.get(kind, "Evaluar la dependencia de los grupos que concentran el resultado.")
            if text not in recommendations:
                recommendations.append(text)
        elif item.item in insights:
            insight = insights[item.item]
            conclusions.append(insight.statement)
    if not conclusions:
        conclusions = ["Los datos no muestran hallazgos relevantes con los métodos aplicados."]
        recommendations = [
            "Revisar la calidad, el periodo y la comprensión del dataset antes de sacar "
            "conclusiones; con más registros o un periodo más largo la investigación puede "
            "encontrar resultados."
        ]
    return conclusions, recommendations


def conclusions_section(
    conclusions: list[str], recommendations: list[str], by: str, reason: str | None
) -> ReportSection:
    origin = (
        "Redactadas por la IA a partir de los hallazgos principales; cada cifra se comprobó con "
        "su evidencia y se retiraron las frases que afirmaban una causa."
        if by == "ai"
        else "Redactadas por reglas a partir de los hallazgos principales"
        + (f" (la IA no estuvo disponible: {reason})." if reason else ".")
    )
    return ReportSection(
        id="conclusions",
        title="Conclusiones y recomendaciones",
        intro=origin,
        blocks=[
            ReportBlock(
                title="Conclusiones: qué muestran los datos",
                paragraphs=[f"• {c}" for c in conclusions],
            ),
            ReportBlock(
                title="Recomendaciones: qué podrías considerar",
                paragraphs=[*(f"• {r}" for r in recommendations), CAUTION],
            ),
        ],
    )


def annex_section(
    evidence: list[tuple[str, str, str | None]],
) -> ReportSection:
    return ReportSection(
        id="evidence",
        title="Anexo: evidencias",
        intro="Cada cifra del informe, con el identificador de la evidencia que la calculó.",
        blocks=[
            ReportBlock(
                table=ReportTable(
                    headers=["Evidencia", "Cifra", "Valor"],
                    rows=[[short(e), label, es(value)] for e, label, value in evidence],
                )
            )
        ],
    )


def build_report_v2(
    source: ReportSource,
    generated_at: datetime,
    analysis: AutomaticAnalysis,
    quality: QualityReport | None,
    inspection: Inspection | None,
    comprehension: Comprehension | None,
    exploration: Exploration | None,
    dashboard: Dashboard | None,
    verdicts: Mapping[str, str],
    narrative: ReportNarrative | None = None,
    narrative_reason: str | None = None,
    review: SourceReview | None = None,
    calls: list[dict[str, object]] | None = None,
) -> ReportDocument:
    items = review_items(analysis, exploration, verdicts)
    principal = [i for i in items if i.principal]
    rule_conclusions, rule_recommendations = rules_conclusions(items, analysis, exploration)
    if narrative is not None and (narrative.conclusions or narrative.recommendations):
        conclusions = [segments(c) for c in narrative.conclusions] or rule_conclusions
        recommendations = [segments(r) for r in narrative.recommendations] or rule_recommendations
        by = "ai"
    else:
        conclusions, recommendations, by = rule_conclusions, rule_recommendations, "rules"
    sections = [
        summary_section(
            source, generated_at, comprehension, dashboard, principal, narrative, conclusions
        ),
        dataset_section(inspection, comprehension),
        methodology_section(inspection, quality, exploration),
        findings_section(items, analysis, exploration),
        investigations_section(exploration),
        conclusions_section(conclusions, recommendations, by, narrative_reason),
        reading_section(review),
        structure_section(review),
    ]
    # Anexo: las cifras citadas (indicadores, hallazgos principales y narrativa).
    results = {result_key(r): r for r in exploration.results} if exploration else {}
    insights = {insight_key(i): i for i in analysis.insights}
    evidence: dict[str, tuple[str, str, str | None]] = {}
    for indicator in dashboard.indicators if dashboard else []:
        evidence[indicator.evidence_id] = (indicator.evidence_id, indicator.name, indicator.value)
    for item in principal:
        if item.item in results:
            for e, label, value in result_figures(results[item.item]):
                evidence.setdefault(e, (e, label, value))
        elif item.item in insights:
            for f in insights[item.item].figures:
                evidence.setdefault(f.evidence_id, (f.evidence_id, f.label, f.value))
    if narrative is not None:
        written: list[Segment] = [
            *narrative.summary,
            *(s for c in narrative.conclusions for s in c),
            *(s for r in narrative.recommendations for s in r),
        ]
        for identifier in cited(written):
            if identifier not in evidence:
                evidence[identifier] = (identifier, "Cifra citada", None)
    if evidence:
        sections.append(annex_section(list(evidence.values())))
    return ReportDocument(
        schema_version=2,
        operation=OPERATION,
        rules_version=RULES,
        title=f"Informe · {source.file_name}",
        source=source,
        generated_at=generated_at,
        sections=[s for s in sections if s is not None],
        evidence_ids=list(evidence),
        review=items,
        narrative_by="ai" if by == "ai" else "rules",
        narrative_reason=narrative_reason,
        calls=calls or [],
    )
