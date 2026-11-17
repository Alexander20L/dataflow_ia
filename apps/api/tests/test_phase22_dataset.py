"""Fase 22: pestaña Dataset. Inspección calculada una vez sobre la tabla completa, registros
paginados en el servidor, diccionario con correcciones manuales que se heredan y nunca cambian
el archivo, y diagnóstico de calidad verificable con cifras conocidas."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_xlsx_ingestion import xlsx_headers
from xlsx_support import Formula, Sheet, make_xlsx

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.inspection.domain import (
    date_readings,
    frequency_of,
    is_ambiguous_date,
    nature_of,
    percent,
    technical_type,
)
from dataflow.modules.inspection.infrastructure import ColumnAnnotationRecord


def work(db: Session, objects: LocalObjects) -> None:
    """Carga e inspección (sin el resto de trabajos de fondo, que aquí no se prueban)."""
    runner = make_runner(
        db,
        objects,
        IsolatedAnalyzer(objects.root, 60, 100_000, 128),
        kinds={"csv_import", "inspection"},
    )
    while runner.run_once():
        pass


def inspection(client: TestClient, version: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/versions/{version}/inspection")
    assert response.status_code == 200, response.text
    return response.json()


def ready(client: TestClient, db: Session, objects: LocalObjects, version: str) -> dict[str, Any]:
    work(db, objects)
    view = inspection(client, version)
    assert view["state"] == "ready", view
    return view


def columns(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in view["inspection"]["columns"]}


def kinds(view: dict[str, Any]) -> dict[tuple[str, tuple[str, ...]], dict[str, Any]]:
    return {(f["kind"], tuple(f["columns"])): f for f in view["inspection"]["findings"]}


def all_rows(client: TestClient, version: str, **params: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.get(
            f"/api/v1/versions/{version}/preview",
            params={"limit": 100, "offset": offset, **params},
        ).json()
        rows += page["rows"]
        offset += 100
        if offset >= page["total"]:
            return rows


# --- Reglas puras -------------------------------------------------------------------------------


def test_percent_dates_frequency_and_nature_rules() -> None:
    assert percent(29, 30) == "96.67" and percent(0, 0) == "0.00" and percent(1, 8) == "12.50"
    assert date_readings("03/04/2026") == {"day_month_year", "month_day_year"}
    assert is_ambiguous_date("03/04/2026") and not is_ambiguous_date("05/05/2026")
    assert date_readings("25/04/2026") == {"day_month_year"}
    assert date_readings("31/02/2026") == set() and date_readings("2026-02-30") == set()
    assert date_readings("2026-02-28") == {"year_month_day"}
    days = [date(2024, m, 1) for m in (1, 2, 3, 5)]
    assert frequency_of(days) == "monthly"
    assert frequency_of([date(2024, 1, d) for d in (1, 2, 3, 4)]) == "daily"
    assert frequency_of(days[:2]) is None
    # Tipo técnico ≠ naturaleza: un año entero es temporal; un código numérico, nominal.
    assert nature_of("integer", "time", "year", 5)[0] == "temporal"
    assert nature_of("integer", "dimension", None, 5)[0] == "nominal"
    assert nature_of("integer", "measure", None, 5)[0] == "discrete"
    assert nature_of("decimal", "measure", None, 5)[0] == "continuous"
    assert nature_of("integer", "identifier", None, 5)[0] == "nominal"
    # Los ceros iniciales no son números; un solo texto deja la columna como texto.
    assert technical_type(["00125", "00126"]) == "string"
    assert technical_type(["1", "2", "abc"]) == "string"
    assert technical_type(["1", "2.5"]) == "decimal"
    assert technical_type(["2024-01-01 10:00:00"]) == "datetime"
    assert technical_type([]) == "empty"


# --- Cifras conocidas -----------------------------------------------------------------------------

KNOWN = (
    b"codigo,region,unidades,precio,fecha\n"
    b"00125,Norte,3,10.5,2024-01-01\n"
    b"00126,Sur,1,20,2024-02-01\n"
    b"00127,Norte,2,,2024-03-01\n"
    b"00128,Este,5,7.25,2024-05-01\n"
    b"00129,Sur,4,12,2024-06-01\n"
    b"00125,Norte,3,10.5,2024-01-01\n"
)


def test_summary_and_columns_match_known_values_and_the_records(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, KNOWN, name="conocido.csv").json()["id"]
    assert inspection(client, version)["state"] == "queued"
    view = ready(client, db, objects, version)
    summary = view["inspection"]["summary"]
    # 6 registros × 5 columnas = 30 celdas; un nulo → 29 / 30 = 96,67 %.
    assert (summary["rows"], summary["columns"], summary["cells"]) == (6, 5, 30)
    assert summary["missing_cells"] == 1 and summary["completeness_percent"] == "96.67"
    assert summary["duplicate_rows"] == 1 and summary["memory_bytes"] > 0
    found = columns(view)
    codigo, unidades, precio, fecha = (
        found["codigo"],
        found["unidades"],
        found["precio"],
        found["fecha"],
    )
    assert codigo["technical_type"] == "string" and codigo["leading_zeros"] == 6
    assert codigo["examples"][0] == "00125"
    assert (precio["nulls"], precio["null_percent"], precio["count"]) == (1, "16.67", 5)
    assert precio["technical_type"] == "decimal"
    assert precio["numeric"]["minimum"] == "7.25" and precio["numeric"]["maximum"] == "20"
    assert precio["numeric"]["median"] == "10.5" and precio["numeric"]["mean"] == "12.05"
    assert precio["numeric"]["q1"] == "10.5" and precio["numeric"]["q3"] == "12"
    assert sum(b["count"] for b in precio["numeric"]["histogram"]) == 5
    assert unidades["technical_type"] == "integer"
    assert fecha["technical_type"] == "date" and fecha["nature"] == "temporal"
    assert fecha["temporal"]["frequency"] == "monthly"
    assert fecha["temporal"]["missing_periods"] == 1
    assert fecha["temporal"]["missing_sample"] == ["2024-04"]
    region = found["region"]
    assert region["categorical"]["top"][0] == {"value": "Norte", "count": 3, "percent": "50.00"}
    assert region["distinct"] == 3 and region["distinct_percent"] == "50.00"
    # Cada cifra coincide con los registros que devuelve la paginación (caso 16).
    rows = all_rows(client, version)
    assert len(rows) == summary["rows"]
    for name, column in found.items():
        values = [r["values"][name] for r in rows]
        assert column["nulls"] == sum(v is None for v in values)
        assert column["distinct"] == len({v for v in values if v is not None})
    findings = kinds(view)
    duplicate = findings[("duplicate_rows", ())]
    assert duplicate["affected_rows"] == 1 and duplicate["sample_rows"] == [6]
    assert findings[("missing_values", ("precio",))]["sample_rows"] == [3]
    assert findings[("leading_zeros", ("codigo",))]["severity"] == "info"
    file = view["inspection"]["file"]
    assert file["format"] == "csv" and file["encoding"] == "utf-8-sig"
    assert file["separator"] == "," and file["blank_lines"] == 0
    assert file["size_bytes"] == len(KNOWN) and file["file_name"] == "conocido.csv"
    # El original no cambia.
    assert client.get(f"/api/v1/versions/{version}/original").content == KNOWN


WINDOWS = (
    "Región;Importe;Código\r\nBogotá;1.234,50;A1\r\n\r\nMedellín;980,25;A2\r\nCali;2.000,00;A3\r\n"
).encode("cp1252")


def test_windows_1252_semicolon_and_decimal_comma(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, WINDOWS, name="regional.csv").json()["id"]
    view = ready(client, db, objects, version)
    file = view["inspection"]["file"]
    assert file["encoding"] == "cp1252" and file["separator"] == ";"
    assert file["decimal_convention"] == "coma decimal (1.234,5)"
    assert file["blank_lines"] == 1
    assert [c["column"] for c in file["converted"]] == ["Importe"]
    importe = columns(view)["Importe"]
    assert importe["technical_type"] == "decimal"
    assert importe["numeric"]["maximum"] == "2000" and importe["numeric"]["minimum"] == "980.25"
    assert "Leída como" in importe["reading"]
    assert "Región" in columns(view) and columns(view)["Región"]["examples"][0] == "Bogotá"


MESSY = (
    b"id,valor,estado,fecha,nota\n"
    b"1,10,N/A,03/04/2026,\n"
    b"2,20,-,05/06/2026,ok\n"
    b"3,abc,activo,31/02/2026,  \n"
    b"4,40,NULL,07/08/2026,ok\n"
    b"5,50,activo,09/10/2026,ok\n"
)


def test_missing_kinds_mixed_types_and_ambiguous_or_invalid_dates(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, MESSY, name="sucio.csv").json()["id"]
    view = ready(client, db, objects, version)
    found = columns(view)
    estado, valor, fecha, nota = found["estado"], found["valor"], found["fecha"], found["nota"]
    # «N/A», «-» y «NULL» se cuentan aparte y siguen siendo valores: nada se vuelve nulo.
    assert estado["nulls"] == 0
    assert {t["token"]: t["count"] for t in estado["missing"]["tokens"]} == {
        "-": 1,
        "n/a": 1,
        "null": 1,
    }
    assert nota["nulls"] == 1 and nota["missing"]["whitespace"] == 1
    assert valor["technical_type"] == "string"
    assert valor["mixed"] == {"numeric": 4, "text": 1, "examples": ["abc"]}
    assert fecha["technical_type"] == "string"
    findings = kinds(view)
    assert findings[("mixed_types", ("valor",))]["dimension"] == "format"
    ambiguous = findings[("ambiguous_dates", ("fecha",))]
    assert ambiguous["affected_rows"] == 4 and "03/04/2026" in ambiguous["examples"]
    invalid = findings[("invalid_dates", ("fecha",))]
    assert invalid["examples"] == ["31/02/2026"] and invalid["sample_rows"] == [3]
    assert findings[("missing_tokens", ("estado",))]["affected_rows"] == 3
    assert findings[("blank_text", ("nota",))]["affected_rows"] == 1
    # Los registros conservan los valores originales.
    rows = all_rows(client, version)
    assert [r["values"]["estado"] for r in rows] == ["N/A", "-", "activo", "NULL", "activo"]
    assert rows[0]["values"]["fecha"] == "03/04/2026"


PERIODS = b"Year,Month,Revenue\n" + b"".join(
    f"{2023 + (m - 1) // 12},{(m - 1) % 12 + 1},{100 + m}\n".encode() for m in range(1, 16)
)


def test_year_and_month_are_a_possible_period_never_a_new_date(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, PERIODS, name="periodos.csv").json()["id"]
    view = ready(client, db, objects, version)
    year = columns(view)["Year"]
    assert year["technical_type"] == "integer" and year["nature"] == "temporal"
    assert year["numeric"] is None and year["temporal"]["minimum"] == "2023"
    assert columns(view)["Revenue"]["nature"] == "discrete"
    period = view["inspection"]["periods"][0]
    assert period["columns"] == ["Year", "Month"] and period["periods"] == 15
    assert [c["name"] for c in view["inspection"]["columns"]] == ["Year", "Month", "Revenue"]


def test_large_dataset_is_inspected_completely(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    lines = [b"id,grupo,importe"] + [
        f"{i},{'ABCD'[i % 4]},{i % 1000}.{i % 7}".encode() for i in range(100_000)
    ]
    content = b"\n".join(lines) + b"\n"
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, content, name="grande.csv").json()["id"]
    view = ready(client, db, objects, version)
    summary = view["inspection"]["summary"]
    assert summary["rows"] == 100_000 and summary["cells"] == 300_000
    grupo = columns(view)["grupo"]
    assert [t["count"] for t in grupo["categorical"]["top"]] == [25_000] * 4
    importe = columns(view)["importe"]
    expected = sum(Decimal(f"{i % 1000}.{i % 7}") for i in range(100_000)) / 100_000
    assert abs(Decimal(importe["numeric"]["mean"]) - expected) < Decimal("0.000001")
    page = client.get(
        f"/api/v1/versions/{version}/preview", params={"limit": 50, "offset": 99_990}
    ).json()
    assert page["total"] == 100_000 and len(page["rows"]) == 10
    assert page["rows"][-1]["row_number"] == 100_000


def test_empty_or_invalid_files_never_have_an_inspection(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    assert upload(client, headers, pid, b"").status_code == 422
    version = upload(client, headers, pid, b"a,b\n", name="vacio.csv").json()["id"]
    work(db, objects)
    assert client.get(f"/api/v1/versions/{version}").json()["state"] == "failed"
    view = inspection(client, version)
    assert view["state"] == "unavailable" and view["inspection"] is None


# --- Registros ------------------------------------------------------------------------------------


def test_records_are_paginated_sorted_and_searched_on_the_server(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    content = b"nombre,cantidad\n" + b"".join(
        f"Item {i},{n}\n".encode() for i, n in enumerate([9, 10, 1, 100, 2, None, 30])
    ).replace(b"None", b"")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, content, name="items.csv").json()["id"]
    view = ready(client, db, objects, version)
    ids = {c["name"]: c["id"] for c in view["inspection"]["columns"]}
    path = f"/api/v1/versions/{version}/preview"
    page = client.get(path, params={"limit": 3, "offset": 3}).json()
    assert page["column_ids"] == [ids["nombre"], ids["cantidad"]]
    assert [r["row_number"] for r in page["rows"]] == [4, 5, 6] and page["total"] == 7
    # Orden numérico (10 después de 9), nulos al final y número de fila original.
    ordered = client.get(path, params={"sort": ids["cantidad"], "limit": 10}).json()
    assert [r["values"]["cantidad"] for r in ordered["rows"]] == [
        "1",
        "2",
        "9",
        "10",
        "30",
        "100",
        None,
    ]
    assert ordered["rows"][0]["row_number"] == 3 and ordered["sort"] == ids["cantidad"]
    descending = client.get(
        path, params={"sort": ids["cantidad"], "descending": True, "limit": 2}
    ).json()
    assert [r["values"]["cantidad"] for r in descending["rows"]] == ["100", "30"]
    found = client.get(path, params={"search": "ITEM 1", "limit": 10}).json()
    assert found["total"] == 1 and found["rows"][0]["values"]["nombre"] == "Item 1"
    # Un nombre de columna o una expresión nunca sirven para ordenar; los límites se validan.
    assert client.get(path, params={"sort": "cantidad"}).status_code == 422
    assert client.get(path, params={"sort": str(uuid4())}).status_code == 422
    assert client.get(path, params={"limit": 101}).status_code == 422
    assert client.get(path, params={"offset": -1}).status_code == 422
    assert client.get(path, params={"search": "^.*$"}).json()["total"] == 0


# --- Excel ----------------------------------------------------------------------------------------


def test_workbook_sheets_range_formulas_and_empty_rows(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    content = make_xlsx(
        [
            Sheet("Portada", [["Informe 2024"]]),
            Sheet(
                "Ventas",
                [
                    ["fecha", "region", "importe", "total"],
                    [date(2024, 1, 1), "Norte", 10, Formula("C2*2", 20)],
                    [None, None, None, None],
                    [date(2024, 2, 1), "Sur", 15, Formula("C4*2", 30)],
                    [date(2024, 3, 1), "Sur", 5, Formula("C5*2", 10)],
                ],
                first_row=2,
            ),
            Sheet("Gastos", [["concepto", "importe"], ["Luz", 12], ["Agua", 8]]),
        ]
    )
    headers = account(client)
    pid = project(client, headers)
    created = client.post(
        f"/api/v1/projects/{pid}/imports/xlsx",
        params={"file_name": "libro.xlsx"},
        content=content,
        headers=xlsx_headers(headers),
    )
    assert created.status_code == 202, created.text
    version = created.json()["id"]
    view = ready(client, db, objects, version)
    file = view["inspection"]["file"]
    assert file["format"] == "xlsx" and file["sheet"] == "Ventas"
    assert [(s["name"], s["selected"]) for s in file["sheets"]] == [
        ("Portada", False),
        ("Ventas", True),
        ("Gastos", False),
    ]
    assert file["used_range"] == "A2:D6" and file["empty_rows"] == 1
    assert file["formula_cells"] == 3 and file["date_cells"] == 3
    assert file["selection_rule"] == "xlsx-selection-v2"
    assert view["inspection"]["summary"]["rows"] == 3
    # La otra hoja con datos es otra versión con su propia inspección (no se unen hojas).
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    other = next(v["id"] for v in versions if v["id"] != version)
    sibling = ready(client, db, objects, other)
    assert sibling["inspection"]["file"]["sheet"] == "Gastos"
    assert [c["name"] for c in sibling["inspection"]["columns"]] == ["concepto", "importe"]


# --- Diccionario ----------------------------------------------------------------------------------


def test_manual_corrections_persist_are_inherited_and_never_change_the_data(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, KNOWN, name="conocido.csv").json()["id"]
    view = ready(client, db, objects, version)
    first_computed = view["inspection"]["scope"]["computed_at"]
    ids = {c["name"]: c["id"] for c in view["inspection"]["columns"]}
    path = f"/api/v1/versions/{version}/dictionary"
    entry = {e["name"]: e for e in view["dictionary"]}
    assert entry["unidades"]["status"] == "automatic"
    assert entry["unidades"]["origin"].startswith("Clasificación automática")
    # Combinaciones sin sentido: una medida de texto o una columna inexistente.
    bad = client.post(path, json={"column_id": ids["region"], "role": "measure"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["code"] == "ANNOTATION_INVALID"
    missing = client.post(path, json={"column_id": str(uuid4()), "role": "text"}, headers=headers)
    assert missing.status_code == 404
    corrected = client.post(
        path,
        json={
            "column_id": ids["unidades"],
            "role": "dimension",
            "nature": "ordinal",
            "notes": "Talla del 1 al 5",
        },
        headers=headers,
    )
    assert corrected.status_code == 200, corrected.text
    after = {e["name"]: e for e in corrected.json()["dictionary"]}
    unidades = after["unidades"]
    assert (unidades["status"], unidades["role"], unidades["nature"]) == (
        "corrected",
        "dimension",
        "ordinal",
    )
    assert (unidades["automatic_role"], unidades["notes"]) == ("measure", "Talla del 1 al 5")
    assert corrected.json()["groups"]["categorical"] == view["groups"]["categorical"] + 1
    confirmed = client.post(
        path, json={"column_id": ids["region"], "confirmed": True}, headers=headers
    ).json()
    assert {e["name"]: e for e in confirmed["dictionary"]}["region"]["status"] == "confirmed"
    # El cálculo y los datos no cambian: misma inspección, mismas filas, mismo original.
    again = inspection(client, version)
    assert again["inspection"] == view["inspection"]
    assert again["inspection"]["scope"]["computed_at"] == first_computed
    assert client.get(f"/api/v1/versions/{version}/original").content == KNOWN
    # La versión siguiente del mismo archivo hereda la corrección; recalcular no la pisa.
    second = upload(client, headers, pid, KNOWN, name="conocido.csv").json()["id"]
    inherited = {e["name"]: e for e in ready(client, db, objects, second)["dictionary"]}
    assert inherited["unidades"]["status"] == "corrected" and inherited["unidades"]["inherited"]
    assert "versión anterior" in inherited["unidades"]["origin"]
    # Otro archivo no la hereda.
    other = upload(client, headers, pid, KNOWN, name="otro.csv").json()["id"]
    assert {e["name"]: e for e in ready(client, db, objects, other)["dictionary"]}["unidades"][
        "status"
    ] == "automatic"
    # Volver a la clasificación automática: corrección vacía.
    restored = client.post(path, json={"column_id": ids["unidades"]}, headers=headers).json()
    assert {e["name"]: e for e in restored["dictionary"]}["unidades"]["status"] == "automatic"
    # Interpretación temporal sólo en columnas temporales.
    timed = client.post(
        path,
        json={"column_id": ids["fecha"], "time_format": "year_month_day"},
        headers=headers,
    )
    assert timed.status_code == 200
    wrong = client.post(
        path, json={"column_id": ids["region"], "time_format": "year"}, headers=headers
    )
    assert wrong.status_code == 422
    # Sólo de añadir: cada corrección es una fila (la inmutabilidad la prueba la migración).
    assert db.scalar(select(func.count()).select_from(ColumnAnnotationRecord)) >= 4
    # Otra cuenta no ve ni corrige la inspección.
    stranger = account(client)
    assert client.get(f"/api/v1/versions/{version}/inspection").status_code == 404
    assert client.post(path, json={"column_id": ids["region"]}, headers=stranger).status_code == 404


def test_inspection_is_computed_once_per_version(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, KNOWN, name="conocido.csv").json()["id"]
    ready(client, db, objects, version)
    for _ in range(3):
        inspection(client, version)
    runs = db.scalars(
        select(ExecutionRecord).where(
            ExecutionRecord.version_id == version, ExecutionRecord.kind == "inspection"
        )
    ).all()
    assert len(runs) == 1 and runs[0].state == "succeeded"
