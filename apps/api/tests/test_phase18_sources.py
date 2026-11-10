"""Fase 18, etapa A: CSV y Excel regionales, varias tablas de un libro y cambios de estructura.

- `regional-values-v1` sólo reescribe columnas cuyos valores admiten una única lectura; ante la
  duda la columna queda como texto con su motivo.
- Un CSV que no es UTF-8 se lee como Windows-1252 y la codificación queda fijada en el plan.
- `xlsx-selection-v2`: las demás tablas con datos del libro se analizan como versiones propias.
- Los cambios de columnas respecto de la versión anterior del mismo archivo sólo se informan.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project, upload
from test_phase16_investigation import reference_analysis
from test_phase17_delivery import investigation, source
from test_xlsx_ingestion import xlsx_headers
from xlsx_support import Sheet, make_xlsx

from dataflow.bootstrap.services import make_datasets
from dataflow.integrations.sources.xlsx_reader import Workbook
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.public import build_report, render_pdf
from dataflow.modules.ingestion.contracts import (
    ColumnChange,
    ConvertedColumn,
    SourceReading,
    SourceReview,
    StructureComparison,
)
from dataflow.platform.regional import read_values

# --- regional-values-v1 (puro) ----------------------------------------------------------------


def column(rows: list[list[str | None]], index: int) -> list[str | None]:
    return [row[index] for row in rows]


def test_regional_numbers_are_rewritten_only_when_unambiguous() -> None:
    rows: list[list[str | None]] = [
        ["1.234,56", "1,234.5", "12", "007", "1,5", None],
        ["0,5", "2,000.25", "15", "008", "2", "3"],
        ["-12,25", "3.5", "3", "009", "1.000,5", "4"],
    ]
    result = read_values(rows, file_convention=False)
    assert column(result.rows, 0) == ["1234.56", "0.5", "-12.25"]
    assert column(result.rows, 1) == ["1234.5", "2000.25", "3.5"]
    # Enteros y códigos con ceros a la izquierda no cambian.
    assert column(result.rows, 2) == ["12", "15", "3"]
    assert column(result.rows, 3) == ["007", "008", "009"]
    assert column(result.rows, 4) == ["1.5", "2", "1000.5"]
    assert column(result.rows, 5) == [None, "3", "4"]
    formats = {item.column: item.format for item in result.converted}
    assert formats == {0: "decimal_comma", 1: "decimal_point_grouped", 4: "decimal_comma"}
    assert result.kept == [] and result.convention is None


def test_ambiguous_numbers_follow_the_file_convention_or_stay_as_text() -> None:
    rows: list[list[str | None]] = [["1.234", "1,234", "10,5"], ["2.500", "2,500", "3"]]
    # Sin convención de archivo (Excel): «1.234» sigue siendo la cifra canónica 1.234 y
    # «1,234» (mil o uno coma dos) se deja como texto.
    alone = read_values([row[:2] for row in rows], file_convention=False)
    assert alone.rows == [["1.234", "1,234"], ["2.500", "2,500"]]
    assert [(k.column, k.kind) for k in alone.kept] == [(1, "number")]
    # CSV con otra columna que sólo admite coma decimal: el archivo usa coma decimal.
    regional = read_values(rows, file_convention=True)
    assert regional.convention == "decimal_comma"
    assert regional.rows == [["1234", "1.234", "10.5"], ["2500", "2.500", "3"]]
    assert all(item.by_file_convention for item in regional.converted if item.column < 2)
    # Convenciones opuestas en el mismo archivo: no hay convención y no se adivina.
    mixed = read_values([["1,5", "1,234.5", "1,234"], ["2", "3", "2,500"]], file_convention=True)
    assert mixed.convention is None
    assert [k.column for k in mixed.kept] == [2]


def test_regional_dates_need_a_value_that_proves_the_order() -> None:
    rows: list[list[str | None]] = [
        ["31/12/2024", "12/31/2024", "01/02/2024", "2024/12/31", "2024-12-31", "32/01/2024"],
        ["01-01-2024", "01/15/2024", "03/04/2024", "2025.1.5", "2025-01-05", "01/01/2024"],
    ]
    result = read_values(rows, file_convention=True)
    assert column(result.rows, 0) == ["2024-12-31", "2024-01-01"]
    assert column(result.rows, 1) == ["2024-12-31", "2024-01-15"]
    assert column(result.rows, 3) == ["2024-12-31", "2025-01-05"]
    # Día y mes intercambiables: se deja como texto con su motivo.
    assert column(result.rows, 2) == ["01/02/2024", "03/04/2024"]
    assert [(k.column, k.kind) for k in result.kept] == [(2, "date")]
    # ISO no cambia y una fecha imposible deja la columna como estaba.
    assert column(result.rows, 4) == ["2024-12-31", "2025-01-05"]
    assert column(result.rows, 5) == ["32/01/2024", "01/01/2024"]
    orders = {item.column: item.format for item in result.converted}
    assert orders == {0: "day_month_year", 1: "month_day_year", 3: "year_month_day"}


# --- CSV regional de extremo a extremo ----------------------------------------------------------

REGIONAL = (
    "Región;Fecha;Importe;Unidades\r\n"
    "Bogotá;31/01/2024;1.234,50;3\r\n"
    "Medellín;29/02/2024;980,25;2\r\n"
    "Bogotá;31/03/2024;2.000,00;5\r\n"
).encode("cp1252")


def test_windows_csv_with_regional_values_is_read_and_explained(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    created = upload(client, headers, pid, REGIONAL, name="ventas_regional.csv")
    assert created.status_code == 202, created.text
    run = client.get(f"/api/v1/executions/{created.json()['execution_id']}").json()
    read = run["plan"]["content"]["steps"][0]
    assert (read["operation"], read["version"]) == ("ingestion.read_csv", 2)
    assert read["parameters"]["encoding"] == "cp1252"
    assert read["parameters"]["separator"] == ";"
    assert read["parameters"]["values"] == "regional-values-v1"
    assert run["plan"]["content"]["config"]["operation_catalog"] == "analysis-v13"
    assert process(db, objects)
    version_id = created.json()["id"]
    assert client.get(f"/api/v1/versions/{version_id}").json()["state"] == "succeeded"
    rows = client.get(f"/api/v1/versions/{version_id}/preview").json()["rows"]
    assert rows[0]["values"] == {
        "Región": "Bogotá",
        "Fecha": "2024-01-31",
        "Importe": "1234.50",
        "Unidades": "3",
    }
    review = client.get(f"/api/v1/versions/{version_id}/reading").json()
    reading = review["reading"]
    assert reading["encoding"] == "cp1252" and reading["separator"] == ";"
    assert reading["convention"] == "decimal_comma"
    converted = {item["column"]: item["format"] for item in reading["converted"]}
    assert converted == {"Fecha": "day_month_year", "Importe": "decimal_comma"}
    assert review["structure"] is None
    # El original no cambia: se descarga byte a byte.
    assert client.get(f"/api/v1/versions/{version_id}/original").content == REGIONAL
    # La interpretación ve una medida y un eje de fechas.
    profile = client.get(f"/api/v1/versions/{version_id}/diagnostic").json()["profile"]
    roles = {c["name"]: c["role"] for c in profile["overview"]["analysis"]["columns"]}
    assert roles["Importe"] == "measure" and roles["Fecha"] == "time"


def test_utf8_csv_without_regional_values_keeps_its_cells(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    created = upload(client, headers, pid, b"id,importe\n1,10.5\n2,3\n").json()
    assert process(db, objects)
    rows = client.get(f"/api/v1/versions/{created['id']}/preview").json()["rows"]
    assert [r["values"] for r in rows] == [
        {"id": "1", "importe": "10.5"},
        {"id": "2", "importe": "3"},
    ]
    reading = client.get(f"/api/v1/versions/{created['id']}/reading").json()["reading"]
    assert reading["encoding"] == "utf-8-sig"
    assert reading["converted"] == [] and reading["kept_as_text"] == []


# --- Cambios de estructura ----------------------------------------------------------------------


def test_structure_changes_are_reported_against_the_previous_version_of_the_same_file(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    first = upload(client, headers, pid, b"id,region,importe\n1,Norte,10\n2,Sur,20\n").json()
    other = upload(client, headers, pid, b"x,y\n1,2\n3,4\n", name="otro.csv").json()
    second = upload(
        client,
        headers,
        pid,
        b"id,zona,importe\n1,Norte,diez\n2,Sur,veinte\n",
    ).json()
    for _ in range(3):
        assert process(db, objects)
    assert client.get(f"/api/v1/versions/{first['id']}/reading").json()["structure"] is None
    assert client.get(f"/api/v1/versions/{other['id']}/reading").json()["structure"] is None
    structure = client.get(f"/api/v1/versions/{second['id']}/reading").json()["structure"]
    assert structure["previous_version_id"] == first["id"]
    assert structure["previous_version_number"] == first["number"]
    changes = {(c["column"], c["change"]) for c in structure["changes"]}
    assert changes == {
        ("zona", "added"),
        ("region", "removed"),
        ("importe", "type_changed"),
    }
    importe = next(c for c in structure["changes"] if c["column"] == "importe")
    assert (importe["before"], importe["after"]) == ("entero", "texto")
    assert importe["description"] == "«importe» cambió el tipo: de entero a texto."
    assert structure["unchanged"] == 1


def test_reading_waits_for_the_result_and_belongs_to_its_owner(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    created = upload(client, headers, pid).json()
    pending = client.get(f"/api/v1/versions/{created['id']}/reading")
    assert pending.status_code == 409 and pending.json()["code"] == "RESULT_NOT_READY"
    assert process(db, objects)
    account(client)
    assert client.get(f"/api/v1/versions/{created['id']}/reading").status_code == 404


# --- Varias tablas de un libro ------------------------------------------------------------------


def book() -> bytes:
    return make_xlsx(
        [
            Sheet("Portada", [["Ventas y gastos 2024"]]),
            Sheet(
                "Ventas",
                [["mes", "region", "importe"], *[[f"2024-0{m}", "N", m] for m in range(1, 7)]],
            ),
            Sheet("Gastos", [["concepto", "importe"], ["Luz", "1.234,5"], ["Agua", "80,25"]]),
            Sheet("Notas", [["texto"], ["revisar"], ["cerrar"]]),
        ]
    )


def test_selection_v2_keeps_the_main_table_and_adds_the_other_data_tables() -> None:
    chosen = Workbook(book()).automatic_tables(100_000)
    assert (chosen.sheet, chosen.table, chosen.header_row) == ("Ventas", None, 1)
    assert chosen.additional == [("Gastos", None, 1)]
    assert chosen.omitted == [("Portada", None), ("Notas", None)]
    # v1 no cambia.
    assert Workbook(book()).automatic(100_000).omitted == [
        ("Portada", None),
        ("Gastos", None),
        ("Notas", None),
    ]


def test_selection_v2_limits_the_number_of_tables() -> None:
    sheets = [Sheet(f"H{i}", [["a", "b"], *[[str(j), j] for j in range(i + 2)]]) for i in range(7)]
    chosen = Workbook(make_xlsx(sheets)).automatic_tables(100_000)
    assert chosen.sheet == "H6"
    assert [a[0] for a in chosen.additional] == ["H5", "H4", "H3", "H2"]
    assert chosen.omitted == [("H0", None), ("H1", None)]


def test_each_data_table_of_a_workbook_becomes_its_own_version(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = book()
    created = client.post(
        f"/api/v1/projects/{pid}/imports/xlsx",
        params={"file_name": "libro.xlsx"},
        content=content,
        headers=xlsx_headers(headers),
    )
    assert created.status_code == 202, created.text
    main = created.json()
    assert main["source_selection"] == {
        "rule": "xlsx-selection-v2",
        "sheet": "Ventas",
        "table": None,
        "header_row": 1,
        "omitted": [{"sheet": "Portada", "table": None}, {"sheet": "Notas", "table": None}],
        "analyzed_together": [{"sheet": "Gastos", "table": None}],
    }
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    assert len(versions) == 2
    sibling = next(v for v in versions if v["id"] != main["id"])
    # La principal queda como la versión más reciente (la que abre la interfaz).
    assert main["number"] == sibling["number"] + 1 and sibling["file_name"] == "libro.xlsx"
    assert sibling["source_selection"]["sheet"] == "Gastos"
    assert sibling["source_selection"]["analyzed_together"] == [{"sheet": "Ventas", "table": None}]
    # Un solo original para las dos versiones; la cuota lo cuenta una vez.
    assert sibling["sha256"] == main["sha256"]
    owner = UUID(client.get("/api/v1/auth/me").json()["user"]["id"])
    assert make_datasets(db).used_bytes(owner) == len(content)
    assert process(db, objects) and process(db, objects)
    for item in (main, sibling):
        assert client.get(f"/api/v1/versions/{item['id']}").json()["state"] == "succeeded"
    rows = client.get(f"/api/v1/versions/{sibling['id']}/preview").json()["rows"]
    assert rows[0]["values"] == {"concepto": "Luz", "importe": "1234.5"}
    reading = client.get(f"/api/v1/versions/{sibling['id']}/reading").json()["reading"]
    assert reading["format"] == "xlsx" and reading["encoding"] is None
    assert [c["column"] for c in reading["converted"]] == ["importe"]


# --- Informe --------------------------------------------------------------------------------------


def test_report_includes_reading_and_structure_sections() -> None:
    analysis = reference_analysis()
    result = investigation(analysis)
    review = SourceReview(
        reading=SourceReading(
            format="csv",
            encoding="cp1252",
            separator=";",
            convention="decimal_comma",
            converted=[
                ConvertedColumn(
                    column="Importe",
                    kind="number",
                    format="decimal_comma",
                    values=3,
                    by_file_convention=False,
                    explanation="Leída como coma decimal y punto de miles; 3 valores.",
                )
            ],
        ),
        structure=StructureComparison(
            previous_version_id=str(uuid4()),
            previous_version_number=1,
            changes=[ColumnChange(column="zona", change="added", description="Columna nueva.")],
            unchanged=4,
        ),
    )
    generated = datetime(2026, 11, 9, tzinfo=UTC)
    document = build_report(source(analysis, result), analysis, result, None, generated, review)
    ids = [section.id for section in document.sections]
    assert ids.index("investigation") < ids.index("reading") < ids.index("structure")
    reading = next(s for s in document.sections if s.id == "reading")
    assert "Windows-1252 (ANSI)" in reading.blocks[0].paragraphs[0]
    structure = next(s for s in document.sections if s.id == "structure")
    assert structure.title == "Cambios respecto de la versión 1"
    assert render_pdf(document).startswith(b"%PDF")
    # Sin revisión, el informe es el de la Fase 17.
    plain = build_report(source(analysis, result), analysis, result, None, generated)
    assert "reading" not in [s.id for s in plain.sections]


@pytest.mark.parametrize("content", [b"\xef\xbb\xbfid;v\n1;2,5\n", b"id;v\n1;2,5\n"])
def test_utf8_with_or_without_bom_resolves_to_utf8(content: bytes) -> None:
    from dataflow.modules.ingestion.plans import resolve_encoding

    assert resolve_encoding(content) == "utf-8-sig"
    assert resolve_encoding("Región;v\n".encode("cp1252")) == "cp1252"


def test_report_job_pins_the_reading_and_the_structure_changes(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    from reference_sales import reference_csv

    from dataflow.bootstrap.services import make_runner

    headers = account(client)
    pid = project(client, headers)
    upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv")
    runner = make_runner(db, objects)
    while runner.run_once():
        pass
    changed = reference_csv().replace(b"Region", b"Zona", 1)
    second = upload(client, headers, pid, changed, name="ventas_mensuales.csv").json()
    while runner.run_once():
        pass
    report = client.get(f"/api/v1/versions/{second['id']}/report").json()
    assert report["state"] == "ready"
    run = client.get(f"/api/v1/executions/{report['execution_id']}").json()
    pinned = run["plan"]["content"]["input"]["review"]
    assert pinned["reading"]["encoding"] == "utf-8-sig"
    changes = {(c["column"], c["change"]) for c in pinned["structure"]["changes"]}
    assert changes == {("Zona", "added"), ("Region", "removed")}
    pdf = client.get(f"/api/v1/versions/{second['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
