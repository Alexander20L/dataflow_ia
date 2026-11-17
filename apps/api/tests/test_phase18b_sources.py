"""Fase 18B: tablas de SQL Server (copia de un solo uso) y de PDF con texto.

- `sqlserver-selection-v1`: tablas de usuario dentro de los límites, completas o nada; tipos no
  admitidos fuera con su motivo; la contraseña no se guarda en ninguna parte.
- `pdf-selection-v1`: tablas con cabecera; una cabecera repetida en la página siguiente une la
  tabla; PDF sin texto o sin tablas se rechaza con su motivo.
"""

import json
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdf_support import blank_pdf, grid, make_pdf, sales_rows
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project

from dataflow.integrations.sources import pdf_reader, sqlserver_reader
from dataflow.integrations.sources.sqlserver_reader import Candidate, Column, canonical, choose
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.contracts import (
    ExcludedColumn,
    OmittedSource,
    SnapshotTable,
    SqlServerConnection,
    SqlSnapshot,
)
from dataflow.platform.config import get_settings
from dataflow.platform.csv_export import write_csv
from dataflow.platform.errors import ApplicationError

SECRET = "contraseña-que-no-debe-quedar"

# --- SQL Server: lector (con una conexión simulada) ---------------------------------------------


class FakeCursor:
    def __init__(self, tables: dict[tuple[str, str], tuple[list[tuple[str, str]], list[tuple]]]):
        self.tables, self.result, self.queries = tables, [], []

    def execute(self, operation: str) -> None:
        self.queries.append(operation)
        if "sys.partitions" in operation:
            self.result = [(s, t, len(rows)) for (s, t), (_, rows) in self.tables.items()]
        elif "INFORMATION_SCHEMA.COLUMNS" in operation:
            self.result = [
                (s, t, name, kind)
                for (s, t), (columns, _) in self.tables.items()
                for name, kind in columns
            ]
        else:
            ((schema, table),) = [k for k in self.tables if f"[{k[0]}].[{k[1]}]" in operation]
            columns, rows = self.tables[(schema, table)]
            names = [n for n, _ in columns]
            wanted = [
                part.strip()[1:-1]
                for part in operation.split(")", 1)[1].split(" FROM ")[0].split(",")
            ]
            limit = int(operation.split("TOP (")[1].split(")")[0])
            self.result = [tuple(row[names.index(w)] for w in wanted) for row in rows][:limit]

    def fetchall(self) -> Sequence[Sequence[Any]]:
        return self.result


class FakeConnection:
    def __init__(self, tables: dict[tuple[str, str], tuple[list[tuple[str, str]], list[tuple]]]):
        self.cursor_ = FakeCursor(tables)
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_

    def close(self) -> None:
        self.closed = True


def database() -> dict[tuple[str, str], tuple[list[tuple[str, str]], list[tuple]]]:
    ventas_cols = [
        ("Id", "int"),
        ("Fecha", "datetime"),
        ("Región", "nvarchar"),
        ("Importe", "decimal"),
        ("Activo", "bit"),
        ("Foto", "varbinary"),
    ]
    ventas = [
        (
            i,
            datetime(2024, i, 1),
            "Norte" if i % 2 else "Sur",
            Decimal(f"{i}0.50"),
            i % 2 == 0,
            b"x",
        )
        for i in range(1, 7)
    ]
    return {
        ("dbo", "Ventas"): (ventas_cols, ventas),
        ("dbo", "Clientes"): (
            [("Codigo", "char"), ("Alta", "date"), ("Puntos", "float")],
            [("C1", date(2024, 1, 5), 1.5), ("C2", date(2024, 2, 5), 1e-05)],
        ),
        ("dbo", "Notas"): ([("Texto", "nvarchar")], [("a",), ("b",)]),
        ("log", "Eventos"): ([("Id", "int"), ("Msg", "nvarchar")], [(i, "x") for i in range(50)]),
        ("dbo", "Vacia"): ([("A", "int"), ("B", "int")], []),
    }


def test_sqlserver_snapshot_copies_whole_tables_with_canonical_cells() -> None:
    connection = FakeConnection(database())
    result = sqlserver_reader.read_database(lambda: connection, 20, 128)
    assert connection.closed
    assert [t.label for t in result.tables] == ["dbo.Ventas", "dbo.Clientes"]
    ventas = result.tables[0]
    assert ventas.headers == ["Id", "Fecha", "Región", "Importe", "Activo"]
    # Fechas a medianoche → fecha; decimales sin exponente; bit → true/false.
    assert ventas.rows[0] == ["1", "2024-01-01", "Norte", "10.50", "false"]
    assert [c.name for c in ventas.excluded] == ["Foto"]
    clientes = result.tables[1]
    assert clientes.rows == [["C1", "2024-01-05", "1.5"], ["C2", "2024-02-05", "0.00001"]]
    reasons = dict(result.omitted)
    assert reasons["dbo.Notas"] == "Menos de dos columnas con tipos admitidos."
    assert reasons["dbo.Vacia"] == "Menos de dos registros."
    assert reasons["log.Eventos"] == "Más de 20 registros: no se copia en parte."
    # Identificadores entre corchetes; nunca se interpolan valores.
    assert any("FROM [dbo].[Ventas]" in q for q in connection.cursor_.queries)


def test_sqlserver_selection_ranks_and_limits_tables() -> None:
    tables = [
        Candidate("dbo", f"T{i}", 10 + i, [Column("a", "int"), Column("b", "int")])
        for i in range(7)
    ]
    chosen, omitted = choose(tables, 100, 128)
    assert [c.name for c in chosen] == ["T6", "T5", "T4", "T3", "T2"]
    assert [t for t, _ in omitted] == ["dbo.T1", "dbo.T0"]
    assert sqlserver_reader.quote("a]b") == "[a]]b]"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, "true"),
        (12, "12"),
        (Decimal("1E+3"), "1000"),
        (2.5e-07, "0.00000025"),
        (datetime(2024, 1, 2, 3, 4, 5), "2024-01-02 03:04:05"),
        (UUID(int=1), "00000000-0000-0000-0000-000000000001"),
        ("", None),
    ],
)
def test_sqlserver_values_become_canonical_text(value: object, expected: str | None) -> None:
    assert canonical(value) == expected


def test_sqlserver_without_usable_tables_explains_why() -> None:
    connection = FakeConnection({("dbo", "Notas"): ([("Texto", "nvarchar")], [("a",), ("b",)])})
    with pytest.raises(ApplicationError) as error:
        sqlserver_reader.read_database(lambda: connection, 20, 128)
    assert error.value.code == "SQLSERVER_NO_TABLES"
    assert connection.closed


def test_unreachable_server_fails_without_echoing_the_password(objects: LocalObjects) -> None:
    analyzer = IsolatedAnalyzer(objects.root, 30, 1000, 128)
    connection = SqlServerConnection(
        server="127.0.0.1", port=1, database="ventas", user="lector", password=SECRET
    )
    with pytest.raises(ApplicationError) as error:
        analyzer.snapshot_sqlserver(connection, analyzer.config(None))
    assert error.value.code == "SQLSERVER_CONNECTION"
    assert SECRET not in error.value.message
    assert not list((objects.root / ".work").glob("*"))  # el directorio temporal se borró


# --- SQL Server: API (copia simulada) -----------------------------------------------------------


def fake_snapshot(tables: list[tuple[str, list[str], list[list[str | None]]]]) -> SqlSnapshot:
    return SqlSnapshot(
        tables=[
            SnapshotTable(
                label=label,
                headers=headers,
                csv=write_csv(headers, rows, "standard").decode(),
                excluded_columns=[ExcludedColumn(column="Foto", type="varbinary", reason="x")]
                if label == "dbo.Ventas"
                else [],
            )
            for label, headers, rows in tables
        ],
        omitted=[OmittedSource(table="dbo.Notas", reason="Menos de dos columnas.")],
    )


VENTAS = (
    "dbo.Ventas",
    ["Id", "Fecha", "Region", "Importe"],
    [[str(i), f"2024-{i:02d}-01", "Norte" if i % 2 else "Sur", f"{i}0.50"] for i in range(1, 7)],
)
CLIENTES = ("dbo.Clientes", ["Codigo", "Puntos"], [["C1", "1.5"], ["C2", "2"]])


def sqlserver(client: TestClient, headers: dict[str, str], pid: str, key: str | None = None):
    return client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver",
        json={
            "server": "sql.example.com",
            "port": 1433,
            "database": "ventas",
            "user": "lector",
            "password": SECRET,
        },
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def test_sqlserver_import_is_disabled_without_allowed_hosts(client: TestClient) -> None:
    headers = account(client)
    pid = project(client, headers)
    response = sqlserver(client, headers, pid)
    assert response.status_code == 503 and response.json()["code"] == "SQLSERVER_DISABLED"


def test_sqlserver_import_only_reaches_allowed_hosts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "sqlserver_allowed_hosts", ["otro.example.com"])
    headers = account(client)
    pid = project(client, headers)
    response = sqlserver(client, headers, pid)
    assert response.status_code == 422 and response.json()["code"] == "SQLSERVER_HOST_NOT_ALLOWED"


def test_sqlserver_tables_become_versions_and_the_password_is_not_kept(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "sqlserver_allowed_hosts", ["SQL.example.com"])
    seen: list[SqlServerConnection] = []

    def snapshot(self: IsolatedAnalyzer, connection: SqlServerConnection, config: Any):
        seen.append(connection)
        return fake_snapshot([VENTAS, CLIENTES])

    monkeypatch.setattr(IsolatedAnalyzer, "snapshot_sqlserver", snapshot)
    headers = account(client)
    pid = project(client, headers)
    key = str(uuid4())
    created = sqlserver(client, headers, pid, key)
    assert created.status_code == 202, created.text
    main = created.json()
    assert seen[0].password.get_secret_value() == SECRET
    assert main["file_name"] == "dbo.Ventas.csv"
    origin = main["source_origin"]
    assert origin["kind"] == "sqlserver" and origin["table"] == "dbo.Ventas"
    assert origin["server"] == "sql.example.com:1433" and origin["database"] == "ventas"
    assert origin["analyzed_together"] == ["dbo.Clientes"]
    assert origin["excluded_columns"][0]["column"] == "Foto"
    assert origin["omitted"] == [{"table": "dbo.Notas", "reason": "Menos de dos columnas."}]
    # Repetir con la misma clave no copia otra vez.
    assert sqlserver(client, headers, pid, key).json()["id"] == main["id"]
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    assert sorted(v["file_name"] for v in versions) == ["dbo.Clientes.csv", "dbo.Ventas.csv"]
    # La contraseña no está en el plan ni en el original.
    for version in versions:
        run = client.get(f"/api/v1/executions/{version['execution_id']}").json()
        assert SECRET not in json.dumps(run)
        assert (
            SECRET.encode() not in client.get(f"/api/v1/versions/{version['id']}/original").content
        )
    assert process(db, objects) and process(db, objects)
    rows = client.get(f"/api/v1/versions/{main['id']}/preview").json()["rows"]
    assert rows[0]["values"] == {
        "Id": "1",
        "Fecha": "2024-01-01",
        "Region": "Norte",
        "Importe": "10.50",
    }
    profile = client.get(f"/api/v1/versions/{main['id']}/diagnostic").json()["profile"]
    roles = {c["name"]: c["role"] for c in profile["overview"]["analysis"]["columns"]}
    assert roles["Importe"] == "measure" and roles["Fecha"] == "time"
    # Una copia posterior de la misma tabla se compara con la anterior.
    monkeypatch.setattr(
        IsolatedAnalyzer,
        "snapshot_sqlserver",
        lambda self, c, cfg: fake_snapshot(
            [("dbo.Ventas", ["Id", "Importe"], [["1", "2"], ["2", "3"]])]
        ),
    )
    again = sqlserver(client, headers, pid).json()
    assert again["source_origin"]["analyzed_together"] == []
    assert process(db, objects)
    structure = client.get(f"/api/v1/versions/{again['id']}/reading").json()["structure"]
    assert structure["previous_version_id"] == main["id"]
    assert {(c["column"], c["change"]) for c in structure["changes"]} == {
        ("Fecha", "removed"),
        ("Region", "removed"),
        ("Importe", "type_changed"),  # de decimal a entero
    }


# --- PDF ------------------------------------------------------------------------------------------


def test_pdf_tables_are_selected_and_repeated_headers_join_pages() -> None:
    content = make_pdf(
        "Informe de ventas",
        grid(sales_rows(40), repeat=True),
        grid([["k", "v"], ["a", "1"], ["b", "2"]]),
        grid([["solo"], ["x"], ["y"]]),
    )
    chosen = pdf_reader.select(content, 1000, 128)
    assert chosen.main.headers == ["Región", "Mes", "Importe"]
    assert len(chosen.main.rows) == 40 and len(chosen.main.segments) == 2
    assert chosen.main.label == "Tabla 1 de las páginas 1–2"
    assert [t.headers for t in chosen.additional] == [["k", "v"]]
    assert [reason for _, reason in chosen.omitted] == [
        "Sin una fila de cabecera con nombres únicos en todas las columnas."
    ]
    table = pdf_reader.read_table(content, chosen.main.segments, 1000, 128)
    assert table.rows[0] == ["Norte", "2024-01", "1.001,50"]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (blank_pdf(), "PDF_NO_TEXT"),
        (make_pdf("Sólo texto, sin tablas."), "PDF_NO_TABLES"),
        (b"%PDF-1.4 roto", "PDF_MALFORMED"),
    ],
)
def test_pdf_without_readable_tables_is_explained(content: bytes, code: str) -> None:
    with pytest.raises(ApplicationError) as error:
        pdf_reader.select(content, 1000, 128)
    assert error.value.code == code


def upload_pdf(client: TestClient, headers: dict[str, str], pid: str, content: bytes):
    return client.post(
        f"/api/v1/projects/{pid}/imports/pdf",
        params={"file_name": "informe.pdf"},
        content=content,
        headers={**headers, "Content-Type": "application/pdf", "Idempotency-Key": str(uuid4())},
    )


def test_each_pdf_table_becomes_a_version_with_regional_values(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = make_pdf(
        grid(sales_rows(12)), grid([["Concepto", "Gasto"], ["Luz", "1.234,5"], ["Agua", "80,25"]])
    )
    created = upload_pdf(client, headers, pid, content)
    assert created.status_code == 202, created.text
    main = created.json()
    assert main["source_origin"]["kind"] == "pdf"
    assert main["source_origin"]["rule"] == "pdf-selection-v1"
    assert main["source_origin"]["pages"] == [1]
    run = client.get(f"/api/v1/executions/{main['execution_id']}").json()
    read = run["plan"]["content"]["steps"][0]
    assert (read["operation"], read["version"]) == ("ingestion.read_pdf", 1)
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    assert len(versions) == 2 and {v["sha256"] for v in versions} == {main["sha256"]}
    assert process(db, objects) and process(db, objects)
    rows = client.get(f"/api/v1/versions/{main['id']}/preview").json()["rows"]
    assert rows[0]["values"] == {"Región": "Norte", "Mes": "2024-01", "Importe": "1001.50"}
    review = client.get(f"/api/v1/versions/{main['id']}/reading").json()
    reading = review["reading"]
    assert review["origin"]["table"] == "Tabla 1 de la página 1"
    assert reading["format"] == "pdf"
    assert [c["column"] for c in reading["converted"]] == ["Importe"]
    assert client.get(f"/api/v1/versions/{main['id']}/original").content == content


@pytest.mark.parametrize(
    ("content", "code", "status"),
    [
        (blank_pdf(), "PDF_NO_TEXT", 422),
        (b"no es un pdf", "PDF_MALFORMED", 422),
    ],
)
def test_unreadable_pdf_is_rejected_before_registering(
    client: TestClient, content: bytes, code: str, status: int
) -> None:
    headers = account(client)
    pid = project(client, headers)
    response = upload_pdf(client, headers, pid, content)
    assert response.status_code == status and response.json()["code"] == code
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["total"] == 0


def test_report_states_where_a_copied_table_comes_from() -> None:
    from datetime import UTC
    from datetime import datetime as moment

    from test_phase16_investigation import reference_analysis
    from test_phase17_delivery import investigation, source

    from dataflow.modules.delivery.public import build_report
    from dataflow.modules.ingestion.contracts import SourceOrigin, SourceReading, SourceReview

    analysis = reference_analysis()
    result = investigation(analysis)
    review = SourceReview(
        reading=SourceReading(format="csv", encoding="utf-8-sig", separator=","),
        structure=None,
        origin=SourceOrigin(
            kind="sqlserver",
            rule="sqlserver-selection-v1",
            table="dbo.Ventas",
            server="sql.example.com:1433",
            database="ventas",
            captured_at="2026-11-09T12:00:00+00:00",
            excluded_columns=[
                ExcludedColumn(column="Foto", type="varbinary", reason="Tipo no admitido.")
            ],
            analyzed_together=["dbo.Clientes"],
        ),
    )
    document = build_report(
        source(analysis, result), analysis, result, None, moment(2026, 11, 9, tzinfo=UTC), review
    )
    facts = next(s for s in document.sections if s.id == "reading").blocks[0].paragraphs
    assert facts[0].startswith("Copia de la tabla dbo.Ventas de la base ventas")
    assert "la contraseña no se guardó" in facts[0]
    assert facts[1] == "Columna Foto no copiada: Tipo no admitido."
    assert facts[2] == "Analizadas aparte: dbo.Clientes."
