"""Fase 32A (ADR-050): conexión a bases de datos públicas.

- `database-destination-v1` (puro): sólo servidores de la lista o, en el modo público, con
  todas sus direcciones públicas y no denegadas; se conecta a la dirección comprobada.
- El subproceso repite la comprobación con su propia resolución (DNS que cambia).
- En el modo público el certificado se verifica; sin cifrado verificable no se conecta.
- Lo que devuelve el servidor tiene límites (celdas, total, catálogo).
- Intentos limitados por cuenta y por destino; entorno mínimo en los subprocesos.
- SQL Server sigue sólo con la lista.
"""

import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_csv_ingestion import account, project
from test_phase18b_sources import SECRET, copied
from test_phase31_related import pg_body, pg_connection, pg_source, sqlserver_with_keys

from dataflow.integrations.sources import postgresql_reader, sqlserver_reader
from dataflow.integrations.sources.sqlserver_reader import Budget
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion import processor
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.contracts import PostgresConnection
from dataflow.platform import destinations, isolation
from dataflow.platform.config import Settings, get_settings
from dataflow.platform.destinations import Allowed, Denied, DestinationPolicy, decide
from dataflow.platform.errors import ApplicationError

__all__ = ["pg_source"]  # fixture compartida con la Fase 31

PUBLIC = DestinationPolicy(public=True)
PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"

# --- database-destination-v1 (puro) -------------------------------------------------------------


def test_without_list_or_public_mode_nothing_is_reachable() -> None:
    assert decide("db.example.com", ["8.8.8.8"], DestinationPolicy()) == Denied("DISABLED")


def test_listed_servers_are_trusted_even_if_private() -> None:
    policy = DestinationPolicy(("Interna.Local",))
    assert decide("interna.local", ["10.0.0.5"], policy) == Allowed("10.0.0.5", "allowlist")
    assert decide("otra.local", ["8.8.8.8"], policy) == Denied("HOST_NOT_ALLOWED")
    assert decide("interna.local", [], policy) == Denied("HOST_UNKNOWN")


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.169.254",  # metadatos de la nube
        "100.64.0.1",  # espacio compartido (CGNAT)
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "192.0.2.10",  # documentación
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",  # IPv4 mapeada
        "::ffff:169.254.169.254",
        "64:ff9b::a00:1",  # NAT64 de 10.0.0.1
        "2002:a00:1::1",  # 6to4 de 10.0.0.1
        "no-es-una-ip",
    ],
)
def test_public_mode_refuses_every_non_public_address(address: str) -> None:
    assert decide("db.example.com", [address], PUBLIC) == Denied("HOST_PRIVATE")


def test_public_mode_accepts_public_addresses_and_pins_the_first() -> None:
    assert decide("db.example.com", ["8.8.8.8", "1.1.1.1"], PUBLIC) == Allowed("8.8.8.8", "public")
    assert decide("db.example.com", ["2001:4860:4860::8888"], PUBLIC) == Allowed(
        "2001:4860:4860::8888", "public"
    )


def test_one_private_address_refuses_the_whole_name() -> None:
    assert decide("db.example.com", ["8.8.8.8", "10.0.0.1"], PUBLIC) == Denied("HOST_PRIVATE")
    assert decide("db.example.com", [], PUBLIC) == Denied("HOST_UNKNOWN")


def test_denied_networks_are_refused_with_the_same_reason() -> None:
    policy = DestinationPolicy(public=True, denied=("8.8.8.0/24", "2001:db8::/32"))
    assert decide("db.example.com", ["8.8.8.8"], policy) == Denied("HOST_PRIVATE")
    assert decide("db.example.com", ["8.8.4.4"], policy) == Allowed("8.8.4.4", "public")
    mapped = DestinationPolicy(public=True, denied=("8.8.8.8/32",))
    assert decide("db.example.com", ["::ffff:8.8.8.8"], mapped) == Denied("HOST_PRIVATE")


def test_addresses_are_resolved_without_dns_when_written_as_such() -> None:
    assert destinations.resolve("8.8.8.8", 5432) == ["8.8.8.8"]
    assert destinations.resolve("nadie.invalid", 5432) == []
    assert all(not destinations.is_public(a) for a in destinations.resolve("localhost", 5432))
    assert destinations.denied_networks(["10.1.0.0/16", "8.8.8.8", " "]) == (
        "10.1.0.0/16",
        "8.8.8.8/32",
    )


def test_policy_travels_to_the_subprocess_unchanged() -> None:
    policy = DestinationPolicy(("a.example.com",), True, ("10.0.0.0/8",))
    assert DestinationPolicy.from_json(policy.as_json()) == policy


# --- La comprobación que cuenta: en el subproceso, justo antes de conectar -------------------


def test_the_subprocess_checks_again_with_its_own_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un nombre que en la API resolvía a una dirección pública y ahora apunta a la red
    interna (DNS que cambia) se rechaza en el subproceso."""
    monkeypatch.setattr(destinations, "resolve", lambda server, port: ["127.0.0.1"])
    params = {"server": "cambia.example.com", "port": 5432, "policy": PUBLIC.as_json()}
    with pytest.raises(ApplicationError) as raised:
        processor.postgresql_destination(params)
    assert raised.value.code == "DATABASE_HOST_PRIVATE"
    monkeypatch.setattr(destinations, "resolve", lambda server, port: ["8.8.8.8"])
    assert processor.postgresql_destination(params) == Allowed("8.8.8.8", "public")


def test_without_policy_the_subprocess_treats_the_server_as_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(destinations, "resolve", lambda server, port: ["10.0.0.9"])
    params = {"server": "interna.local", "port": 5432}
    assert processor.postgresql_destination(params) == Allowed("10.0.0.9", "allowlist")


# --- API -----------------------------------------------------------------------------------------


def public_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "database_public_access", True)
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", [])


@pytest.mark.parametrize(
    ("server", "code"),
    [
        ("127.0.0.1", "DATABASE_HOST_PRIVATE"),
        ("localhost", "DATABASE_HOST_PRIVATE"),
        ("169.254.169.254", "DATABASE_HOST_PRIVATE"),
        ("nadie.invalid", "DATABASE_HOST_UNKNOWN"),
    ],
)
def test_public_mode_never_reaches_internal_servers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, server: str, code: str
) -> None:
    public_mode(monkeypatch)
    headers = account(client)
    pid = project(client, headers)
    body = {"server": server, "database": "x", "user": "u", "password": SECRET}
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect", json=body, headers=headers
    )
    assert photo.status_code == 422 and photo.json()["code"] == code
    assert SECRET not in photo.text
    created = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 422 and created.json()["code"] == code


def test_public_mode_denies_the_dataflow_database_even_when_listed_elsewhere(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La base de DataFlow se deniega aunque su dirección fuera pública."""
    public_mode(monkeypatch)
    monkeypatch.setattr(destinations, "resolve", lambda server, port: ["8.8.8.8"])
    monkeypatch.setattr(
        get_settings(), "database_url", "postgresql+psycopg://u:p@8.8.8.8:5432/dataflow"
    )
    headers = account(client)
    pid = project(client, headers)
    body = {"server": "db.example.com", "database": "x", "user": "u", "password": SECRET}
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect", json=body, headers=headers
    )
    assert photo.status_code == 422 and photo.json()["code"] == "DATABASE_HOST_PRIVATE"


def test_listed_servers_keep_working_in_public_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pg_source: Any
) -> None:
    url, schema = pg_source
    public_mode(monkeypatch)
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", [url.host or "127.0.0.1"])
    headers = account(client)
    pid = project(client, headers)
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect",
        json=pg_body(pg_connection(url, schema)),
        headers=headers,
    )
    assert copied(client, photo)["tables"]


def test_sqlserver_stays_list_only_in_public_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_mode(monkeypatch)
    headers = account(client)
    pid = project(client, headers)
    body = {"server": "8.8.8.8", "database": "x", "user": "u", "password": SECRET}
    disabled = client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver/inspect", json=body, headers=headers
    )
    assert disabled.status_code == 503 and disabled.json()["code"] == "SQLSERVER_DISABLED"
    monkeypatch.setattr(get_settings(), "sqlserver_allowed_hosts", ["sql.example.com"])
    other = client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver/inspect", json=body, headers=headers
    )
    assert other.status_code == 422 and other.json()["code"] == "SQLSERVER_HOST_NOT_ALLOWED"


def test_connection_attempts_are_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlserver_with_keys(monkeypatch)
    monkeypatch.setattr(get_settings(), "database_attempts_per_user", 2)
    headers = account(client)
    pid = project(client, headers)
    body = {
        "server": "sql.example.com",
        "database": "ventas",
        "user": "lector",
        "password": SECRET,
    }
    for _ in range(2):
        ok = client.post(
            f"/api/v1/projects/{pid}/imports/sqlserver/inspect", json=body, headers=headers
        )
        assert copied(client, ok)["tables"]
    limited = client.post(
        f"/api/v1/projects/{pid}/imports/sqlserver/inspect", json=body, headers=headers
    )
    assert limited.status_code == 429 and limited.json()["code"] == "DATABASE_RATE_LIMITED"
    # Otra cuenta sí puede (el límite por destino es más alto).
    other = account(client)
    other_pid = project(client, other)
    again = client.post(
        f"/api/v1/projects/{other_pid}/imports/sqlserver/inspect", json=body, headers=other
    )
    assert copied(client, again)["tables"]


def test_database_access_tells_the_screen_what_to_show(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = account(client)
    assert client.get("/api/v1/database-access", headers=headers).json() == {
        "postgresql": "disabled",
        "sqlserver": "disabled",
        "egress_ips": [],
    }
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", ["pg.example.com"])
    monkeypatch.setattr(get_settings(), "sqlserver_allowed_hosts", ["sql.example.com"])
    monkeypatch.setattr(get_settings(), "database_egress_ips", ["203.0.113.7"])
    listed = client.get("/api/v1/database-access", headers=headers).json()
    assert listed == {"postgresql": "allowlist", "sqlserver": "allowlist", "egress_ips": []}
    monkeypatch.setattr(get_settings(), "database_public_access", True)
    public = client.get("/api/v1/database-access", headers=headers).json()
    assert public["postgresql"] == "public" and public["egress_ips"] == ["203.0.113.7"]
    client.cookies.clear()
    assert client.get("/api/v1/database-access").status_code == 401


def test_the_server_certificate_must_be_pem() -> None:
    base = {"server": "db.example.com", "database": "x", "user": "u", "password": SECRET}
    assert PostgresConnection(**base, ca_certificate=PEM).ca_certificate is not None
    assert PostgresConnection(**base, ca_certificate="  ").ca_certificate is None
    with pytest.raises(ValueError, match="PEM"):
        PostgresConnection(**base, ca_certificate="no es un certificado")
    assert PEM not in repr(PostgresConnection(**base, ca_certificate=PEM))


def test_public_mode_needs_isolation_to_start() -> None:
    with pytest.raises(RuntimeError, match="connector"):
        Settings(database_public_access=True).require_database_isolation()
    Settings(
        database_public_access=True, database_public_unisolated=True
    ).require_database_isolation()
    Settings().require_database_isolation()


# --- Conexión y lectura ------------------------------------------------------------------------


def test_verified_connections_refuse_a_server_without_tls(pg_source: Any) -> None:
    url, _ = pg_source
    with pytest.raises(ApplicationError) as raised:
        postgresql_reader.connect(
            url.host or "127.0.0.1",
            url.port or 5432,
            url.database or "",
            url.username or "",
            url.password or "",
            10,
            address="127.0.0.1",
            verify=True,
        )
    assert raised.value.code == "DATABASE_TLS_UNVERIFIED"


def test_listed_copies_record_how_they_were_reached(objects: LocalObjects, pg_source: Any) -> None:
    url, schema = pg_source
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    snapshot = analyzer.snapshot_postgresql(pg_connection(url, schema), analyzer.config(None))
    assert snapshot.access == "allowlist" and snapshot.tls in {"none", "encrypted"}


def test_oversized_cells_omit_the_table_and_the_total_stops_the_copy(
    objects: LocalObjects, pg_source: Any
) -> None:
    url, schema = pg_source
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    with admin.begin() as connection:
        connection.execute(text(f'CREATE TABLE "{schema}".notas (id integer, texto text)'))
        connection.execute(
            text(f"INSERT INTO \"{schema}\".notas VALUES (1, repeat('x', 70000)), (2, 'corto')")
        )
    admin.dispose()
    analyzer = IsolatedAnalyzer(objects.root, 45, 100_000, 128)
    snapshot = analyzer.snapshot_postgresql(pg_connection(url, schema), analyzer.config(None))
    omitted = {o.table: o.reason for o in snapshot.omitted}
    assert "64 KB" in omitted[f"{schema}.notas"]
    # Fase 33: el tope de la copia ya no la hace fallar: entran las tablas más pequeñas
    # (carreras, 45 bytes) y las que ya no caben (alumnos, 150) se omiten con su motivo.
    tiny = IsolatedAnalyzer(objects.root, 45, 100_000, 128, database_max_bytes=100)
    small = tiny.snapshot_postgresql(pg_connection(url, schema), tiny.config(None))
    assert [t.label for t in small.tables] == [f"{schema}.carreras"]
    reasons = {o.table: o.reason for o in small.omitted}
    assert "tamaño máximo" in reasons[f"{schema}.alumnos"]
    assert "64 KB" in reasons[f"{schema}.notas"]


class Batches:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        batch, self.rows = self.rows[:size], self.rows[size:]
        return batch


def test_rows_are_read_in_batches_with_limits() -> None:
    rows: list[tuple[object, ...]] = [(i, "x" * 10) for i in range(2500)]
    assert len(sqlserver_reader.fetch_rows(Batches(list(rows)), 3000, Budget())) == 2500
    assert "Más de 2000" in str(sqlserver_reader.fetch_rows(Batches(list(rows)), 2000, Budget()))
    wide = Budget(max_cell_bytes=5)
    assert "celdas" in str(sqlserver_reader.fetch_rows(Batches(list(rows)), 3000, wide))
    with pytest.raises(sqlserver_reader.BudgetExhausted):
        sqlserver_reader.fetch_rows(Batches(list(rows)), 3000, Budget(max_bytes=1000))


def test_a_crowded_catalog_is_refused() -> None:
    class Catalog:
        def __init__(self, tables: int) -> None:
            self.tables, self.result = tables, []

        def execute(self, operation: str, parameters: object = None) -> None:
            if "pg_class" in operation:
                self.result = [(f"t{i}", 10) for i in range(self.tables)]
            else:
                self.result = []

        def fetchall(self) -> list[tuple[object, ...]]:
            return self.result

    with pytest.raises(ApplicationError) as raised:
        postgresql_reader.catalog(Catalog(501), "public")
    assert raised.value.code == "DATABASE_TOO_LARGE"
    assert len(postgresql_reader.catalog(Catalog(3), "public")) == 3


# --- Entorno mínimo de los subprocesos ------------------------------------------------------------


def test_isolated_processes_do_not_inherit_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("DATAFLOW_DATABASE_URL", "DATAFLOW_AI_API_KEY", "PGPASSWORD", "FREETDSCONF"):
        monkeypatch.setenv(name, "secreto")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local")
    seen: dict[str, Any] = {}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.update(kwargs, command=command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(isolation.subprocess, "run", run)
    isolation.run_isolated(tmp_path, "modulo", {"input.bin": b"x"}, [], [], 5)
    environment = seen["env"]
    assert not {"DATAFLOW_DATABASE_URL", "DATAFLOW_AI_API_KEY", "PGPASSWORD", "FREETDSCONF"} & set(
        environment
    )
    assert "HTTPS_PROXY" not in environment and environment["PATH"] == os.environ["PATH"]
    assert (
        Path(seen["cwd"]).is_absolute()
        and Path(seen["cwd"]).parent == (tmp_path / ".work").resolve()
    )
    assert seen["command"][1] == "-P"
