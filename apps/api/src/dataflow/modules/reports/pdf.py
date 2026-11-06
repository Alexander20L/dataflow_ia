"""PDF de una revisión exacta del informe con ReportLab (sin base de datos ni navegador).

Cada bloque de datos lleva al pie su procedencia (dataset, versión, ejecución, plan, filtros,
periodo y fecha de cálculo) y una tabla con las cifras exactas y su `evidence_id`. Las tarjetas
de barras o líneas añaden un gráfico vectorial dibujado con las mismas filas; el gráfico ilustra,
la trazabilidad está en la tabla. Cada página indica la revisión y la fecha de generación.
"""

import io
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from dataflow.modules.reports.contracts import Provenance, ReportSnapshot, SnapshotBlock

MAX_ROWS = 200
STATUS_LABELS = {
    "pending": "Calculándose cuando se generó el PDF",
    "failed": "Ejecución fallida",
    "not_executed": "Sin calcular",
    "insufficient_data": "Datos insuficientes",
    "semantic_requirement_missing": "Requisito semántico pendiente",
    "invalid_plan": "Análisis no válido para esta versión",
}
HEADINGS = {"conclusion": "Conclusión", "limitations": "Limitaciones"}
ACCENT = colors.HexColor("#4f46e5")
MUTED = colors.HexColor("#64748b")

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("title", parent=styles["Title"], fontSize=18, alignment=0, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
META = ParagraphStyle("meta", parent=BODY, fontSize=7.5, leading=10, textColor=MUTED)
KPI = ParagraphStyle("kpi", parent=BODY, fontSize=22, leading=26, textColor=ACCENT)
WARN = ParagraphStyle("warn", parent=BODY, textColor=colors.HexColor("#92400e"))


def text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def render_pdf(snapshot: ReportSnapshot) -> bytes:
    buffer = io.BytesIO()
    generated = snapshot.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    footer = (
        f"{snapshot.report_title} · revisión {snapshot.revision} ({snapshot.revision_id}) · "
        f"generado {generated}"
    )

    def on_page(canvas: Canvas, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 10 * mm, footer[:160])
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"pág. {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=snapshot.report_title,
        author="DataFlow AI",
        subject=f"Informe revisión {snapshot.revision} · {snapshot.revision_id}",
    )
    story: list[Flowable] = [
        Paragraph(text(snapshot.report_title), TITLE),
        Paragraph(
            text(
                f"Dataset {snapshot.dataset} · versión v{snapshot.version_number} · informe "
                f"revisión {snapshot.revision} ({snapshot.revision_id}) · contenido SHA-256 "
                f"{snapshot.content_sha256} · generado {generated}"
            ),
            META,
        ),
        Spacer(1, 6),
    ]
    for block in snapshot.blocks:
        story.extend(block_flowables(block))
    document.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


def block_flowables(block: SnapshotBlock) -> list[Flowable]:
    if block.provenance is None:
        heading = HEADINGS.get(block.kind)
        flowables: list[Flowable] = [Paragraph(heading, H2)] if heading else []
        flowables.append(Paragraph(text(block.text or ""), BODY))
        flowables.append(Spacer(1, 4))
        return flowables
    provenance = block.provenance
    flowables = [Paragraph(text(block.title or "Análisis"), H2)]
    if provenance.status != "ready" or not block.result:
        label = STATUS_LABELS.get(provenance.status, provenance.status)
        message = f" — {provenance.message}" if provenance.message else ""
        flowables.append(Paragraph(text(f"{label}{message}"), WARN))
    else:
        flowables.extend(data_flowables(block.result, provenance))
    flowables.append(Spacer(1, 3))
    flowables.append(Paragraph(text(provenance_line(provenance)), META))
    return [KeepTogether(flowables[:2]), *flowables[2:]]


def provenance_line(p: Provenance) -> str:
    filters = "; ".join(
        f"{str(f.get('column_id', ''))[:8]} {f.get('operator', '')} "
        f"{', '.join(str(v) for v in f.get('values') or [])}".strip()
        for f in p.filters
    )
    period = ""
    if p.time_range:
        period = f" · periodo {p.time_range.get('start') or '…'} – {p.time_range.get('end') or '…'}"
    executed = p.executed_at.strftime("%Y-%m-%d %H:%M UTC") if p.executed_at else "sin ejecución"
    dashboard = (
        f" · dashboard revisión {p.dashboard_revision_id}" if p.dashboard_revision_id else ""
    )
    return (
        f"Procedencia · dataset {p.dataset} · versión v{p.version_number} ({p.version_id}) · "
        f"ejecución {p.execution_id or '—'} · plan {p.plan_revision_id}{dashboard} · "
        f"filtros: {filters or 'ninguno'}{period} · calculado {executed}"
    )


def group_label(row: dict[str, Any], dimensions: list[dict[str, Any]]) -> str:
    labels = row.get("labels") or {}
    return " · ".join(str(labels.get(d["key"]) or "") for d in dimensions) or "Total"


def number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(Decimal(value))
    except InvalidOperation:
        return None


def data_flowables(result: dict[str, Any], p: Provenance) -> list[Flowable]:
    dimensions = result.get("dimensions") or []
    metrics = result.get("metrics") or []
    rows = result.get("rows") or []
    chosen = [m for m in metrics if p.metric is None or m["key"] == p.metric] or metrics[:1]
    flowables: list[Flowable] = []
    if p.view == "kpi" and rows:
        metric = chosen[0]
        unit = metric.get("currency") or metric.get("unit") or ""
        value = rows[0]["values"].get(metric["key"])
        flowables.append(
            Paragraph(text(f"{value if value is not None else 'sin filas'} {unit}"), KPI)
        )
    elif p.view in {"bar", "line"} and rows:
        flowables.append(chart(rows, dimensions, chosen[0], p.view))
    flowables.append(figures(rows, dimensions, chosen if p.view != "table" else metrics))
    if len(rows) * len(chosen if p.view != "table" else metrics) > MAX_ROWS:
        flowables.append(
            Paragraph(
                f"Se muestran las primeras {MAX_ROWS} cifras; el CSV del resultado las incluye "
                "todas con su evidence_id.",
                META,
            )
        )
    return flowables


def figures(
    rows: list[dict[str, Any]], dimensions: list[dict[str, Any]], metrics: list[dict[str, Any]]
) -> Table:
    """Cifras exactas (cadena canónica) con su dirección de evidencia."""
    data: list[list[Any]] = [["Grupo", "Métrica", "Valor", "evidence_id"]]
    for row in rows:
        for metric in metrics:
            if len(data) > MAX_ROWS:
                break
            key = metric["key"]
            unit = metric.get("currency") or metric.get("unit") or ""
            value = row["values"].get(key)
            data.append(
                [
                    group_label(row, dimensions)[:40],
                    str(metric["label"])[:24],
                    f"{value} {unit}".strip() if value is not None else "sin filas",
                    row["evidence"].get(key, ""),
                ]
            )
    table = Table(data, colWidths=[52 * mm, 30 * mm, 26 * mm, 72 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
                ("FONT", (0, 1), (2, -1), "Helvetica", 7.5),
                ("FONT", (3, 1), (3, -1), "Courier", 5.4),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, MUTED),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def chart(
    rows: list[dict[str, Any]], dimensions: list[dict[str, Any]], metric: dict[str, Any], view: str
) -> Drawing:
    """Gráfico vectorial de una métrica (barras o líneas) con las filas del resultado."""
    rows = rows[:40]
    drawing = Drawing(180 * mm, 62 * mm)
    values = [number(row["values"].get(metric["key"])) for row in rows]
    categories = [group_label(row, dimensions)[:14] for row in rows]
    plot = VerticalBarChart() if view == "bar" else HorizontalLineChart()
    plot.x, plot.y = 14 * mm, 12 * mm
    plot.width, plot.height = 160 * mm, 46 * mm
    plot.data = [values]  # un nulo no se dibuja: nunca se pinta como 0
    plot.categoryAxis.categoryNames = categories
    plot.categoryAxis.labels.fontSize = 6
    plot.categoryAxis.labels.angle = 30 if len(categories) > 8 else 0
    plot.categoryAxis.labels.boxAnchor = "ne" if len(categories) > 8 else "n"
    plot.valueAxis.labels.fontSize = 6
    # El eje parte de 0 (o del valor más negativo): ninguna barra queda fuera ni se exagera.
    present = [v for v in values if v is not None]
    plot.valueAxis.valueMin = min([0.0, *present])
    if isinstance(plot, VerticalBarChart):
        plot.bars[0].fillColor = ACCENT
        plot.bars[0].strokeColor = None
    else:
        plot.lines[0].strokeColor = ACCENT
        plot.lines[0].strokeWidth = 1.5
    drawing.add(plot)
    return drawing
