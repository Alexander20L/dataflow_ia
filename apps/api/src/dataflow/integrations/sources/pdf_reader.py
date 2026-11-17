"""Tablas de un PDF con texto (Fase 18B, regla `pdf-selection-v1`).

Sólo se usa desde el subproceso de ingesta. Se leen las tablas que pdfplumber detecta por sus
líneas; un PDF escaneado (sin texto) no se lee: haría falta OCR y no se adivina. Una tabla que
sigue en la página siguiente con la misma cabecera repetida se une a la anterior.
"""

import io
from dataclasses import dataclass, field
from typing import Any

from dataflow.platform.errors import ApplicationError

SELECTION_RULE = "pdf-selection-v1"
MAX_TABLES = 5
MAX_PAGES = 200


def fail(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, 422)


@dataclass
class PdfTable:
    """Una tabla lógica: segmentos (página, índice en la página) con la misma cabecera."""

    segments: list[tuple[int, int]]
    headers: list[str]
    rows: list[list[str | None]] = field(default_factory=list)

    @property
    def label(self) -> str:
        first, last = self.segments[0][0], self.segments[-1][0]
        pages = f"la página {first}" if first == last else f"las páginas {first}–{last}"
        return f"Tabla {self.segments[0][1] + 1} de {pages}"


@dataclass
class PdfSelection:
    main: PdfTable
    additional: list[PdfTable]
    omitted: list[tuple[str, str]]


def cell(value: str | None) -> str | None:
    """Texto de la celda: los saltos de línea del ajuste de texto se vuelven espacios."""
    if value is None:
        return None
    text = " ".join(part.strip() for part in value.splitlines()).strip()
    return text or None


def open_pdf(content: bytes) -> Any:
    import pdfplumber  # sólo en el subproceso de ingesta
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    try:
        document = pdfplumber.open(io.BytesIO(content))
        pages = len(document.pages)
    except PDFPasswordIncorrect as exc:
        raise fail("PDF_ENCRYPTED", "El PDF está protegido con contraseña.") from exc
    except Exception as exc:
        raise fail("PDF_MALFORMED", "El archivo no es un PDF legible.") from exc
    if pages > MAX_PAGES:
        document.close()
        raise fail("PDF_PAGE_LIMIT", f"El PDF tiene más de {MAX_PAGES} páginas.")
    return document


def raw_tables(content: bytes) -> tuple[list[tuple[int, int, list[list[str | None]]]], bool]:
    """(página, índice, filas) de cada tabla detectada y si el PDF tiene texto."""
    document = open_pdf(content)
    found: list[tuple[int, int, list[list[str | None]]]] = []
    has_text = False
    try:
        for number, page in enumerate(document.pages, start=1):
            has_text = has_text or bool((page.extract_text() or "").strip())
            for index, table in enumerate(page.extract_tables()):
                rows = [[cell(v) for v in row] for row in table]
                rows = [row for row in rows if any(v is not None for v in row)]
                if rows:
                    found.append((number, index, rows))
    finally:
        document.close()
    return found, has_text


def logical_tables(
    found: list[tuple[int, int, list[list[str | None]]]],
) -> tuple[list[PdfTable], list[tuple[str, str]]]:
    tables: list[PdfTable] = []
    omitted: list[tuple[str, str]] = []
    for page, index, rows in found:
        header = rows[0]
        previous = tables[-1] if tables else None
        if (
            previous is not None
            and index == 0
            and previous.segments[-1][0] == page - 1
            and header == previous.headers
        ):
            previous.segments.append((page, index))
            previous.rows.extend(rows[1:])
            continue
        names = [h for h in header if h is not None]
        if len(header) < 2 or len(names) != len(header) or len(set(names)) != len(names):
            omitted.append(
                (
                    PdfTable([(page, index)], []).label,
                    "Sin una fila de cabecera con nombres únicos en todas las columnas.",
                )
            )
            continue
        tables.append(PdfTable([(page, index)], [str(h) for h in header], rows[1:]))
    return tables, omitted


def select(content: bytes, max_rows: int, max_columns: int) -> PdfSelection:
    """Regla `pdf-selection-v1`: tablas con cabecera, al menos dos columnas y dos registros,
    dentro de los límites; la principal es la mayor (registros × columnas; empates, la primera)
    y hasta `MAX_TABLES - 1` más se analizan como versiones propias."""
    found, has_text = raw_tables(content)
    if not has_text:
        raise fail(
            "PDF_NO_TEXT",
            "El PDF no tiene texto (parece escaneado); hace falta un PDF generado por un "
            "programa, no una imagen.",
        )
    tables, omitted = logical_tables(found)
    eligible: list[PdfTable] = []
    for table in tables:
        if len(table.rows) < 2:
            omitted.append((table.label, "Menos de dos registros."))
        elif len(table.rows) > max_rows or len(table.headers) > max_columns:
            omitted.append((table.label, "Supera los límites de registros o columnas."))
        else:
            eligible.append(table)
    if not eligible:
        raise ApplicationError(
            "PDF_NO_TABLES",
            "El PDF no tiene tablas con cabecera, al menos dos columnas y dos registros.",
            422,
            {"omitted": [{"table": t, "reason": r} for t, r in omitted]},
        )
    ranked = sorted(
        enumerate(eligible), key=lambda p: (-(len(p[1].rows) * len(p[1].headers)), p[0])
    )
    chosen = [table for _, table in ranked[:MAX_TABLES]]
    omitted.extend((t.label, "Hay otras tablas más grandes.") for _, t in ranked[MAX_TABLES:])
    return PdfSelection(chosen[0], chosen[1:], omitted)


def read_table(
    content: bytes, segments: list[tuple[int, int]], max_rows: int, max_columns: int
) -> PdfTable:
    """La tabla lógica fijada en el plan, leída otra vez del original (determinista)."""
    found, _ = raw_tables(content)
    tables, _ = logical_tables(found)
    table = next((t for t in tables if t.segments == segments), None)
    if table is None:
        raise fail("PDF_TABLE_NOT_FOUND", "La tabla fijada en el plan no está en el PDF.")
    if len(table.rows) > max_rows or len(table.headers) > max_columns:
        raise fail("PDF_LIMIT", "La tabla supera los límites de registros o columnas.")
    width = len(table.headers)
    if any(len(row) != width for row in table.rows):
        raise fail("PDF_SHAPE", "La tabla tiene filas con un número distinto de columnas.")
    return table
