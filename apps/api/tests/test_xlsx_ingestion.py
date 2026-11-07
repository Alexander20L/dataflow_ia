"""Fase 12A: importación de Excel (.xlsx) con la misma tabla que produce el CSV."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project, upload
from xlsx_support import ExcelError, Formula, Sheet, make_xlsx

from dataflow.integrations.sources.xlsx_reader import (
    canonical_number,
    excel_date,
    is_date_format,
    read_xlsx,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.errors import ApplicationError

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXAMPLE = Path(__file__).resolve().parents[3] / "examples"


def read(content: bytes, sheet: str | None = None, table: str | None = None, header: int = 1):
    return read_xlsx(content, sheet, table, header, 1000, 64)


def error_code(content: bytes, **kwargs: object) -> str:
    with pytest.raises(ApplicationError) as caught:
        read(content, **kwargs)  # type: ignore[arg-type]
    return caught.value.code


def test_canonical_numbers_dates_and_formats() -> None:
    assert canonical_number("100.50") == ("100.5", False)
    assert canonical_number("1E-3") == ("0.001", False)
    assert canonical_number("12000") == ("12000", False)
    assert canonical_number("1.2E+4") == ("12000", False)
    assert canonical_number("0.30000000000000004") == ("0.30000000000000004", True)
    assert excel_date("46023", False, "A1") == "2026-01-01"
    assert excel_date("46023.5", False, "A1") == "2026-01-01T12:00:00"
    assert excel_date("0.25", False, "A1") == "06:00:00"
    assert excel_date("59", False, "A1") == "1900-02-28"
    assert excel_date("61", False, "A1") == "1900-03-01"
    assert excel_date("0", True, "A1") == "1904-01-01"
    assert is_date_format("dd/mm/yyyy") and is_date_format("yyyy-mm-dd hh:mm")
    assert not is_date_format("#,##0.00") and not is_date_format("[h]:mm")
    assert not is_date_format('0.00 "días"') and not is_date_format("[Red]0.00")


def test_reads_sheet_with_types_offset_header_and_blank_rows() -> None:
    content = make_xlsx(
        [
            Sheet("Notas", [["nota"], ["sin datos"]]),
            Sheet(
                "Ventas",
                [
                    ["Informe de ventas"],
                    [],
                    ["id", "fecha", "importe", "activo", "total"],
                    ["001", date(2026, 1, 2), Decimal("100.50"), True, Formula("C4*2", 201)],
                    [],
                    ["002", datetime(2026, 1, 3, 8, 30), 7, False, Formula('"x"&A6', "x002")],
                ],
                first_col=2,
            ),
        ]
    )
    result = read(content, "Ventas", header=3)
    assert result.headers == ["id", "fecha", "importe", "activo", "total"]
    assert result.rows == [
        ["001", "2026-01-02", "100.5", "true", "201"],
        ["002", "2026-01-03T08:30:00", "7", "false", "x002"],
    ]
    # Sin hoja elegida: la primera visible.
    assert read(content).sheet == "Notas"


def test_named_table_is_read_by_its_range_and_ignores_cells_around_it() -> None:
    content = make_xlsx(
        [
            Sheet(
                "Datos",
                [
                    ["nota suelta", None, None, None, "otra"],
                    [None, "sku", "stock"],
                    [None, "A-1", 5],
                    [None, "B-2", 7],
                    ["fuera", None, None, None, 99],
                ],
                tables=[("Inventario", "B2:C4")],
            )
        ]
    )
    result = read(content, table="Inventario")
    assert (result.sheet, result.table, result.header_row) == ("Datos", "Inventario", 2)
    assert result.rows == [["A-1", "5"], ["B-2", "7"]]
    # Por hoja, las celdas fuera de las columnas de la cabecera son un error explícito.
    assert error_code(content, sheet="Datos", header=2) == "XLSX_SHAPE"


@pytest.mark.parametrize(
    ("sheet", "code"),
    [
        (Sheet("H", [["a", "a"], [1, 2]]), "XLSX_DUPLICATE_HEADERS"),
        (Sheet("H", [["a", None, "c"], [1, 2, 3]]), "XLSX_HEADERS"),
        (Sheet("H", [["a"]]), "XLSX_NO_ROWS"),
        (Sheet("H", [["a"], [Formula("1/0")]]), "XLSX_FORMULA_WITHOUT_VALUE"),
        (Sheet("H", [["a"], [ExcelError("#DIV/0!")]]), "XLSX_CELL_ERROR"),
        (Sheet("H", [["a", "b"], [1, 2]], merges=["A2:B2"]), "XLSX_MERGED_CELLS"),
        (Sheet("H", [["a"], [1]], protected=True), "XLSX_PROTECTED"),
    ],
)
def test_ambiguous_or_unsafe_sheets_fail_with_a_code(sheet: Sheet, code: str) -> None:
    assert error_code(make_xlsx([sheet])) == code


def test_rejects_other_formats_and_limits() -> None:
    assert error_code(b"\xd0\xcf\x11\xe0legacy") == "UNSUPPORTED_FORMAT"
    assert error_code(make_xlsx([Sheet("H", [["a"], [1]])], macro=True)) == "UNSUPPORTED_FORMAT"
    assert error_code(make_xlsx([Sheet("H", [["a"], [1]])]), sheet="Otra") == "XLSX_SHEET_NOT_FOUND"
    many = make_xlsx([Sheet("H", [["a"], *[[n] for n in range(5)]])])
    with pytest.raises(ApplicationError) as caught:
        read_xlsx(many, None, None, 1, 3, 64)
    assert caught.value.code in {"XLSX_ROW_LIMIT", "XLSX_EXPANDED_LIMIT"}


def test_rejects_doctype_declarations() -> None:
    import io
    import zipfile

    source = zipfile.ZipFile(io.BytesIO(make_xlsx([Sheet("H", [["a"], [1]])])))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b"?>", b'?><!DOCTYPE x [<!ENTITY a "aaaa">]>', 1).replace(
                    b"<v>1</v>", b"<v>&a;</v>"
                )
            target.writestr(item, data)
    assert error_code(buffer.getvalue()) == "XLSX_MALFORMED"


def example_workbook() -> bytes:
    """ventas_calidad.csv como libro: números como números y fechas como fechas."""
    lines = (EXAMPLE / "ventas_calidad.csv").read_text(encoding="utf-8").splitlines()
    rows: list[list[object]] = [lines[0].split(",")]
    for line in lines[1:]:
        if not line:
            continue
        identifier, day, region, amount, units = line.split(",")
        rows.append(
            [
                identifier,
                date.fromisoformat(day) if day else None,
                region or None,
                Decimal(amount) if amount.strip() else (amount or None),
                int(units) if units else None,
            ]
        )
    return make_xlsx([Sheet("Ventas", rows)])


def xlsx_headers(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Content-Type": XLSX_MIME, "Idempotency-Key": str(uuid4())}


def test_xlsx_import_inspects_imports_and_matches_the_csv_figures(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    book = example_workbook()
    assert book == example_workbook()  # generador determinista
    base = f"/api/v1/projects/{project_id}/imports/xlsx"
    inspection = client.post(
        base + "/inspect",
        params={"file_name": "ventas.xlsx"},
        content=book,
        headers=xlsx_headers(headers),
    )
    assert inspection.status_code == 200, inspection.text
    body = inspection.json()
    assert body["sheets"] == [{"name": "Ventas", "hidden": False, "tables": []}]
    assert body["columns"] == ["id", "fecha", "region", "importe", "unidades"]
    assert body["problem"] is None and body["rows"][0][:2] == ["001", "2026-01-01"]
    missing = client.post(
        base + "/inspect",
        params={"file_name": "ventas.xlsx", "header_row": 3},
        content=book,
        headers=xlsx_headers(headers),
    ).json()
    assert missing["problem"]["code"] in {"XLSX_HEADERS", "XLSX_DUPLICATE_HEADERS"}

    rejected = client.post(
        base,
        params={"file_name": "ventas.xls", "sheet": "Ventas"},
        content=book,
        headers=xlsx_headers(headers),
    )
    assert rejected.status_code == 422 and rejected.json()["code"] == "UNSUPPORTED_FORMAT"
    wrong_type = client.post(
        base,
        params={"file_name": "ventas.xlsx", "sheet": "Ventas"},
        content=book,
        headers={**xlsx_headers(headers), "Content-Type": "text/csv"},
    )
    assert wrong_type.status_code == 415

    created = client.post(
        base,
        params={"file_name": "ventas.xlsx", "sheet": "Ventas"},
        content=book,
        headers=xlsx_headers(headers),
    )
    assert created.status_code == 202, created.text
    assert process(db, objects)
    xlsx_version = created.json()["id"]
    assert client.get(f"/api/v1/versions/{xlsx_version}").json()["state"] == "succeeded"
    assert client.get(f"/api/v1/versions/{xlsx_version}/original").content == book
    overview = client.get(f"/api/v1/versions/{xlsx_version}/diagnostic").json()["profile"][
        "overview"
    ]
    assert overview["algorithm"] == "automatic-overview-v2"
    assert overview["kpis"][0]["value"] == "6"
    assert overview["table_detail"]["rows"][0][0] == "001"

    csv_content = (EXAMPLE / "ventas_calidad.csv").read_bytes()
    csv_version = upload(client, headers, project_id, content=csv_content).json()["id"]
    assert process(db, objects)

    def table(version: str) -> list[dict[str, str | None]]:
        page = client.get(f"/api/v1/versions/{version}/preview", params={"limit": 100}).json()
        return [row["values"] for row in page["rows"]]

    def figures(rows: list[dict[str, str | None]]) -> list[dict[str, object]]:
        return [
            {
                key: Decimal(value)
                if key in {"importe", "unidades"} and value and value.strip()
                else value
                for key, value in row.items()
            }
            for row in rows
        ]

    assert figures(table(xlsx_version)) == figures(table(csv_version))
    xlsx_quality = client.get(f"/api/v1/versions/{xlsx_version}/diagnostic").json()["quality"]
    csv_quality = client.get(f"/api/v1/versions/{csv_version}/diagnostic").json()["quality"]
    for key in ("missing_cells", "duplicate_rows", "completeness_percent"):
        assert xlsx_quality[key] == csv_quality[key]
    plan = client.get(f"/api/v1/projects/{project_id}/versions").json()["items"]
    assert {item["file_name"] for item in plan} == {"ventas.xlsx", "ventas.csv"}


def test_failed_workbook_never_publishes_a_table(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    book = make_xlsx([Sheet("H", [["a", "b"], [1, 2]], merges=["A2:B2"])])
    created = client.post(
        f"/api/v1/projects/{project_id}/imports/xlsx",
        params={"file_name": "malo.xlsx", "sheet": "H"},
        content=book,
        headers=xlsx_headers(headers),
    )
    assert created.status_code == 202
    assert process(db, objects)
    version = client.get(f"/api/v1/versions/{created.json()['id']}").json()
    assert version["state"] == "failed" and version["error_code"] == "XLSX_MERGED_CELLS"
