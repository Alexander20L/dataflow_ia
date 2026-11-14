"""PDF del informe automático con ReportLab (sin base de datos, red ni navegador).

Dibuja un `ReportDocument` ya armado: no decide contenido ni calcula. Los gráficos convierten
las cifras canónicas a coma flotante sólo para dibujar; la cifra exacta y su evidencia están en
la tabla de cada bloque. `invariant=1` hace la salida reproducible para el mismo documento.
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
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Flowable

from dataflow.modules.delivery.contracts import ReportBlock, ReportChart, ReportDocument
from dataflow.modules.delivery.numbers import cap_decimals

ACCENT = colors.HexColor("#4f46e5")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
WIDTH = A4[0] - 30 * mm

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("title", parent=styles["Title"], fontSize=18, alignment=0, spaceAfter=4)
H1 = ParagraphStyle(
    "h1", parent=styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=4, textColor=ACCENT
)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
META = ParagraphStyle("meta", parent=BODY, fontSize=7.5, leading=10, textColor=MUTED)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10)
BADGE = ParagraphStyle("badge", parent=META, textColor=ACCENT)


def text(value: str) -> str:
    """Texto para el PDF. Fase 24B: cada cifra se lee con tres decimales como mucho."""
    return escape(cap_decimals(value)).replace("\n", "<br/>")


def render_pdf(document: ReportDocument) -> bytes:
    buffer = io.BytesIO()
    generated = document.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    source = document.source
    footer = (
        f"DataFlow AI · {source.file_name} v{source.version_number} · informe "
        f"{document.rules_version} · {generated}"
    )

    def on_page(canvas: Canvas, template: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 10 * mm, footer[:150])
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"pág. {template.page}")
        canvas.restoreState()

    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=document.title,
        author="DataFlow AI",
        subject=f"Versión {source.version_id} · análisis {source.analysis_sha256}",
        invariant=1,
    )
    story: list[Flowable] = [
        Paragraph(text(document.title), TITLE),
        Paragraph(
            text(
                f"Versión v{source.version_number} ({source.version_id}) · análisis "
                f"{source.analysis_execution_id} · investigación "
                f"{source.investigation_execution_id} · generado {generated}"
            ),
            META,
        ),
        Spacer(1, 4),
    ]
    for section in document.sections:
        story.append(Paragraph(text(section.title), H1))
        if section.intro:
            story.append(Paragraph(text(section.intro), BODY))
            story.append(Spacer(1, 3))
        for block in section.blocks:
            story.extend(block_flowables(block))
    template.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


def block_flowables(block: ReportBlock) -> list[Flowable]:
    head: list[Flowable] = []
    if block.title:
        head.append(Paragraph(text(block.title), H2))
    if block.badge:
        head.append(Paragraph(text(block.badge), BADGE))
    body: list[Flowable] = [Paragraph(text(item), BODY) for item in block.paragraphs]
    if block.chart is not None:
        drawing = chart(block.chart)
        if drawing is not None:
            body.append(drawing)
    if block.table is not None and block.table.rows:
        body.append(Spacer(1, 3))
        body.append(table(block.table.headers, block.table.rows))
    flowables = [KeepTogether([*head, *body[:1]]), *body[1:], Spacer(1, 5)]
    return flowables


def table(headers: list[str], rows: list[list[str]]) -> Table:
    data = [[Paragraph(f"<b>{text(item)}</b>", CELL) for item in headers]]
    data.extend([[Paragraph(text(cell), CELL) for cell in row] for row in rows])
    result = Table(data, colWidths=[WIDTH / len(headers)] * len(headers), repeatRows=1)
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return result


def axis_label(value: float) -> str:
    """Etiqueta del eje de valores con tres decimales como mucho (Fase 24B)."""
    return cap_decimals(format(Decimal(repr(value)).normalize(), "f"))


def chart(spec: ReportChart) -> Drawing | None:
    try:
        values = [float(Decimal(value)) for value in spec.values]
    except (InvalidOperation, ValueError):
        return None
    drawing = Drawing(WIDTH, 120)
    plot: VerticalBarChart | HorizontalLineChart
    if spec.type == "bar":
        plot = VerticalBarChart()
        plot.bars[0].fillColor = ACCENT
    else:
        plot = HorizontalLineChart()
        plot.lines[0].strokeColor = ACCENT
        plot.lines[0].strokeWidth = 1.5
    plot.x, plot.y, plot.width, plot.height = 40, 25, WIDTH - 60, 85
    plot.data = [values]
    plot.categoryAxis.categoryNames = [label[:14] for label in spec.labels]
    plot.categoryAxis.labels.fontSize = 6
    plot.categoryAxis.labels.angle = 30 if len(values) > 8 else 0
    plot.categoryAxis.labels.boxAnchor = "ne" if len(values) > 8 else "n"
    plot.valueAxis.labels.fontSize = 6
    plot.valueAxis.labelTextFormat = axis_label
    plot.valueAxis.valueMin = min(0.0, *values)
    drawing.add(plot)
    return drawing
