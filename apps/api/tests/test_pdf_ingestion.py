"""Fase 12C: tablas de PDF con capa de texto, elegidas por la persona."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pdf_support import make_pdf, scanned_pdf
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project, upload

from dataflow.integrations.sources.pdf_reader import inspect, read_tables
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.errors import ApplicationError

EXAMPLE = Path(__file__).resolve().parents[3] / "examples"
SALES = [["id", "region", "importe"], ["001", "Norte", "100.50"], ["002", "Sur", "80.00"]]
STOCK = [["sku", "stock"], ["A-1", "5"], ["B-2", "7"]]


def csv_rows() -> list[list[str]]:
    lines = (EXAMPLE / "ventas_calidad.csv").read_text(encoding="utf-8").splitlines()
    return [line.split(",") for line in lines if line]


def example_pdf() -> bytes:
    return make_pdf([csv_rows()])


def code(callable_: object, *args: object) -> str:
    with pytest.raises(ApplicationError) as caught:
        callable_(*args)  # type: ignore[operator]
    return caught.value.code


def test_lists_candidates_and_reads_the_chosen_one() -> None:
    content = make_pdf([SALES, STOCK])
    result = inspect(content, 1000, 64)
    assert [(t["id"], t["columns"]) for t in result["tables"]] == [
        ("p1-t1", ["id", "region", "importe"]),
        ("p1-t2", ["sku", "stock"]),
    ]
    assert all(not t["issues"] for t in result["tables"])
    assert read_tables(content, ["p1-t2"], 1000, 64) == (["sku", "stock"], STOCK[1:])


def test_continuation_across_pages_only_when_chosen_together() -> None:
    first = SALES
    second = [SALES[0], ["003", "Este", "120.25"]]
    content = make_pdf([first, second], break_after=True)
    ids = [t["id"] for t in inspect(content, 1000, 64)["tables"]]
    assert ids == ["p1-t1", "p2-t1"]
    headers, rows = read_tables(content, ids, 1000, 64)
    assert headers == SALES[0]
    assert rows == [*SALES[1:], ["003", "Este", "120.25"]]  # cabecera repetida omitida
    assert read_tables(content, ids[:1], 1000, 64)[1] == SALES[1:]
    mismatch = make_pdf([SALES, STOCK], break_after=True)
    tables = [t["id"] for t in inspect(mismatch, 1000, 64)["tables"]]
    assert code(read_tables, mismatch, tables, 1000, 64) == "PDF_UNION_MISMATCH"


def test_scanned_ambiguous_and_invalid_inputs_fail_with_a_code() -> None:
    assert code(inspect, scanned_pdf(), 1000, 64) == "PDF_NO_TEXT_LAYER"
    assert code(inspect, b"no es un pdf", 1000, 64) == "UNSUPPORTED_FORMAT"
    duplicated = make_pdf([[["a", "a"], ["1", "2"]]])
    table = inspect(duplicated, 1000, 64)["tables"][0]
    assert table["issues"] == ["Hay cabeceras repetidas."]
    assert code(read_tables, duplicated, [table["id"]], 1000, 64) == "PDF_TABLE_AMBIGUOUS"
    assert code(read_tables, make_pdf([SALES]), ["p9-t1"], 1000, 64) == "PDF_TABLE_NOT_FOUND"
    assert code(read_tables, make_pdf([SALES]), [], 1000, 64) == "PDF_TABLE_REQUIRED"


def test_pdf_import_reproduces_the_csv_table_exactly(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    content = example_pdf()
    base = f"/api/v1/projects/{project_id}/imports/pdf"
    pdf_headers = {**headers, "Content-Type": "application/pdf"}
    inspection = client.post(
        base + "/inspect", params={"file_name": "ventas.pdf"}, content=content, headers=pdf_headers
    )
    assert inspection.status_code == 200, inspection.text
    tables = inspection.json()["tables"]
    assert len(tables) == 1 and tables[0]["columns"] == csv_rows()[0]
    missing = client.post(
        base,
        params={"file_name": "ventas.pdf"},
        content=content,
        headers={**pdf_headers, "Idempotency-Key": str(uuid4())},
    )
    assert missing.status_code == 422  # sin tabla elegida no se importa nada
    created = client.post(
        base,
        params={"file_name": "ventas.pdf", "tables": [tables[0]["id"]]},
        content=content,
        headers={**pdf_headers, "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 202, created.text
    assert process(db, objects)
    csv_version = upload(
        client, headers, project_id, content=(EXAMPLE / "ventas_calidad.csv").read_bytes()
    ).json()["id"]
    assert process(db, objects)

    def table(version: str) -> list[dict[str, str | None]]:
        page = client.get(f"/api/v1/versions/{version}/preview", params={"limit": 100}).json()
        return [row["values"] for row in page["rows"]]

    pdf_rows = table(created.json()["id"])
    expected = table(csv_version)
    # PDF no distingue un espacio de una celda vacía: " " del CSV es nulo en el PDF.
    assert pdf_rows == [
        {k: (None if v is not None and not v.strip() else v) for k, v in row.items()}
        for row in expected
    ]
    scanned = client.post(
        base + "/inspect",
        params={"file_name": "escaneado.pdf"},
        content=scanned_pdf(),
        headers=pdf_headers,
    )
    assert scanned.status_code == 422 and scanned.json()["code"] == "PDF_NO_TEXT_LAYER"
