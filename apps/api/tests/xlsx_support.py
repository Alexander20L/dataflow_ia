"""Generador mínimo de .xlsx para pruebas (Fase 12A): sin dependencias, XML OOXML a mano.

Celdas: `str` → texto compartido, `int`/`float`/`Decimal` → número, `date`/`datetime` →
número de serie con formato de fecha, `bool`, `None` → vacía, `Formula(expr, value)` y
`ExcelError("#DIV/0!")`.
"""

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from dataflow.integrations.sources.xlsx_reader import cell_name

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class Formula:
    expression: str
    value: object = None


@dataclass(frozen=True)
class ExcelError:
    code: str


@dataclass
class Sheet:
    name: str
    rows: list[list[object]]
    first_row: int = 1
    first_col: int = 1
    tables: list[tuple[str, str]] = field(default_factory=list)  # (nombre, ref)
    merges: list[str] = field(default_factory=list)
    protected: bool = False
    hidden: bool = False


def serial(value: date | datetime) -> str:
    base = datetime(1899, 12, 30)
    moment = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
    delta = moment - base
    number = Decimal(delta.days) + Decimal(delta.seconds) / Decimal(86400)
    return format(number.normalize(), "f")


def make_xlsx(sheets: list[Sheet], macro: bool = False) -> bytes:
    shared: list[str] = []
    index: dict[str, int] = {}

    def cell(ref: str, value: object) -> str:
        if value is None:
            return ""
        formula = ""
        if isinstance(value, Formula):
            formula = f"<f>{escape(value.expression)}</f>"
            value = value.value
            if value is None:
                return f'<c r="{ref}">{formula}</c>'
        if isinstance(value, ExcelError):
            return f'<c r="{ref}" t="e">{formula}<v>{escape(value.code)}</v></c>'
        if isinstance(value, bool):
            return f'<c r="{ref}" t="b">{formula}<v>{int(value)}</v></c>'
        if isinstance(value, (date, datetime)):
            return f'<c r="{ref}" s="1">{formula}<v>{serial(value)}</v></c>'
        if isinstance(value, (int, float, Decimal)):
            return f'<c r="{ref}">{formula}<v>{value}</v></c>'
        text = str(value)
        if formula:
            return f'<c r="{ref}" t="str">{formula}<v>{escape(text)}</v></c>'
        if text not in index:
            index[text] = len(shared)
            shared.append(text)
        return f'<c r="{ref}" t="s"><v>{index[text]}</v></c>'

    files: dict[str, str] = {}
    workbook_rels = []
    sheet_entries = []
    overrides = []
    table_number = 0
    for number, sheet in enumerate(sheets, start=1):
        rows_xml = []
        for offset, row in enumerate(sheet.rows):
            r = sheet.first_row + offset
            cells = "".join(cell(cell_name(r, sheet.first_col + c), v) for c, v in enumerate(row))
            rows_xml.append(f'<row r="{r}">{cells}</row>')
        extra = ""
        if sheet.protected:
            extra += '<sheetProtection sheet="1" objects="1"/>'
        if sheet.merges:
            extra += (
                f'<mergeCells count="{len(sheet.merges)}">'
                + "".join(f'<mergeCell ref="{m}"/>' for m in sheet.merges)
                + "</mergeCells>"
            )
        table_parts = ""
        sheet_rels = []
        if sheet.tables:
            parts = []
            for position, (name, ref) in enumerate(sheet.tables, start=1):
                table_number += 1
                files[f"xl/tables/table{table_number}.xml"] = (
                    f'<?xml version="1.0" encoding="UTF-8"?><table xmlns="{MAIN}" '
                    f'id="{table_number}" name="{name}" displayName="{name}" ref="{ref}"/>'
                )
                overrides.append(
                    f'<Override PartName="/xl/tables/table{table_number}.xml" ContentType="'
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>'
                )
                sheet_rels.append(
                    f'<Relationship Id="rId{position}" Type="{REL}/table" '
                    f'Target="../tables/table{table_number}.xml"/>'
                )
                parts.append(f'<tablePart r:id="rId{position}"/>')
            table_parts = f'<tableParts count="{len(parts)}">' + "".join(parts) + "</tableParts>"
            files[f"xl/worksheets/_rels/sheet{number}.xml.rels"] = (
                f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
                + "".join(sheet_rels)
                + "</Relationships>"
            )
        files[f"xl/worksheets/sheet{number}.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}" xmlns:r="{REL}">'
            f"<sheetData>{''.join(rows_xml)}</sheetData>{extra}{table_parts}</worksheet>"
        )
        workbook_rels.append(
            f'<Relationship Id="rId{number}" Type="{REL}/worksheet" '
            f'Target="worksheets/sheet{number}.xml"/>'
        )
        state = ' state="hidden"' if sheet.hidden else ""
        sheet_entries.append(
            f'<sheet name="{escape(sheet.name)}" sheetId="{number}"{state} r:id="rId{number}"/>'
        )
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{number}.xml" ContentType="'
            'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    count = len(sheets)
    workbook_rels.append(
        f'<Relationship Id="rId{count + 1}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
    )
    workbook_rels.append(
        f'<Relationship Id="rId{count + 2}" Type="{REL}/styles" Target="styles.xml"/>'
    )
    files["xl/sharedStrings.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{MAIN}" count="{len(shared)}" '
        f'uniqueCount="{len(shared)}">'
        + "".join(f'<si><t xml:space="preserve">{escape(t)}</t></si>' for t in shared)
        + "</sst>"
    )
    files["xl/styles.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="{MAIN}">'
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>'
        '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164" applyNumberFormat="1"/></cellXfs>'
        "</styleSheet>"
    )
    files["xl/workbook.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" xmlns:r="{REL}">'
        f"<sheets>{''.join(sheet_entries)}</sheets></workbook>"
    )
    files["xl/_rels/workbook.xml.rels"] = (
        f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
        + "".join(workbook_rels)
        + "</Relationships>"
    )
    files["_rels/.rels"] = (
        f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
        f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    main_type = (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
        if macro
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    files["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="'
        'http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="'
        'application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/xl/workbook.xml" ContentType="{main_type}"/>'
        + "".join(overrides)
        + "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            # Fecha fija: el mismo contenido produce los mismos bytes (hash estable).
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return buffer.getvalue()
