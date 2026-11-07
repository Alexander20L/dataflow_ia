"""PDFs de prueba (Fase 12C) con reportlab: tablas con rejilla, varias tablas y sin texto."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])


def make_pdf(
    tables: list[list[list[str]]], repeat_header: bool = False, break_after: bool = False
) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, invariant=1)
    story: list[object] = [Paragraph("Informe de ventas", getSampleStyleSheet()["Title"])]
    for rows in tables:
        table = Table(rows, repeatRows=1 if repeat_header else 0)
        table.setStyle(GRID)
        story += [table, Spacer(1, 24)]
        if break_after:
            story.append(PageBreak())
    document.build(story)
    return buffer.getvalue()


def scanned_pdf() -> bytes:
    """Sólo dibujo (como una página escaneada): sin capa de texto."""
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    for row in range(5):
        page.rect(50, 700 - row * 20, 300, 20)
    page.showPage()
    page.save()
    return buffer.getvalue()
