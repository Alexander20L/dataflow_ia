"""Lector de `.xlsx` (Fase 12A): una hoja o tabla con nombre → cabeceras y filas de texto.

Lee el paquete OOXML directamente (zip + XML de la biblioteca estándar), sin dependencias
nuevas, y sólo se ejecuta dentro del subproceso aislado de ingesta. Reglas:

- Fórmulas: se usa el **resultado guardado**; nunca se recalcula. Sin resultado → error.
- Fechas: un número con formato de fecha se convierte a texto ISO (`YYYY-MM-DD`,
  `YYYY-MM-DDTHH:MM:SS` o `HH:MM:SS`); la conversión de tipo sigue siendo la de Limpieza.
- Números: representación decimal canónica (sin exponente ni ceros sobrantes); más de 15
  cifras significativas → advertencia (no tienen representación exacta en Excel).
- Booleanos `true`/`false`; celdas vacías → nulo; errores de Excel (`#DIV/0!`…) → error.
- Celdas combinadas en el rango, hojas protegidas, libros con macros, `.xls`/`.xlsb` o
  cifrados → error con código. Nunca se devuelve una tabla «aproximada».
"""

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from posixpath import dirname, join, normpath
from typing import IO
from xml.etree.ElementTree import Element, iterparse

from dataflow.platform.errors import ApplicationError

READER_VERSION = "xlsx-reader-1"
MAX_PART_BYTES = 64 * 1024 * 1024  # XML descomprimido de una parte
MAX_PACKAGE_BYTES = 160 * 1024 * 1024  # paquete completo descomprimido
MAX_WARNINGS = 20
REL_TYPES = "/officeDocument/2006/relationships/"
DATE_FORMAT_IDS = {*range(14, 23), *range(27, 37), 45, 46, 47, *range(50, 59)}
CELL_REF = re.compile(r"^([A-Z]{1,3})([0-9]{1,7})$")
DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


def fail(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, 422)


@dataclass(frozen=True)
class SheetInfo:
    name: str
    path: str
    hidden: bool
    tables: list[str]


@dataclass(frozen=True)
class TableInfo:
    name: str
    sheet: str
    first_row: int
    first_col: int
    last_row: int
    last_col: int
    header_rows: int
    totals_rows: int


@dataclass
class ReadResult:
    sheet: str
    table: str | None
    header_row: int
    headers: list[str]
    rows: list[list[str | None]]
    warnings: list[dict[str, str]] = field(default_factory=list)
    warning_count: int = 0


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attribute(element: Element, name: str) -> str | None:
    """Atributo por nombre local (r:id existe en el espacio transicional y en el estricto)."""
    for key, value in element.attrib.items():
        if local(key) == name:
            return value
    return None


def column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index


def column_letters(index: int) -> str:
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def cell_name(row: int, column: int) -> str:
    return f"{column_letters(column)}{row}"


def parse_ref(ref: str) -> tuple[int, int]:
    match = CELL_REF.match(ref.replace("$", "").upper())
    if not match:
        raise fail("XLSX_MALFORMED", f"Referencia de celda no válida: {ref[:20]}.")
    return int(match.group(2)), column_index(match.group(1))


def parse_range(ref: str) -> tuple[int, int, int, int]:
    first, _, last = ref.partition(":")
    top, left = parse_ref(first)
    bottom, right = parse_ref(last or first)
    return top, left, bottom, right


def is_date_format(code: str) -> bool:
    """Primera sección del formato, sin literales ni corchetes ([Red], [$-409]; [h] es una
    duración, no una fecha)."""
    section = code.split(";", 1)[0]
    if re.search(r"\[(h+|m+|s+)\]", section, re.IGNORECASE):
        return False
    section = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", section)
    return bool(re.search(r"[dmyhs]", section, re.IGNORECASE))


def canonical_number(text: str) -> tuple[str, bool]:
    """(representación decimal canónica, ¿supera 15 cifras significativas?)."""
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise fail("XLSX_MALFORMED", "El libro contiene un número no válido.") from exc
    if not value.is_finite():
        raise fail("XLSX_MALFORMED", "El libro contiene un número no finito.")
    if value == 0:
        return "0", False
    normalized = value.normalize()
    inexact = len(normalized.as_tuple().digits) > 15
    if normalized == normalized.to_integral_value():
        return str(int(normalized)), inexact
    return format(normalized, "f"), inexact


def excel_date(serial_text: str, date1904: bool, ref: str) -> str:
    serial = Decimal(serial_text)
    if serial < 0:
        raise fail("XLSX_DATE_INVALID", f"La celda {ref} tiene una fecha negativa.")
    whole = int(serial)
    seconds = int(((serial - whole) * 86400).to_integral_value())
    if seconds == 86400:
        whole, seconds = whole + 1, 0
    clock = (datetime.min + timedelta(seconds=seconds)).time()
    if whole == 0 and not date1904:
        return clock.isoformat()
    if date1904:
        day = date(1904, 1, 1) + timedelta(days=whole)
    elif whole == 60:
        raise fail("XLSX_DATE_INVALID", f"La celda {ref} usa el 29/02/1900, que no existe.")
    else:
        day = date(1899, 12, 31 if whole < 60 else 30) + timedelta(days=whole)
    return day.isoformat() if seconds == 0 else datetime.combine(day, clock).isoformat()


class Workbook:
    def __init__(self, content: bytes) -> None:
        if content[:4] != b"PK\x03\x04":
            raise fail(
                "UNSUPPORTED_FORMAT",
                "El archivo no es un .xlsx (¿un .xls antiguo o un libro cifrado con contraseña?).",
            )
        try:
            self.zip = zipfile.ZipFile(BytesIO(content))
            infos = self.zip.infolist()
        except (zipfile.BadZipFile, OSError) as exc:
            raise fail("UNSUPPORTED_FORMAT", "El archivo .xlsx está dañado.") from exc
        self.names = {info.filename for info in infos}
        if sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES:
            raise fail("XLSX_EXPANDED_LIMIT", "El libro descomprimido supera el límite permitido.")
        if "[Content_Types].xml" not in self.names:
            raise fail("UNSUPPORTED_FORMAT", "El archivo no es un libro de Excel .xlsx.")
        types = self.read("[Content_Types].xml").decode("utf-8", "replace").lower()
        if "macroenabled" in types or any(n.lower().endswith("vbaproject.bin") for n in self.names):
            raise fail("UNSUPPORTED_FORMAT", "Los libros con macros (.xlsm) no se admiten.")
        if "sheet.binary" in types or any(n.lower().endswith(".bin") for n in self.names):
            raise fail("UNSUPPORTED_FORMAT", "Los libros binarios (.xlsb) no se admiten.")
        root_rels = self.relationships("_rels/.rels", "")
        workbook = next(
            (t for kind, t in root_rels.values() if kind == "officeDocument"), "xl/workbook.xml"
        )
        if workbook not in self.names:
            raise fail("UNSUPPORTED_FORMAT", "El archivo no contiene un libro de Excel.")
        rels_path = join(dirname(workbook), "_rels", workbook.rsplit("/", 1)[-1] + ".rels")
        rels = self.relationships(rels_path, dirname(workbook))
        self.date1904 = False
        sheets: list[tuple[str, str, bool]] = []
        for element in self.elements(workbook):
            name = local(element.tag)
            if name == "workbookPr":
                self.date1904 = (attribute(element, "date1904") or "").lower() in {"1", "true"}
            elif name == "sheet":
                relation = rels.get(attribute(element, "id") or "")
                if relation and relation[0] == "worksheet":
                    sheets.append(
                        (
                            attribute(element, "name") or "",
                            relation[1],
                            (attribute(element, "state") or "visible") != "visible",
                        )
                    )
        if not sheets:
            raise fail("XLSX_NO_SHEETS", "El libro no contiene hojas de cálculo.")
        self.shared_path = next((t for k, t in rels.values() if k == "sharedStrings"), None)
        self.styles_path = next((t for k, t in rels.values() if k == "styles"), None)
        self.tables: list[TableInfo] = []
        self.sheets: list[SheetInfo] = []
        for name, path, hidden in sheets:
            sheet_rels = join(dirname(path), "_rels", path.rsplit("/", 1)[-1] + ".rels")
            tables = []
            for kind, target in self.relationships(sheet_rels, dirname(path)).values():
                if kind == "table" and target in self.names:
                    table = self.table(target, name)
                    self.tables.append(table)
                    tables.append(table.name)
            self.sheets.append(SheetInfo(name, path, hidden, tables))
        self._shared: list[str] | None = None
        self._dates: list[bool] | None = None

    # --- partes del paquete -------------------------------------------------------------
    def read(self, name: str) -> bytes:
        info = self.zip.getinfo(name)
        if info.file_size > MAX_PART_BYTES:
            raise fail("XLSX_EXPANDED_LIMIT", "Una hoja descomprimida supera el límite permitido.")
        with self.zip.open(info) as stream:
            data = stream.read(MAX_PART_BYTES + 1)
        if len(data) > MAX_PART_BYTES:
            raise fail("XLSX_EXPANDED_LIMIT", "Una hoja descomprimida supera el límite permitido.")
        return data

    def stream(self, name: str) -> IO[bytes]:
        if name not in self.names:
            raise fail("XLSX_MALFORMED", "Falta una parte del libro.")
        info = self.zip.getinfo(name)
        if info.file_size > MAX_PART_BYTES:
            raise fail("XLSX_EXPANDED_LIMIT", "Una hoja descomprimida supera el límite permitido.")
        with self.zip.open(info) as head:
            if DOCTYPE.search(head.read(4096)):
                raise fail("XLSX_MALFORMED", "El libro contiene declaraciones XML no admitidas.")
        return self.zip.open(info)

    def elements(self, name: str) -> Iterator[Element]:
        """Elementos al cerrarse (iterparse en flujo). No se resuelven entidades: se rechaza
        cualquier DOCTYPE antes de analizar."""
        with self.stream(name) as handle:
            try:
                for _, element in iterparse(handle, events=("end",)):
                    yield element
            except SyntaxError as exc:  # ParseError
                raise fail("XLSX_MALFORMED", "El XML del libro está dañado.") from exc

    def relationships(self, path: str, base: str) -> dict[str, tuple[str, str]]:
        if path not in self.names:
            return {}
        result: dict[str, tuple[str, str]] = {}
        for element in self.elements(path):
            if local(element.tag) != "Relationship":
                continue
            if (element.get("TargetMode") or "") == "External":
                continue
            kind = (element.get("Type") or "").rsplit("/", 1)[-1]
            target = element.get("Target") or ""
            resolved = target.lstrip("/") if target.startswith("/") else join(base, target)
            result[element.get("Id") or ""] = (kind, normpath(resolved))
        return result

    def table(self, path: str, sheet: str) -> TableInfo:
        root = next(e for e in self.elements(path) if local(e.tag) == "table")
        top, left, bottom, right = parse_range(root.get("ref") or "")
        return TableInfo(
            root.get("displayName") or root.get("name") or "",
            sheet,
            top,
            left,
            bottom,
            right,
            int(root.get("headerRowCount") or 1),
            int(root.get("totalsRowCount") or 0),
        )

    @property
    def shared(self) -> list[str]:
        if self._shared is None:
            self._shared = []
            if self.shared_path and self.shared_path in self.names:
                for element in self.elements(self.shared_path):
                    if local(element.tag) == "si":
                        self._shared.append(rich_text(element))
                        element.clear()
        return self._shared

    @property
    def dates(self) -> list[bool]:
        """¿El estilo `s` de una celda es un formato de fecha?"""
        if self._dates is None:
            custom: dict[int, str] = {}
            xfs: list[int] = []
            if self.styles_path and self.styles_path in self.names:
                inside_cell_xfs = False
                with self.stream(self.styles_path) as handle:
                    for event, element in iterparse(handle, events=("start", "end")):
                        name = local(element.tag)
                        if name == "cellXfs":
                            inside_cell_xfs = event == "start"
                        elif event == "end" and name == "numFmt":
                            custom[int(element.get("numFmtId") or 0)] = (
                                element.get("formatCode") or ""
                            )
                        elif event == "end" and name == "xf" and inside_cell_xfs:
                            xfs.append(int(element.get("numFmtId") or 0))
            self._dates = [
                (fmt in custom and is_date_format(custom[fmt]))
                or (fmt not in custom and fmt in DATE_FORMAT_IDS)
                for fmt in xfs
            ]
        return self._dates

    # --- lectura de una hoja ------------------------------------------------------------
    def select(self, sheet: str | None, table: str | None) -> tuple[SheetInfo, TableInfo | None]:
        if table:
            found = next((t for t in self.tables if t.name == table), None)
            if not found:
                raise fail("XLSX_TABLE_NOT_FOUND", f"El libro no contiene la tabla «{table}».")
            if sheet and sheet != found.sheet:
                raise fail("XLSX_TABLE_NOT_FOUND", f"La tabla «{table}» no está en «{sheet}».")
            return next(s for s in self.sheets if s.name == found.sheet), found
        if sheet is None:
            visible = [s for s in self.sheets if not s.hidden] or self.sheets
            return visible[0], None
        chosen = next((s for s in self.sheets if s.name == sheet), None)
        if not chosen:
            raise fail("XLSX_SHEET_NOT_FOUND", f"El libro no contiene la hoja «{sheet}».")
        return chosen, None

    def cells(
        self, sheet: SheetInfo, max_cells: int
    ) -> tuple[dict[int, dict[int, str | None]], list[tuple[int, int, int, int]], bool, list[str]]:
        """Celdas con valor por fila y columna, rangos combinados, protección e inexactos."""
        rows: dict[int, dict[int, str | None]] = {}
        merges: list[tuple[int, int, int, int]] = []
        protected = False
        inexact: list[str] = []
        count = 0
        row_number = 0
        column = 0
        for element in self.elements(sheet.path):
            name = local(element.tag)
            if name == "c":
                ref = element.get("r")
                if ref:
                    row_number, column = parse_ref(ref)
                else:
                    column += 1
                value = self.value(element, cell_name(row_number, column), inexact)
                if value is not None:
                    count += 1
                    if count > max_cells:
                        raise fail(
                            "XLSX_EXPANDED_LIMIT",
                            "La hoja tiene más celdas con datos de las permitidas.",
                        )
                    rows.setdefault(row_number, {})[column] = value
                element.clear()
            elif name == "row":
                element.clear()
            elif name == "mergeCell":
                merges.append(parse_range(element.get("ref") or ""))
            elif name == "sheetProtection":
                protected = (element.get("sheet") or "").lower() in {"1", "true"}
        return rows, merges, protected, inexact

    def value(self, cell: Element, ref: str, inexact: list[str]) -> str | None:
        kind = cell.get("t") or "n"
        formula = value = inline = None
        for child in cell:
            name = local(child.tag)
            if name == "f":
                formula = child
            elif name == "v":
                value = child.text or ""
            elif name == "is":
                inline = child
        if formula is not None and value is None:
            raise fail(
                "XLSX_FORMULA_WITHOUT_VALUE",
                f"La celda {ref} tiene una fórmula sin resultado guardado. Abre el libro en "
                "Excel, guárdalo y vuelve a subirlo.",
            )
        if kind == "inlineStr":
            text = rich_text(inline) if inline is not None else ""
        elif value is None:
            return None
        elif kind == "s":
            try:
                text = self.shared[int(value)]
            except (ValueError, IndexError) as exc:
                raise fail(
                    "XLSX_MALFORMED", f"La celda {ref} apunta a un texto inexistente."
                ) from exc
        elif kind in {"str", "d"}:
            text = value
        elif kind == "b":
            text = "true" if value.strip() in {"1", "true"} else "false"
        elif kind == "e":
            raise fail(
                "XLSX_CELL_ERROR",
                f"La celda {ref} contiene el error de Excel {value[:16]}; corrígelo antes de "
                "importar.",
            )
        else:
            style = int(cell.get("s") or 0)
            if style < len(self.dates) and self.dates[style] and value.strip():
                return excel_date(value.strip(), self.date1904, ref)
            text, too_precise = canonical_number(value.strip())
            if too_precise:
                inexact.append(ref)
        return text if text != "" else None

    def read_table(
        self,
        sheet_name: str | None,
        table_name: str | None,
        header_row: int,
        max_rows: int,
        max_columns: int,
    ) -> ReadResult:
        sheet, table = self.select(sheet_name, table_name)
        rows, merges, protected, inexact = self.cells(sheet, max(1, max_rows + 1) * max_columns)
        if protected:
            raise fail(
                "XLSX_PROTECTED",
                f"La hoja «{sheet.name}» está protegida; quita la protección y vuelve a subirla.",
            )
        if table:
            if table.header_rows != 1:
                raise fail(
                    "XLSX_TABLE_NO_HEADER", f"La tabla «{table.name}» no tiene fila de cabecera."
                )
            header_row = table.first_row
            left, right = table.first_col, table.last_col
            last = table.last_row - table.totals_rows
        else:
            header = rows.get(header_row, {})
            filled = [c for c, v in header.items() if v is not None and v.strip()]
            if not filled:
                raise fail(
                    "XLSX_HEADERS", f"La fila {header_row} de «{sheet.name}» no tiene cabeceras."
                )
            left, right = min(filled), max(filled)
            last = max(rows) if rows else header_row
        if right - left + 1 > max_columns:
            raise fail("XLSX_COLUMN_LIMIT", "La tabla supera el límite de columnas.")
        headers: list[str] = []
        for column in range(left, right + 1):
            text = rows.get(header_row, {}).get(column)
            ref = cell_name(header_row, column)
            if text is None or not text.strip() or len(text) > 200:
                raise fail(
                    "XLSX_HEADERS",
                    f"La cabecera {ref} está vacía o supera 200 caracteres; cada columna "
                    "necesita un nombre.",
                )
            headers.append(text)
        if len(set(headers)) != len(headers):
            raise fail(
                "XLSX_DUPLICATE_HEADERS", "La cabecera contiene nombres de columna repetidos."
            )
        data: list[list[str | None]] = []
        last_data = header_row
        for number in sorted(rows):
            if number <= header_row or number > last:
                continue
            cells = rows[number]
            if not table:
                outside = [c for c in cells if (c < left or c > right) and cells[c] is not None]
                if outside:
                    raise fail(
                        "XLSX_SHAPE",
                        f"La celda {cell_name(number, outside[0])} tiene datos fuera de las "
                        "columnas de la cabecera. Elige una tabla con nombre o limpia esas celdas.",
                    )
            values = [cells.get(column) for column in range(left, right + 1)]
            if all(value is None for value in values):
                continue
            if len(data) >= max_rows:
                raise fail("XLSX_ROW_LIMIT", "La tabla supera el límite de registros.")
            data.append(values)
            last_data = number
        if not data:
            raise fail("XLSX_NO_ROWS", "La tabla no contiene registros después de la cabecera.")
        bottom = last if table else last_data
        for top, first, end, final in merges:
            if top <= bottom and end >= header_row and first <= right and final >= left:
                raise fail(
                    "XLSX_MERGED_CELLS",
                    f"El rango {cell_name(top, first)}:{cell_name(end, final)} tiene celdas "
                    "combinadas; sepáralas antes de importar.",
                )
        warnings = [
            {
                "code": "XLSX_INEXACT_NUMBER",
                "cell": ref,
                "message": "Número con más de 15 cifras significativas; Excel no lo guarda exacto.",
            }
            for ref in inexact[:MAX_WARNINGS]
        ]
        return ReadResult(
            sheet.name,
            table.name if table else None,
            header_row,
            headers,
            data,
            warnings,
            len(inexact),
        )


def rich_text(element: Element) -> str:
    """Texto de un <si>/<is>: <t> directos y de las «runs» <r>, sin la fonética <rPh>."""
    parts: list[str] = []
    for child in element:
        name = local(child.tag)
        if name == "t":
            parts.append(child.text or "")
        elif name == "r":
            parts.extend(t.text or "" for t in child if local(t.tag) == "t")
    return "".join(parts)


def read_xlsx(
    content: bytes,
    sheet: str | None,
    table: str | None,
    header_row: int,
    max_rows: int,
    max_columns: int,
) -> ReadResult:
    return Workbook(content).read_table(sheet, table, header_row, max_rows, max_columns)
