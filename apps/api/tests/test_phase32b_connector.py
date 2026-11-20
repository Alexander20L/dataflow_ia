"""Fase 32B (ADR-050): servicio `connector` para bases PostgreSQL públicas.

- El conector sólo atiende a la API (token compartido), repite la regla de destinos en su
  subproceso y devuelve la copia o el mismo error que el subproceso local.
- La API copia en el conector los destinos fuera de la lista; los de la lista, como antes.
- Sin conector (o sin token), el modo público no arranca salvo en desarrollo.
- Compose: el conector no comparte red con `postgres` ni con el exterior salvo `egress`.
"""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import uvicorn
import yaml
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_csv_ingestion import account, project
from test_phase18b_sources import SECRET, copied, fake_snapshot
from test_phase31_related import pg_body, pg_connection, pg_source

from dataflow.bootstrap import services
from dataflow.bootstrap.connector import create_app
from dataflow.bootstrap.connector_client import HttpConnector
from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.contracts import PostgresConnection, SqlSnapshot
from dataflow.platform import destinations
from dataflow.platform.config import Settings, get_settings
from dataflow.platform.destinations import DestinationPolicy
from dataflow.platform.errors import ApplicationError

__all__ = ["pg_source"]  # fixture compartida con la Fase 31

TOKEN = "t" * 40
CONFIG = ProcessingConfig(max_rows=100_000, max_columns=128, timeout_seconds=45)
COMPOSE = Path(__file__).resolve().parents[3] / "infrastructure" / "compose" / "compose.yaml"


def listed(url: Any) -> DestinationPolicy:
    return DestinationPolicy((url.host or "127.0.0.1",))


def request_body(connection: PostgresConnection, policy: DestinationPolicy) -> dict[str, Any]:
    return {
        "connection": pg_body(connection),
        "policy": {
            "allowed_hosts": list(policy.allowed_hosts),
            "public": policy.public,
            "denied": list(policy.denied),
        },
        "max_rows": 100_000,
        "max_columns": 128,
        "timeout_seconds": 45,
        "max_bytes": 50 * 1024 * 1024,
        "max_cell_bytes": 64 * 1024,
    }


@pytest.fixture
def connector(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(connector_token=TOKEN), scratch=tmp_path))


# --- El servicio ------------------------------------------------------------------------------


def test_the_connector_refuses_to_start_without_a_token(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="token"):
        create_app(Settings(), scratch=tmp_path)
    with pytest.raises(RuntimeError, match="token"):
        create_app(Settings(connector_token="corto"), scratch=tmp_path)


def test_the_connector_only_answers_to_the_api(connector: TestClient) -> None:
    assert connector.get("/health").json() == {"status": "ok"}
    for headers in ({}, {"Authorization": "Bearer otro"}, {"Authorization": TOKEN}):
        refused = connector.post("/v1/snapshot/postgresql", json={}, headers=headers)
        assert refused.status_code == 401 and refused.json()["code"] == "CONNECTOR_UNAUTHORIZED"
    auth = {"Authorization": f"Bearer {TOKEN}"}
    invalid = connector.post("/v1/snapshot/postgresql", json={"x": 1}, headers=auth)
    assert invalid.status_code == 422 and invalid.json()["code"] == "CONNECTOR_INVALID"
    huge = connector.post("/v1/snapshot/postgresql", content=b"x" * (200 * 1024), headers=auth)
    assert huge.status_code == 413
    # Sin documentación ni esquema públicos.
    assert connector.get("/docs").status_code == 404
    assert connector.get("/openapi.json").status_code == 404


def test_the_connector_copies_a_schema_and_repeats_the_destination_rule(
    connector: TestClient, pg_source: Any
) -> None:
    url, schema = pg_source
    auth = {"Authorization": f"Bearer {TOKEN}"}
    connection = pg_connection(url, schema)
    copied = connector.post(
        "/v1/snapshot/postgresql", json=request_body(connection, listed(url)), headers=auth
    )
    assert copied.status_code == 200, copied.text
    snapshot = SqlSnapshot.model_validate_json(copied.content)
    assert {t.label for t in snapshot.tables} == {f"{schema}.alumnos", f"{schema}.carreras"}
    assert connection.password.get_secret_value() not in copied.text
    # En el modo público, la red interna sigue cerrada aunque la API se hubiera equivocado.
    private = connector.post(
        "/v1/snapshot/postgresql",
        json=request_body(connection, DestinationPolicy(public=True)),
        headers=auth,
    )
    assert private.status_code == 422 and private.json()["code"] == "DATABASE_HOST_PRIVATE"


# --- El cliente de la API, contra un conector real --------------------------------------------


@pytest.fixture
def running_connector(tmp_path: Path) -> Iterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(Settings(connector_token=TOKEN), scratch=tmp_path)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_the_api_client_gets_the_copy_or_the_same_error(
    running_connector: str, pg_source: Any
) -> None:
    url, schema = pg_source
    client = HttpConnector(running_connector, TOKEN, 50 * 1024 * 1024, 64 * 1024)
    snapshot = client.snapshot_postgresql(pg_connection(url, schema), CONFIG, listed(url))
    assert len(snapshot.tables) == 2 and snapshot.access == "allowlist"
    with pytest.raises(ApplicationError) as raised:
        client.snapshot_postgresql(
            pg_connection(url, schema), CONFIG, DestinationPolicy(public=True)
        )
    assert raised.value.code == "DATABASE_HOST_PRIVATE" and raised.value.status == 422
    with pytest.raises(ApplicationError) as wrong:
        client.snapshot_postgresql(pg_connection(url, schema, SECRET), CONFIG, listed(url))
    assert wrong.value.code == "POSTGRESQL_CONNECTION" and SECRET not in wrong.value.message


def test_a_misconfigured_or_missing_connector_is_an_outage(
    running_connector: str, pg_source: Any
) -> None:
    url, schema = pg_source
    impostor = HttpConnector(running_connector, "x" * 40, 1024, 1024)
    with pytest.raises(ApplicationError) as refused:
        impostor.snapshot_postgresql(pg_connection(url, schema), CONFIG, listed(url))
    assert refused.value.code == "DATABASE_CONNECTOR_UNAVAILABLE" and refused.value.status == 503
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed = probe.getsockname()[1]
    gone = HttpConnector(f"http://127.0.0.1:{closed}", TOKEN, 1024, 1024)
    with pytest.raises(ApplicationError) as missing:
        gone.snapshot_postgresql(pg_connection(url, schema), CONFIG, listed(url))
    assert missing.value.code == "DATABASE_CONNECTOR_UNAVAILABLE"
    with pytest.raises(ValueError):
        HttpConnector("file:///etc/passwd", TOKEN, 1, 1)


# --- La API desvía al conector lo que no está en la lista ---------------------------------------


class FakeConnector:
    calls: list[tuple[str, DestinationPolicy]] = []

    def __init__(self, *args: Any) -> None:
        pass

    def snapshot_postgresql(
        self,
        connection: PostgresConnection,
        config: ProcessingConfig,
        policy: DestinationPolicy,
        timeout: int | None = None,
    ) -> SqlSnapshot:
        FakeConnector.calls.append((connection.server, policy))
        return fake_snapshot(
            [("public.ventas", ["id", "importe"], [["1", "5"], ["2", "7"]])]
        ).model_copy(update={"access": "public", "tls": "verified"})


def connector_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeConnector.calls = []
    monkeypatch.setattr(services, "HttpConnector", FakeConnector)
    monkeypatch.setattr(get_settings(), "database_public_access", True)
    monkeypatch.setattr(get_settings(), "connector_url", "http://connector:8100")
    monkeypatch.setattr(get_settings(), "connector_token", SecretStr(TOKEN))


def test_public_destinations_are_copied_in_the_connector(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_mode(monkeypatch)
    monkeypatch.setattr(destinations, "resolve", lambda server, port: ["8.8.8.8"])
    headers = account(client)
    pid = project(client, headers)
    body = {"server": "db.example.com", "database": "x", "user": "u", "password": SECRET}
    created = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    origin = copied(client, created)["source_origin"]
    assert origin["access"] == "public" and origin["tls"] == "verified"
    ((server, policy),) = FakeConnector.calls
    assert server == "db.example.com" and policy.public
    # La propia base de DataFlow viaja como denegada.
    assert policy.denied


def test_listed_servers_are_still_copied_by_the_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pg_source: Any
) -> None:
    url, schema = pg_source
    connector_mode(monkeypatch)
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", [url.host or "127.0.0.1"])
    headers = account(client)
    pid = project(client, headers)
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect",
        json=pg_body(pg_connection(url, schema)),
        headers=headers,
    )
    assert copied(client, photo)["tables"]
    assert FakeConnector.calls == []


def test_private_destinations_never_reach_the_connector(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_mode(monkeypatch)
    headers = account(client)
    pid = project(client, headers)
    body = {"server": "127.0.0.1", "database": "x", "user": "u", "password": SECRET}
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect", json=body, headers=headers
    )
    assert photo.status_code == 422 and photo.json()["code"] == "DATABASE_HOST_PRIVATE"
    assert FakeConnector.calls == []


# --- Arranque ----------------------------------------------------------------------------------


def test_public_mode_starts_only_with_the_connector_and_its_token(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="CONNECTOR_URL"):
        Settings(database_public_access=True).require_database_isolation()
    with pytest.raises(RuntimeError, match="token"):
        Settings(
            database_public_access=True, connector_url="http://connector:8100"
        ).require_database_isolation()
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n", encoding="utf-8")
    ready = Settings(
        database_public_access=True,
        connector_url="http://connector:8100",
        connector_token_file=token_file,
    )
    ready.require_database_isolation()
    assert ready.connector_secret() == TOKEN
    # Fuera del modo público, la URL sin token no impide arrancar (el conector no se usa).
    Settings(connector_url="http://connector:8100").require_database_isolation()
    empty = tmp_path / "vacio"
    empty.write_text("", encoding="utf-8")
    assert Settings(connector_token_file=empty).connector_secret() is None


# --- Compose -----------------------------------------------------------------------------------


def test_compose_isolates_the_connector() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services_ = compose["services"]
    connector_ = services_["connector"]
    assert set(connector_["networks"]) == {"connector", "egress"}
    assert compose["networks"]["connector"]["internal"] is True
    # Nadie más está en `egress`, y el conector no está en la red de `postgres`.
    for name, service in services_.items():
        if name != "connector":
            assert "egress" not in service.get("networks", []), name
    assert set(services_["postgres"]["networks"]) == {"backend"}
    assert set(services_["api"]["networks"]) == {"backend", "connector"}
    # Sin credenciales de DataFlow ni clave de IA, sin volúmenes ni puertos, endurecido.
    environment = connector_.get("environment", {})
    assert not any(key.startswith(("DATAFLOW_DATABASE", "DATAFLOW_AI")) for key in environment)
    assert connector_.get("secrets") == ["connector_token"]
    assert "volumes" not in connector_ and "ports" not in connector_
    assert connector_["read_only"] is True and connector_["cap_drop"] == ["ALL"]
    assert connector_["profiles"] == ["public-databases"]
