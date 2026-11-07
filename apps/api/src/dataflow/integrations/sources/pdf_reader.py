"""Lector de tablas de PDF con capa de texto (Fase 12C) con pdfplumber.

Sólo se ejecuta en el subproceso aislado de ingesta. Reglas:

- Un PDF sin capa de texto (escaneado) → `PDF_NO_TEXT_LAYER`; el OCR es otro incremento.
- Se listan las tablas candidatas por página (`p<página>-t<n>`) con su vista previa; nunca se
  elige una en silencio: la importación exige los identificadores elegidos por la persona.
- Estructura validada: mismo número de columnas en todas las filas, cabeceras no vacías y
  únicas. Una tabla dudosa se lista con sus problemas y no se puede importar.
- Varias tablas sólo se unen si la persona las elige juntas (continuación en otra página):
  mismo número de columnas; una cabecera repetida al inicio de la continuación se omite.
- Texto de celda normalizado: espacios y saltos de línea internos colapsados; vacía → nulo.
"""

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from dataflow.platform.errors import ApplicationError

READER_VERSION = "pdf-reader-1"
MAX_PAGES = 100
PREVIEW_ROWS = 10


def fail(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, 422)


@dataclass
class Candidate:
    id: str
    page: int
    index: int
    headers: list[str | None]
    rows: list[list[str | None]]
    issues: list[str] = field(default_factory=list)


def cell(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def candidates(content: bytes, max_rows: int, max_columns: int) -> tuple[int, list[Candidate]]:
    if not content.startswith(b"%PDF-"):
        raise fail("UNSUPPORTED_FORMAT", "El archivo no es un PDF.")
    import pdfplumber

    try:
        document = pdfplumber.open(BytesIO(content))
        pages = document.pages
    except Exception as exc:
        if "PDFPassword" in repr(exc):
            raise fail("PDF_ENCRYPTED", "El PDF está protegido con contraseña.") from None
        raise fail("PDF_MALFORMED", "El PDF está dañado o no se puede leer.") from None
    with document:
        if len(pages) > MAX_PAGES:
            raise fail("PDF_PAGE_LIMIT", f"El PDF supera {MAX_PAGES} páginas.")
        has_text = False
        found: list[Candidate] = []
        for number, page in enumerate(pages, start=1):
            if page.chars:
                has_text = True
            for index, table in enumerate(page.extract_tables(), start=1):
                rows = [[cell(value) for value in row] for row in table]
                rows = [row for row in rows if any(value is not None for value in row)]
                if not rows:
                    continue
                candidate = Candidate(f"p{number}-t{index}", number, index, rows[0], rows[1:])
                widths = {len(row) for row in rows}
                if len(widths) != 1:
                    candidate.issues.append("Las filas no tienen el mismo número de columnas.")
                if len(rows[0]) > max_columns:
                    candidate.issues.append("Supera el límite de columnas.")
                if len(rows) - 1 > max_rows:
                    candidate.issues.append("Supera el límite de filas.")
                if any(h is None or len(h) > 200 for h in rows[0]):
                    candidate.issues.append("Hay cabeceras vacías o combinadas.")
                elif len(set(rows[0])) != len(rows[0]):
                    candidate.issues.append("Hay cabeceras repetidas.")
                if len(rows) < 2:
                    candidate.issues.append("No tiene filas después de la cabecera.")
                found.append(candidate)
        if not has_text:
            raise fail(
                "PDF_NO_TEXT_LAYER",
                "El PDF no tiene capa de texto (¿escaneado?). El OCR aún no está disponible.",
            )
        return len(pages), found


def inspect(content: bytes, max_rows: int, max_columns: int) -> dict[str, Any]:
    pages, found = candidates(content, max_rows, max_columns)
    return {
        "pages": pages,
        "tables": [
            {
                "id": c.id,
                "page": c.page,
                "index": c.index,
                "columns": c.headers,
                "rows": c.rows[:PREVIEW_ROWS],
                "row_count": len(c.rows),
                "issues": c.issues,
            }
            for c in found
        ],
    }


def read_tables(
    content: bytes, table_ids: list[str], max_rows: int, max_columns: int
) -> tuple[list[str], list[list[str | None]]]:
    """Las tablas elegidas, en el orden dado; más de una sólo como continuación confirmada."""
    if not table_ids:
        raise fail("PDF_TABLE_REQUIRED", "Elige la tabla que quieres importar.")
    if len(set(table_ids)) != len(table_ids):
        raise fail("PDF_TABLE_REQUIRED", "Una tabla está elegida más de una vez.")
    _, found = candidates(content, max_rows, max_columns)
    by_id = {c.id: c for c in found}
    chosen = []
    for table_id in table_ids:
        if table_id not in by_id:
            raise fail("PDF_TABLE_NOT_FOUND", f"El PDF no contiene la tabla {table_id}.")
        chosen.append(by_id[table_id])
    first = chosen[0]
    if first.issues:
        raise fail("PDF_TABLE_AMBIGUOUS", f"La tabla {first.id}: {first.issues[0]}")
    headers = [h for h in first.headers if h is not None]
    rows = list(first.rows)
    for continuation in chosen[1:]:
        width = {len(continuation.headers), *(len(r) for r in continuation.rows)}
        if width != {len(headers)}:
            raise fail(
                "PDF_UNION_MISMATCH",
                f"La tabla {continuation.id} no tiene las mismas columnas que {first.id}.",
            )
        if continuation.headers != first.headers:
            rows.append(continuation.headers)  # sin cabecera repetida: su primera fila es dato
        rows.extend(continuation.rows)
    if len(rows) > max_rows:
        raise fail("PDF_ROW_LIMIT", "La tabla supera el límite de filas.")
    if not rows:
        raise fail("PDF_NO_ROWS", "La tabla no tiene filas después de la cabecera.")
    return headers, rows
