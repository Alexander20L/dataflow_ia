"""Fase 31 (ADR-049): modelo de datos de tablas relacionadas y PostgreSQL.

- `relations-v1` (puro): claves sin vacíos ni repetidos; relaciones entre todas las tablas,
  declaradas o por el nombre, sólo si todos los valores existen; una vista por tabla de hechos
  (muchos a uno, a dos pasos) y una vista general por entidad con métricas de cada tabla de
  hechos; ante la duda no se une y se explica.
- Carga de 2 a 5 archivos: cada tabla y cada vista es una versión; se abre la vista principal.
- «Foto» del esquema (archivos y bases) sin guardar nada.
- Bases de datos: SQL Server (con esquema, `sqlserver-selection-v2`) y PostgreSQL usan las claves
  foráneas declaradas; PostgreSQL contra la base real de pruebas.
"""

import base64
import json
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project
from test_phase18b_sources import SECRET, FakeConnection, copied, database, fake_snapshot
from xlsx_support import Sheet, make_xlsx

from dataflow.integrations.sources import sqlserver_reader
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.contracts import (
    ForeignKey,
    PostgresConnection,
    SqlServerConnection,
    SqlSnapshot,
)
from dataflow.modules.ingestion.relations import Declared, Table, identifier, relate
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

CARRERAS = Table("carreras.csv", ["id", "carrera"], [["1", "Sistemas"], ["2", "Civil"]])
ESTUDIANTES = Table(
    "estudiantes.csv",
    ["id", "nombre", "id_carrera"],
    [["10", "Ana", "1"], ["11", "Luis", "2"], ["12", "Eva", "1"]],
)
ASISTENCIA = Table(
    "asistencia.csv",
    ["id", "id_estudiante", "fecha", "asistio"],
    [
        ["1", "10", "2026-03-02", "si"],
        ["2", "11", "2026-03-02", "no"],
        ["3", "10", "2026-03-09", "si"],
        ["4", "12", "2026-03-09", "si"],
        ["5", "11", "2026-03-09", "si"],
    ],
)
NOTAS = Table(
    "notas.csv",
    ["id_estudiante", "curso", "nota"],
    [["10", "Mate", "15"], ["10", "Física", "14"], ["11", "Mate", "10"], ["12", "Mate", "17.5"]],
)


# --- relations-v1 (puro) ----------------------------------------------------------------------


def test_each_fact_table_is_joined_to_what_it_points_without_changing_its_records() -> None:
    result = relate([CARRERAS, ESTUDIANTES, ASISTENCIA], [], 128)
    fact = next(v for v in result.views if v.kind == "fact")
    assert result.main == fact.name == "asistencia (tablas unidas)"
    assert fact.tables == ["asistencia.csv", "estudiantes.csv", "carreras.csv"]
    assert fact.headers == [
        "id",
        "id_estudiante",
        "fecha",
        "asistio",
        "nombre",
        "id_carrera",
        "carrera",
    ]
    assert len(fact.rows) == len(ASISTENCIA.rows)
    assert fact.rows[1] == ["2", "11", "2026-03-02", "no", "Luis", "2", "Civil"]
    roles = {t.label: t.role for t in result.tables}
    assert roles == {
        "asistencia.csv": "fact",
        "estudiantes.csv": "entity",
        "carreras.csv": "dimension",
    }
    keys = {t.label: t.keys for t in result.tables}
    assert keys["estudiantes.csv"] == ["id"]
    joined = {(r.table, r.column): r for r in result.relations if r.status == "joined"}
    assert joined[("asistencia.csv", "id_estudiante")].cardinality == "N:1"
    assert joined[("estudiantes.csv", "id_carrera")].added_columns == ["carrera"]


def test_two_fact_tables_are_analyzed_together_in_the_general_view() -> None:
    result = relate([CARRERAS, ESTUDIANTES, ASISTENCIA, NOTAS], [], 128)
    assert [v.kind for v in result.views] == ["fact", "fact", "entity"]
    general = result.views[-1]
    assert result.main == general.name == "estudiantes (vista general)"
    assert general.tables == ["estudiantes.csv", "carreras.csv", "asistencia.csv", "notas.csv"]
    assert general.headers == [
        "id",
        "nombre",
        "id_carrera",
        "carrera",
        "registros en asistencia",
        "% asistio = no (asistencia)",
        "registros en notas",
        "% curso = Física (notas)",
        "promedio de nota (notas)",
    ]
    # Un registro por estudiante; métricas exactas y sin redondear.
    assert general.rows == [
        ["10", "Ana", "1", "Sistemas", "2", "0", "2", "50", "14.5"],
        ["11", "Luis", "2", "Civil", "2", "50", "1", "0", "10"],
        ["12", "Eva", "1", "Sistemas", "1", "0", "1", "0", "17.5"],
    ]
    roles = {t.label: t.role for t in result.tables}
    assert roles["notas.csv"] == "fact" and roles["estudiantes.csv"] == "entity"


def test_averages_keep_every_decimal() -> None:
    notas = Table("notas.csv", ["id_estudiante", "nota"], [["10", "1"], ["10", "2"], ["11", "1"]])
    result = relate([ESTUDIANTES, notas], [], 128)
    general = next(v for v in result.views if v.kind == "entity")
    assert general.rows[0][-1] == "1.5"
    third = Table(
        "notas.csv", ["id_estudiante", "nota"], [["10", "1"], ["10", "1"], ["10", "2"], ["11", "1"]]
    )
    value = next(v for v in relate([ESTUDIANTES, third], [], 128).views if v.kind == "entity")
    assert value.rows[0][-1].startswith("1.3333333333")


def test_two_generic_ids_are_not_a_relation() -> None:
    a = Table("ventas.csv", ["id", "importe"], [["1", "5"], ["2", "7"]])
    b = Table("clientes.csv", ["id", "nombre"], [["1", "Ana"], ["2", "Luis"]])
    result = relate([a, b], [], 128)
    assert result.main is None and not result.relations and not result.views
    assert {t.role for t in result.tables} == {"separate"}


def test_values_without_a_match_prevent_the_join_and_say_how_many() -> None:
    orphan = Table(
        "asistencia.csv",
        ["id_estudiante", "fecha"],
        [["10", "2026-03-02"], ["99", "2026-03-02"], ["11", "2026-03-09"]],
    )
    result = relate([ESTUDIANTES, orphan], [], 128)
    assert result.main is None
    (relation,) = [r for r in result.relations if r.table == "asistencia.csv"]
    assert relation.status == "not_joined" and relation.reason.startswith("1 valor(es)")


def test_a_key_with_repeated_values_is_not_used() -> None:
    repeated = Table("estudiantes.csv", ["codigo_alumno", "nombre"], [["A", "x"], ["A", "y"]])
    child = Table("notas.csv", ["codigo_alumno", "nota"], [["A", "15"], ["A", "12"]])
    assert relate([repeated, child], [], 128).main is None


def test_two_columns_pointing_to_the_same_table_are_ambiguous() -> None:
    ciudades = Table("ciudades.csv", ["id", "ciudad"], [["1", "Lima"], ["2", "Cusco"]])
    vuelos = Table(
        "vuelos.csv",
        ["id_ciudad", "ciudad_id", "pasajeros"],
        [["1", "2", "100"], ["2", "1", "80"]],
    )
    result = relate([ciudades, vuelos], [], 128)
    assert result.main is None
    assert all("Más de una columna" in r.reason for r in result.relations)


def test_declared_foreign_keys_relate_columns_with_any_name() -> None:
    clientes = Table("dbo.Clientes", ["Codigo", "Nombre"], [["C1", "Ana"], ["C2", "Luis"]])
    ventas = Table("dbo.Ventas", ["Comprador", "Importe"], [["C1", "5"], ["C2", "7"], ["C1", "1"]])
    result = relate(
        [clientes, ventas], [Declared("dbo.Ventas", "Comprador", "dbo.Clientes", "Codigo")], 128
    )
    assert result.main == "Ventas (tablas unidas)"
    assert result.views[0].headers == ["Comprador", "Importe", "Nombre"]
    assert result.relations[0].origin == "declared"


def test_repeated_column_names_get_the_table_name() -> None:
    sedes = Table("sedes.csv", ["id", "nombre"], [["1", "Norte"], ["2", "Sur"]])
    ventas = Table("ventas.csv", ["nombre", "id_sede"], [["Ana", "1"], ["Luis", "2"], ["Eva", "1"]])
    result = relate([sedes, ventas], [], 128)
    assert result.views[0].headers == ["nombre", "id_sede", "nombre (sedes)"]


def test_the_column_limit_stops_the_join_with_its_reason() -> None:
    result = relate([ESTUDIANTES, ASISTENCIA], [], 5)
    assert not [v for v in result.views if v.kind == "fact"]
    assert any("5 columnas" in r.reason for r in result.relations)


def test_identifier_names_are_recognized() -> None:
    assert [identifier(n) for n in ["id_estudiante", "CodigoCliente", "IdVenta", "nro"]] == [
        True
    ] * 4
    assert not identifier("nota") and not identifier("ciudad")


# --- Lectura en el subproceso ----------------------------------------------------------------


def related_payload(files: list[tuple[str, str, bytes]], declared: Any = ()) -> bytes:
    return json.dumps(
        {
            "tables": [
                {"label": name, "format": kind, "content_base64": base64.b64encode(data).decode()}
                for name, kind, data in files
            ],
            "declared": list(declared),
        }
    ).encode()


def test_windows_csv_and_workbook_are_read_like_their_own_versions(objects: LocalObjects) -> None:
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    students = "codigo_alumno;nombre;beca\r\nA1;Ana;1.234,50\r\nA2;Íñigo;800,00\r\n".encode(
        "cp1252"
    )
    book = make_xlsx(
        [
            Sheet(
                "Notas",
                [
                    ["codigo_alumno", "curso", "nota"],
                    ["A1", "Mate", 15],
                    ["A2", "Mate", 12],
                    ["A1", "Física", 14],
                ],
            )
        ]
    )
    result = analyzer.relate(
        related_payload([("alumnos.csv", "csv", students), ("notas.xlsx", "xlsx", book)]),
        analyzer.config(None),
    )
    assert result.main == "notas (tablas unidas)"
    assert result.xlsx["notas.xlsx"].sheet == "Notas"
    lines = result.csv["notas (tablas unidas)"].splitlines()
    assert lines[0] == "codigo_alumno,curso,nota,nombre,beca"
    # Valores regionales en formato canónico; texto en Windows-1252 bien leído.
    assert lines[2] == "A2,Mate,12,Íñigo,800.00"
    general = result.csv["alumnos (vista general)"].splitlines()
    assert general[1] == "A1,Ana,1234.50,2,50,14.5"


def test_an_unreadable_file_is_named_in_the_error(objects: LocalObjects) -> None:
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    with pytest.raises(ApplicationError) as raised:
        analyzer.relate(
            related_payload([("a.csv", "csv", b"x,y\n1,2\n"), ("b.csv", "csv", b"x,y\n1\n")]),
            analyzer.config(None),
        )
    assert raised.value.message.startswith("b.csv:")


# --- Carga de varios archivos por la API -------------------------------------------------------


def csv_bytes(table: Table) -> bytes:
    lines = [",".join(table.headers)] + [",".join(c or "" for c in row) for row in table.rows]
    return ("\n".join(lines) + "\n").encode()


def related_body(files: list[tuple[str, bytes]]) -> dict[str, Any]:
    return {
        "files": [
            {"name": name, "content_base64": base64.b64encode(data).decode()}
            for name, data in files
        ]
    }


def upload_related(
    client: TestClient,
    headers: dict[str, str],
    pid: str,
    files: list[tuple[str, bytes]],
    key: str | None = None,
):
    return client.post(
        f"/api/v1/projects/{pid}/imports/related",
        json=related_body(files),
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def test_the_schema_photo_of_related_files_saves_nothing(client: TestClient) -> None:
    headers = account(client)
    pid = project(client, headers)
    files = [(t.label, csv_bytes(t)) for t in (CARRERAS, ESTUDIANTES, ASISTENCIA, NOTAS)]
    response = client.post(
        f"/api/v1/projects/{pid}/imports/related/inspect",
        json=related_body(files),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    model = response.json()
    assert model["rule"] == "relations-v1" and model["main"] == "estudiantes (vista general)"
    assert {t["label"]: t["role"] for t in model["tables"]}["notas.csv"] == "fact"
    tables = {t["label"]: t for t in model["tables"]}
    assert tables["estudiantes.csv"]["headers"] == ["id", "nombre", "id_carrera"]
    assert tables["estudiantes.csv"]["keys"] == ["id"]
    assert [v["kind"] for v in model["views"]] == ["fact", "fact", "entity"]
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["items"] == []


def test_related_files_become_versions_and_the_general_view_is_analyzed(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    key = str(uuid4())
    files = [(t.label, csv_bytes(t)) for t in (CARRERAS, ESTUDIANTES, ASISTENCIA, NOTAS)]
    created = upload_related(client, headers, pid, files, key)
    assert created.status_code == 202, created.text
    main = created.json()
    assert main["file_name"] == "estudiantes (vista general).csv"
    origin = main["source_origin"]
    assert origin["kind"] == "related" and origin["rule"] == "relations-v1" and origin["joined"]
    assert origin["view_kind"] == "entity"
    assert sorted(origin["analyzed_together"]) == [
        "asistencia.csv",
        "carreras.csv",
        "estudiantes.csv",
        "notas.csv",
    ]
    assert len(origin["views"]) == 3
    # La misma clave no vuelve a registrar nada.
    assert upload_related(client, headers, pid, files, key).json()["id"] == main["id"]
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    names = {v["file_name"] for v in versions}
    assert names == {
        "carreras.csv",
        "estudiantes.csv",
        "asistencia.csv",
        "notas.csv",
        "asistencia (tablas unidas).csv",
        "notas (tablas unidas).csv",
        "estudiantes (vista general).csv",
    }
    members = {v["file_name"]: v for v in versions}
    assert members["notas.csv"]["source_origin"]["joined"] is False
    original = client.get(f"/api/v1/versions/{members['carreras.csv']['id']}/original")
    assert original.content == csv_bytes(CARRERAS)
    for _ in range(len(versions)):
        assert process(db, objects)
    page = client.get(f"/api/v1/versions/{main['id']}/preview").json()
    assert page["total"] == len(ESTUDIANTES.rows)
    assert page["rows"][0]["values"]["promedio de nota (notas)"] == "14.5"


def test_related_files_without_a_common_key_are_analyzed_separately(
    client: TestClient,
) -> None:
    headers = account(client)
    pid = project(client, headers)
    a = Table("ventas.csv", ["id", "importe"], [["1", "5"], ["2", "7"], ["3", "1"]])
    b = Table("clientes.csv", ["id", "nombre"], [["1", "Ana"], ["2", "Luis"]])
    created = upload_related(client, headers, pid, [(t.label, csv_bytes(t)) for t in (b, a)])
    assert created.status_code == 202, created.text
    main = created.json()
    assert main["file_name"] == "ventas.csv"  # la de más registros
    assert main["source_origin"]["joined"] is False
    assert {t["role"] for t in main["source_origin"]["tables"]} == {"separate"}


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ([("a.csv", b"x\n1\n")], "RELATED_INVALID"),
        ([("a.csv", b"x\n1\n"), ("b.txt", b"x\n1\n")], "RELATED_FORMAT"),
        ([("a.csv", b"x\n1\n"), ("A.CSV", b"x\n1\n")], "RELATED_DUPLICATE_NAMES"),
    ],
)
def test_related_files_are_validated_before_reading(
    client: TestClient, files: list[tuple[str, bytes]], code: str
) -> None:
    headers = account(client)
    pid = project(client, headers)
    response = upload_related(client, headers, pid, files)
    assert response.status_code == 422 and response.json()["code"] == code
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["items"] == []


# --- Bases de datos: esquema y claves foráneas declaradas --------------------------------------


def test_sqlserver_can_be_limited_to_one_schema() -> None:
    connection = FakeConnection(database())
    result = sqlserver_reader.read_database(lambda: connection, 100, 128, "log")
    assert [t.label for t in result.tables] == ["log.Eventos"]
    empty = FakeConnection(database())
    with pytest.raises(ApplicationError) as raised:
        sqlserver_reader.read_database(lambda: empty, 100, 128, "nada")
    assert raised.value.code == "SQLSERVER_SCHEMA_EMPTY"


def test_sqlserver_v2_takes_up_to_ten_tables() -> None:
    tables = [
        sqlserver_reader.Candidate(
            "dbo",
            f"T{i:02d}",
            10 + i,
            [sqlserver_reader.Column("a", "int"), sqlserver_reader.Column("b", "int")],
        )
        for i in range(12)
    ]
    chosen, omitted = sqlserver_reader.choose(tables, 100, 128, sqlserver_reader.MAX_TABLES_V2)
    assert len(chosen) == 10 and [t for t, _ in omitted] == ["dbo.T01", "dbo.T00"]


def sqlserver_with_keys(monkeypatch: pytest.MonkeyPatch) -> list[SqlServerConnection]:
    monkeypatch.setattr(get_settings(), "sqlserver_allowed_hosts", ["sql.example.com"])
    base = fake_snapshot(
        [
            ("dbo.Ventas", ["Id", "Comprador", "Importe"], [["1", "C1", "5"], ["2", "C2", "7"]]),
            ("dbo.Clientes", ["Codigo", "Nombre"], [["C1", "Ana"], ["C2", "Luis"]]),
        ]
    )
    base.tables[0].foreign_keys = [ForeignKey(column="Comprador", references="dbo.Clientes.Codigo")]
    seen: list[SqlServerConnection] = []

    def snapshot(
        self: IsolatedAnalyzer, c: SqlServerConnection, cfg: Any, timeout: int | None = None
    ) -> SqlSnapshot:
        seen.append(c)
        return base

    monkeypatch.setattr(IsolatedAnalyzer, "snapshot_sqlserver", snapshot)
    return seen


SQL_BODY = {
    "server": "sql.example.com",
    "database": "ventas",
    "schema_name": "dbo",
    "user": "lector",
    "password": SECRET,
}


def test_sqlserver_schema_photo_shows_declared_keys_and_saves_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = sqlserver_with_keys(monkeypatch)
    headers = account(client)
    pid = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver/inspect", json=SQL_BODY, headers=headers
    )
    model = copied(client, response)
    assert seen[0].schema_name == "dbo"
    assert model["relations"][0]["origin"] == "declared"
    assert model["omitted"] == [{"table": "dbo.Notas", "reason": "Menos de dos columnas."}]
    assert SECRET not in response.text
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["items"] == []


def test_sqlserver_tables_with_declared_keys_open_the_joined_view(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlserver_with_keys(monkeypatch)
    headers = account(client)
    pid = project(client, headers)
    created = client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver",
        json=SQL_BODY,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    main = copied(client, created)
    assert main["file_name"] == "Ventas (tablas unidas).csv"
    origin = main["source_origin"]
    assert origin["kind"] == "related" and origin["database"] == "ventas/dbo"
    assert origin["relations"][0]["origin"] == "declared"
    assert SECRET not in json.dumps(origin)
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    names = {v["file_name"] for v in versions}
    assert names == {
        "Ventas (tablas unidas).csv",
        "Clientes (vista general).csv",
        "dbo.Ventas.csv",
        "dbo.Clientes.csv",
    }
    table = next(v for v in versions if v["file_name"] == "dbo.Ventas.csv")
    assert table["source_origin"]["rule"] == "sqlserver-selection-v3"


# --- PostgreSQL ---------------------------------------------------------------------------------


@pytest.fixture
def pg_source() -> Any:
    """Un esquema efímero de la base de pruebas con dos tablas y una clave foránea."""
    url = make_url(get_settings().database_url)
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    schema = "src_" + uuid4().hex[:12]
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".carreras (id integer PRIMARY KEY, carrera text,'
                " foto bytea)"
            )
        )
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".alumnos (codigo text PRIMARY KEY,'
                f' carrera integer REFERENCES "{schema}".carreras(id), ingreso timestamp,'
                " promedio numeric(5,2))"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".carreras VALUES'
                " (1, 'Sistemas', NULL), (2, 'Civil', NULL)"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".alumnos VALUES'
                " ('A1', 1, '2024-03-01 00:00', 15.5), ('A2', 2, '2024-03-01 00:00', 12.25),"
                " ('A3', 1, '2023-08-15 00:00', 17)"
            )
        )
    yield url, schema
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def pg_connection(url: Any, schema: str, password: str | None = None) -> PostgresConnection:
    return PostgresConnection(
        server=url.host or "127.0.0.1",
        port=url.port or 5432,
        database=url.database or "",
        schema_name=schema,
        user=url.username or "",
        password=password if password is not None else unquote(url.password or ""),
    )


def pg_body(connection: PostgresConnection) -> dict[str, Any]:
    return {**connection.model_dump(), "password": connection.password.get_secret_value()}


def test_postgresql_schema_is_copied_read_only_with_its_foreign_keys(
    objects: LocalObjects, pg_source: Any
) -> None:
    url, schema = pg_source
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    snapshot = analyzer.snapshot_postgresql(pg_connection(url, schema), analyzer.config(None))
    tables = {t.label: t for t in snapshot.tables}
    assert set(tables) == {f"{schema}.alumnos", f"{schema}.carreras"}
    alumnos = tables[f"{schema}.alumnos"]
    assert alumnos.csv.splitlines()[1] == "A1,1,2024-03-01,15.50"  # medianoche → fecha
    assert alumnos.foreign_keys == [
        ForeignKey(column="carrera", references=f"{schema}.carreras.id")
    ]
    assert tables[f"{schema}.carreras"].excluded_columns[0].column == "foto"


def test_wrong_postgresql_password_fails_without_echoing_it(
    objects: LocalObjects, pg_source: Any
) -> None:
    url, schema = pg_source
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    with pytest.raises(ApplicationError) as raised:
        analyzer.snapshot_postgresql(pg_connection(url, schema, SECRET), analyzer.config(None))
    assert raised.value.code == "POSTGRESQL_CONNECTION" and SECRET not in raised.value.message


def test_postgresql_import_only_reaches_allowed_hosts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = account(client)
    pid = project(client, headers)
    body = {"server": "pg.example.com", "database": "x", "user": "u", "password": SECRET}
    disabled = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert disabled.status_code == 503 and disabled.json()["code"] == "POSTGRESQL_DISABLED"
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", ["otro.example.com"])
    other = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect", json=body, headers=headers
    )
    assert other.status_code == 422 and other.json()["code"] == "POSTGRESQL_HOST_NOT_ALLOWED"


def test_postgresql_schema_photo_and_import_use_the_declared_key(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
    pg_source: Any,
) -> None:
    url, schema = pg_source
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", [url.host or "127.0.0.1"])
    headers = account(client)
    pid = project(client, headers)
    connection = pg_connection(url, schema)
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect",
        json=pg_body(connection),
        headers=headers,
    )
    model = copied(client, photo)
    (joined,) = [r for r in model["relations"] if r["status"] == "joined"]
    assert joined["origin"] == "declared" and joined["column"] == "carrera"
    # La relación por el nombre («carrera» → «carreras.carrera») se descarta con su motivo.
    assert any("no están en" in r["reason"] for r in model["relations"] if r is not joined)
    assert {t["label"]: t["role"] for t in model["tables"]}[f"{schema}.alumnos"] == "fact"
    created = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=pg_body(connection),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    main = copied(client, created)
    origin = main["source_origin"]
    assert main["file_name"] == "alumnos (tablas unidas).csv"
    assert origin["kind"] == "related" and origin["database"].endswith(f"/{schema}")
    versions = client.get(f"/api/v1/projects/{pid}/versions").json()["items"]
    assert len(versions) == 4  # dos tablas, la vista de alumnos y la vista general de carreras
    for version in versions:
        run = client.get(f"/api/v1/executions/{version['execution_id']}").json()
        assert connection.password.get_secret_value() not in json.dumps(run)
    for _ in range(len(versions)):
        assert process(db, objects)
    rows = client.get(f"/api/v1/versions/{main['id']}/preview").json()["rows"]
    assert rows[1]["values"]["carrera (carreras)"] == "Civil"
