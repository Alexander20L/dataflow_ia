"""Fase 9 · exportación CSV: serialización fija, ida y vuelta con la ingesta y trazabilidad."""

import io
from typing import Any
from uuid import UUID, uuid4

import polars as pl
import pytest
from analytics_support import typed_table
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_analytics_runner import confirm_semantics, execute, metrics_for, query_plan
from test_cleaning_runner import Scenario
from test_csv_ingestion import upload

from dataflow.bootstrap.services import make_executions, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion.processor import parse_csv
from dataflow.platform.csv_export import write_csv
from dataflow.platform.tabular import table_logical_sha256


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def test_standard_and_regional_serialization_rules() -> None:
    header = ["texto", "importe"]
    rows: list[list[str | None]] = [
        ["a,b", "10.50"],
        ['dice "hola"', "-3.25"],
        ["línea\nnueva", None],
        ["=SUMA(A1)", "0.00"],
        [None, "7.00"],
    ]
    standard = write_csv(header, rows, "standard", frozenset({1}), frozenset({0}))
    assert standard == (
        b"texto,importe\n"
        b'"a,b",10.50\n'
        b'"dice ""hola""",-3.25\n'
        b'"l\xc3\xadnea\nnueva",\n'
        b"=SUMA(A1),0.00\n"  # el estándar nunca cambia el contenido
        b",7.00\n"
    )
    regional = write_csv(header, rows, "excel_regional", frozenset({1}), frozenset({0}))
    assert regional.startswith(b"\xef\xbb\xbftexto;importe\r\n")
    assert b"a,b;10,50\r\n" in regional  # la coma ya no es separador: sin comillas
    assert b";-3,25\r\n" in regional  # negativo decimal intacto, con coma decimal
    assert b"'=SUMA(A1);0,00\r\n" in regional  # fórmula neutralizada sólo en texto
    # Una fila nula de una sola columna no puede ser una línea en blanco (la ingesta la salta).
    single = write_csv(["id"], [["1"], [None], ["3"]], "standard")
    assert single == b'id\n1\n""\n3\n'
    assert parse_csv(single, ",", 10, 10)[1] == [["1"], [None], ["3"]]


def table_of(s: Scenario, version: str) -> tuple[Any, pl.DataFrame]:
    table = make_executions(s.db).representations(s.owner, UUID(version))[0]
    return table, pl.read_parquet(io.BytesIO(s.objects.read(table.content)))


TRICKY = (
    "id,nombre,nota,importe\n"
    '001,"Pérez, Ana","dice ""sí""", 12.50\n'
    '002,,"multi\nlínea",\n'
    "003,  espacios  ,=1+1,-0\n"
    '004,"","",""\n'
    "005,Ñandú,€ y «comillas»,7\n"
).encode()


def test_text_version_round_trip_keeps_the_logical_hash(scenario: Scenario) -> None:
    s = scenario
    project = s.project_id
    first = upload(s.client, s.headers, project, TRICKY, name="dificil.csv").json()
    assert make_runner(s.db, s.objects).run_once()
    exported = s.client.get(f"/api/v1/versions/{first['id']}/export.csv")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    assert "dificil-v" in exported.headers["content-disposition"]
    again = upload(s.client, s.headers, project, exported.content, name="vuelta.csv").json()
    assert make_runner(s.db, s.objects).run_once()
    original, before = table_of(s, first["id"])
    reimported, after = table_of(s, again["id"])
    # El hash lógico incluye los IDs de columna, propios de cada versión: se recalcula la tabla
    # reimportada con los descriptores de la original (mismos nombres, tipos y celdas).
    assert table_logical_sha256(original.columns, after) == original.logical_content_sha256
    assert [c["name"] for c in reimported.columns] == [c["name"] for c in original.columns]
    assert after.to_dicts() == before.to_dicts()
    assert before.row(1)[1] is None and before.row(3) == ("004", None, None, None)


def test_derived_typed_version_exports_in_both_profiles(scenario: Scenario) -> None:
    s = scenario
    table = typed_table(s)
    version = table["version_id"]
    assert s.client.get(f"/api/v1/versions/{version}/original").status_code == 409  # sin cambios
    standard = s.client.get(f"/api/v1/versions/{version}/export.csv").content.decode()
    lines = standard.split("\n")
    assert lines[0] == "id,fecha,region,importe,unidades"
    assert lines[1] == "001,2026-01-01,Norte,100.50,2"
    assert lines[2] == "002,2026-01-02,Sur,,1"  # nulo: vacío
    regional = s.client.get(
        f"/api/v1/versions/{version}/export.csv", params={"profile": "excel_regional"}
    ).content
    assert regional.startswith(b"\xef\xbb\xbfid;fecha;region;importe;unidades\r\n")
    assert b"001;2026-01-01;Norte;100,50;2\r\n" in regional
    assert (
        s.client.get(
            f"/api/v1/versions/{version}/export.csv", params={"profile": "otro"}
        ).status_code
        == 422
    )


def test_analysis_result_csv_keeps_each_evidence_id(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    table = typed_table(s)
    income, operations = metrics_for(s, table)
    semantic = confirm_semantics(
        s, table, importe=("measure", "EUR"), fecha=("business_date", None)
    )
    plan = query_plan(
        s,
        table,
        [income, operations],
        semantic,
        version=2,
        dimensions=[c["region"]],
        ranking={"metric_revision_id": operations["id"], "top_n": 3},
        share_of_total=[income["id"]],
    )
    run = execute(s, plan)
    result = s.client.get(f"/api/v1/executions/{run}/analysis").json()
    exported = s.client.get(f"/api/v1/executions/{run}/analysis.csv")
    assert exported.status_code == 200
    frame = pl.read_csv(io.BytesIO(exported.content), infer_schema=False)
    assert frame.columns[:4] == ["Posición", "Posición · evidence_id", "region", "Ingresos (EUR)"]
    assert "Ingresos · % del total · evidence_id" in frame.columns
    north = frame.row(0, named=True)
    assert (north["region"], north["Ingresos (EUR)"]) == ("Norte", "201.00")
    assert north["Ingresos · evidence_id"] == result["rows"][0]["evidence"]["m0"]
    assert north["Posición · evidence_id"] == result["rows"][0]["rank"]["evidence"]
    regional = s.client.get(
        f"/api/v1/executions/{run}/analysis.csv", params={"profile": "excel_regional"}
    ).content.decode("utf-8-sig")
    assert "1;" + result["rows"][0]["rank"]["evidence"] + ";Norte;201,00;" in regional
    other = s.client.get(f"/api/v1/executions/{uuid4()}/analysis.csv")
    assert other.status_code == 404
