"""PDF de prueba con tablas reticuladas (Fase 18B), generados con ReportLab (ya es dependencia)."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])


def grid(rows: list[list[str]], repeat: bool = False) -> Table:
    table = Table(rows, repeatRows=1 if repeat else 0)
    table.setStyle(GRID)
    return table


def make_pdf(*items: Flowable | str) -> bytes:
    """Cadena = párrafo; "PAGE" = salto de página."""
    styles = getSampleStyleSheet()
    story: list[Flowable] = []
    for item in items:
        if item == "PAGE":
            story.append(PageBreak())
        elif isinstance(item, str):
            story.extend([Paragraph(item, styles["Normal"]), Spacer(1, 12)])
        else:
            story.extend([item, Spacer(1, 18)])
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, invariant=1).build(story)
    return buffer.getvalue()


def sales_rows(months: int = 12) -> list[list[str]]:
    return [["Región", "Mes", "Importe"]] + [
        ["Norte" if m % 2 else "Sur", f"2024-{m:02d}", f"{m}.{m:03d},50"]
        for m in range(1, months + 1)
    ]


def blank_pdf() -> bytes:
    """Un PDF sin texto (como uno escaneado)."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, invariant=1)
    page.rect(100, 100, 200, 200)
    page.showPage()
    page.save()
    return buffer.getvalue()
