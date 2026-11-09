"""Reglas puras de la entrega (`automatic-report-v1`): qué va en el informe y en qué orden, y
el progreso por etapas de una carga.

Sin frameworks, base de datos ni proveedor. El informe no calcula: copia las cifras canónicas de
los hallazgos y de la investigación (sólo cambia su formato de lectura) y conserva cada
`evidence_id`; el anexo final enumera todas las evidencias citadas.
"""

import re
from datetime import datetime
from uuid import UUID

from dataflow.modules.analytics.contracts import (
    AutomaticAnalysis,
    AutomaticEvidence,
    AutomaticInsight,
)
from dataflow.modules.copilot.contracts import Segment
from dataflow.modules.delivery.contracts import (
    Progress,
    ReportBlock,
    ReportChart,
    ReportDocument,
    ReportSection,
    ReportSource,
    ReportTable,
    RunSummary,
    Stage,
    StageId,
    StageState,
)
from dataflow.modules.investigation.contracts import Investigation, Proposal
from dataflow.modules.quality.contracts import QualityReport

SUMMARY_FINDINGS = 5
MAX_CHART_POINTS = 24
STOPPED = {
    "max_iterations": "se completaron las iteraciones permitidas",
    "no_new_proposals": "la IA no propuso nada nuevo y válido",
    "ai_unavailable": "la IA no está disponible: sólo se aplicaron las reglas",
    "ai_error": "el proveedor de IA falló; se conservan los resultados ya calculados",
    "max_ai_calls": "se alcanzó el máximo de llamadas a la IA",
    "max_cost": "se alcanzó el presupuesto de IA de la investigación",
    "max_seconds": "se alcanzó el tiempo máximo",
    "max_queries": "se alcanzó el máximo de consultas",
    "nothing_to_investigate": "no hay medida, agrupación o meses que seguir",
}
SEVERITY = {"alta": "Alta", "media": "Media", "baja": "Baja"}
QUALITY_SEVERITY = {"blocking": "Bloqueante", "warning": "Advertencia", "info": "Observación"}
ORIGIN = {"rule": "Regla", "ai": "Propuesto por la IA"}


def es(value: str | None, unit: str = "number") -> str:
    """Cifra canónica con formato español (sólo presentación; no redondea)."""
    if value is None:
        return "sin dato"
    text = value
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
        sign = text[0] if text[0] in "+-" else ""
        integer, _, fraction = text.lstrip("+-").partition(".")
        grouped = re.sub(r"\B(?=(\d{3})+(?!\d))", ".", integer)
        text = f"{sign}{grouped},{fraction}" if fraction else f"{sign}{grouped}"
    return f"{text} %" if unit == "percent" else text


def short(evidence_id: str) -> str:
    return evidence_id[:12]


def segments(items: list[Segment]) -> str:
    """Texto de la IA ya verificado; cada cifra lleva su evidencia entre corchetes."""
    parts = []
    for item in items:
        if item.kind == "evidence" and item.evidence_id:
            parts.append(f"{item.text} [{short(item.evidence_id)}]")
        elif item.kind == "unverified":
            parts.append("[cifra retirada]")
        else:
            parts.append(item.text)
    return "".join(parts).strip()


def cited(items: list[Segment]) -> list[str]:
    return [item.evidence_id for item in items if item.kind == "evidence" and item.evidence_id]


def insight_block(insight: AutomaticInsight, badge: str | None = None) -> ReportBlock:
    paragraphs = [insight.statement]
    if insight.coverage:
        paragraphs.append(f"Cobertura: {insight.coverage}")
    paragraphs.extend(insight.notes)
    table = (
        ReportTable(
            headers=["Cifra", "Valor", "Evidencia"],
            rows=[
                [figure.label, es(figure.value, figure.unit), short(figure.evidence_id)]
                for figure in insight.figures
            ],
        )
        if insight.figures
        else None
    )
    chart = None
    points = [point for point in (insight.chart.points if insight.chart else [])]
    if insight.chart and 1 < len(points) <= MAX_CHART_POINTS:
        valued = [point for point in points if point.value is not None]
        if len(valued) > 1:
            chart = ReportChart(
                type=insight.chart.type,
                title=insight.chart.title,
                labels=[point.label for point in valued],
                values=[point.value for point in valued if point.value is not None],
            )
    return ReportBlock(
        title=insight.title, badge=badge, paragraphs=paragraphs, table=table, chart=chart
    )


def target(proposal: Proposal) -> str:
    detail = proposal.month or (str(proposal.year) if proposal.year else None) or proposal.group
    return " · ".join(part for part in [proposal.kind, proposal.dimension, detail] if part)


def summary_section(
    source: ReportSource, analysis: AutomaticAnalysis, quality: QualityReport | None
) -> ReportSection:
    intro = (
        f"Informe automático de {source.file_name} (versión v{source.version_number}). "
        "Todas las cifras las calculó el motor determinista sobre el dataset completo; "
        "cada una lleva su referencia de evidencia (anexo final)."
    )
    if quality is not None:
        intro += f" Filas analizadas: {es(str(quality.row_count), 'count')}."
    key = sorted(analysis.insights, key=lambda item: -item.importance)[:SUMMARY_FINDINGS]
    blocks = [
        ReportBlock(
            title=insight.title,
            paragraphs=[insight.statement],
            table=ReportTable(
                headers=["Cifra", "Valor", "Evidencia"],
                rows=[
                    [figure.label, es(figure.value, figure.unit), short(figure.evidence_id)]
                    for figure in insight.figures[:4]
                ],
            )
            if insight.figures
            else None,
        )
        for insight in key
    ]
    if not blocks:
        blocks = [ReportBlock(paragraphs=["No se obtuvieron hallazgos para esta carga."])]
    return ReportSection(id="summary", title="Resumen", intro=intro, blocks=blocks)


def explanation_section(investigation: Investigation) -> ReportSection:
    content = investigation.explanation
    if investigation.explanation_state != "ready" or content is None:
        reason = investigation.explanation_reason or investigation.ai_reason or "no disponible"
        return ReportSection(
            id="explanation",
            title="Explicación automática (IA)",
            blocks=[
                ReportBlock(
                    paragraphs=[
                        f"Sin explicación de la IA ({reason}). Los hallazgos y la "
                        "investigación por reglas no dependen de ella."
                    ]
                )
            ],
        )
    blocks = [
        ReportBlock(title="Resumen ejecutivo", paragraphs=[segments(content.resumen_ejecutivo)])
    ]
    for alert in content.alertas_criticas:
        blocks.append(
            ReportBlock(
                title=segments(alert.titulo),
                badge=f"Severidad {SEVERITY.get(alert.severidad, alert.severidad)}",
                paragraphs=[segments(alert.detalle)],
            )
        )
    if content.recomendaciones:
        blocks.append(
            ReportBlock(
                title="Recomendaciones",
                paragraphs=[f"• {segments(item)}" for item in content.recomendaciones],
            )
        )
    return ReportSection(
        id="explanation",
        title="Explicación automática (IA)",
        intro="Redactada por la IA sobre cifras ya calculadas; sólo cita evidencias "
        "verificadas y las cifras sin evidencia se retiran.",
        blocks=blocks,
    )


def investigation_section(investigation: Investigation) -> ReportSection:
    origin = {proposal.key: proposal for proposal in investigation.proposals if proposal.key}
    blocks: list[ReportBlock] = []
    for result in investigation.results:
        proposal = origin.get(result.key)
        badge = ORIGIN.get(proposal.origin) if proposal else None
        if result.status == "computed" and result.insight is not None:
            block = insight_block(result.insight, badge)
            if proposal:
                block = block.model_copy(
                    update={"paragraphs": [f"Motivo: {proposal.motive}", *block.paragraphs]}
                )
            blocks.append(block)
        else:
            blocks.append(
                ReportBlock(
                    title=result.key,
                    badge=badge,
                    paragraphs=[result.reason or "Sin datos para este seguimiento."],
                )
            )
    rejected = [proposal for proposal in investigation.proposals if proposal.status == "rejected"]
    if rejected:
        blocks.append(
            ReportBlock(
                title="Propuestas rechazadas",
                paragraphs=["Python rechazó estas propuestas antes de calcular nada."],
                table=ReportTable(
                    headers=["Origen", "Propuesta", "Motivo del rechazo"],
                    rows=[
                        [ORIGIN.get(item.origin, item.origin), target(item), item.reason or ""]
                        for item in rejected
                    ],
                ),
            )
        )
    if not blocks:
        blocks = [ReportBlock(paragraphs=["No hubo seguimientos que calcular."])]
    consumption = investigation.consumption
    intro = (
        f"Seguimientos de los hallazgos en {investigation.iterations} iteración(es); "
        f"se detuvo porque {STOPPED.get(investigation.stopped, investigation.stopped)}. "
        f"Llamadas a la IA: {consumption.ai_calls}; costo estimado US$ {es(consumption.cost_usd)}."
    )
    return ReportSection(
        id="investigation", title="Investigación automática", intro=intro, blocks=blocks
    )


def quality_section(quality: QualityReport | None) -> ReportSection | None:
    if quality is None:
        return None
    blocks = [
        ReportBlock(
            table=ReportTable(
                headers=["Indicador", "Valor"],
                rows=[
                    ["Filas", es(str(quality.row_count), "count")],
                    ["Celdas", es(str(quality.cell_count), "count")],
                    ["Celdas vacías", es(str(quality.missing_cells), "count")],
                    ["Filas duplicadas", es(str(quality.duplicate_rows), "count")],
                    ["Completitud", es(f"{quality.completeness_percent:.2f}", "percent")],
                ],
            )
        )
    ]
    analytical = quality.analytical
    if analytical is not None and analytical.findings:
        blocks.append(
            ReportBlock(
                title="Revisión analítica",
                table=ReportTable(
                    headers=["Hallazgo", "Severidad", "Filas afectadas", "Análisis afectados"],
                    rows=[
                        [
                            item.title,
                            QUALITY_SEVERITY.get(item.severity, item.severity),
                            es(str(item.affected_rows), "count"),
                            ", ".join(item.affected_analyses) or "ninguno",
                        ]
                        for item in analytical.findings
                    ],
                ),
            )
        )
    return ReportSection(
        id="quality",
        title="Calidad de los datos",
        intro="Calidad evaluada automáticamente al subir el archivo; no se modificó el original.",
        blocks=blocks,
    )


def omitted_section(analysis: AutomaticAnalysis) -> ReportSection | None:
    omitted = analysis.plan.omitted
    if not omitted:
        return None
    return ReportSection(
        id="omitted",
        title="Análisis omitidos",
        intro="El plan automático descartó estos análisis; cada uno con su motivo.",
        blocks=[
            ReportBlock(
                table=ReportTable(
                    headers=["Análisis", "Motivo"],
                    rows=[[item.title, item.reason] for item in omitted],
                )
            )
        ],
    )


def limitations_section(
    analysis: AutomaticAnalysis, investigation: Investigation
) -> ReportSection | None:
    seen: list[str] = []
    for text in [*analysis.limitations, *investigation.limitations]:
        if text not in seen:
            seen.append(text)
    if not seen:
        return None
    return ReportSection(
        id="limitations",
        title="Limitaciones",
        blocks=[ReportBlock(paragraphs=[f"• {text}" for text in seen])],
    )


def evidence_ids(analysis: AutomaticAnalysis, investigation: Investigation) -> list[str]:
    found: list[str] = []
    for insight in analysis.insights:
        found.extend(figure.evidence_id for figure in insight.figures)
    for result in investigation.results:
        if result.insight is not None:
            found.extend(figure.evidence_id for figure in result.insight.figures)
    content = investigation.explanation
    if investigation.explanation_state == "ready" and content is not None:
        found.extend(cited(content.resumen_ejecutivo))
        for alert in content.alertas_criticas:
            found.extend(cited(alert.titulo) + cited(alert.detalle))
        for item in content.recomendaciones:
            found.extend(cited(item))
    return list(dict.fromkeys(found))


def evidence_section(
    identifiers: list[str], analysis: AutomaticAnalysis, investigation: Investigation
) -> ReportSection:
    known: dict[str, AutomaticEvidence] = {item.evidence_id: item for item in analysis.evidence}
    for result in investigation.results:
        known.update({item.evidence_id: item for item in result.evidence})
    rows = []
    for identifier in identifiers:
        item = known.get(identifier)
        rows.append(
            [identifier, item.label, es(item.value, item.unit), item.method]
            if item
            else [identifier, "", "", ""]
        )
    return ReportSection(
        id="evidence",
        title="Anexo: evidencias",
        intro="Cada referencia del informe (12 primeros caracteres) corresponde a una de estas "
        "evidencias; su procedencia completa se consulta en la aplicación.",
        blocks=[
            ReportBlock(
                table=ReportTable(headers=["Evidencia", "Cifra", "Valor", "Método"], rows=rows)
            )
        ],
    )


def build_report(
    source: ReportSource,
    analysis: AutomaticAnalysis,
    investigation: Investigation,
    quality: QualityReport | None,
    generated_at: datetime,
) -> ReportDocument:
    identifiers = evidence_ids(analysis, investigation)
    sections = [
        summary_section(source, analysis, quality),
        explanation_section(investigation),
        ReportSection(
            id="findings",
            title="Hallazgos",
            intro="Hallazgos del análisis automático, en el orden del plan.",
            blocks=[insight_block(insight) for insight in analysis.insights]
            or [ReportBlock(paragraphs=["Sin hallazgos."])],
        ),
        investigation_section(investigation),
        quality_section(quality),
        omitted_section(analysis),
        limitations_section(analysis, investigation),
        evidence_section(identifiers, analysis, investigation),
    ]
    return ReportDocument(
        title=f"Informe automático · {source.file_name}",
        source=source,
        generated_at=generated_at,
        sections=[section for section in sections if section is not None],
        evidence_ids=identifiers,
    )


# --- Progreso por etapas ---------------------------------------------------------------------

STAGES: list[tuple[StageId, str, set[str]]] = [
    ("analysis", "Análisis del archivo", {"csv_import", "table_analysis"}),
    ("investigation", "Investigación", {"investigation"}),
    ("report", "Informe", {"automatic_report"}),
]
STATES: dict[str, StageState] = {
    "queued": "queued",
    "running": "running",
    "succeeded": "done",
    "failed": "failed",
    "cancelled": "failed",
}
DETAILS = {
    "queued": "En cola: esperando su turno.",
    "running": "En curso.",
    "succeeded": "Terminado.",
    "cancelled": "Cancelado.",
}


def progress(version: UUID, runs: list[RunSummary]) -> Progress:
    """`runs` de la versión, del más reciente al más antiguo (sólo cuenta el último de cada
    etapa). Una etapa sin trabajo tras otra terminada no aplica a esta carga."""
    stages: list[Stage] = []
    previous: StageState = "done"
    for identifier, title, kinds in STAGES:
        run = next((item for item in runs if item.kind in kinds), None)
        if run is not None:
            stage = Stage(
                id=identifier,
                title=title,
                state=STATES[run.state],
                detail=DETAILS.get(run.state, f"Falló ({run.error_code or 'error'})."),
                execution_id=run.id,
                finished_at=run.finished_at,
            )
        elif previous in {"pending", "queued", "running"}:
            stage = Stage(
                id=identifier,
                title=title,
                state="pending",
                detail="Empezará cuando termine la etapa anterior.",
            )
        else:
            stage = Stage(
                id=identifier,
                title=title,
                state="skipped",
                detail="No se hizo: la etapa anterior no terminó."
                if previous == "failed"
                else "No aplica a esta carga (procesada antes de esta etapa o sin hallazgos).",
            )
        stages.append(stage)
        previous = stage.state
    return Progress(
        version_id=version,
        complete=all(stage.state in {"done", "failed", "skipped"} for stage in stages),
        stages=stages,
    )
