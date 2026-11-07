"""Fase 12B: conexiones de SQL Server con un servidor simulado (el real se prueba en CI)."""

import io
import json
import logging
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import polars as pl
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project

from dataflow.bootstrap.app import app
from dataflow.bootstrap.dependencies import Db, Objects, connection_service
from dataflow.bootstrap.services import make_connections
from dataflow.integrations.sources.sqlserver_reader import (
    ConnectionParameters,
    canonical,
    quote,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.connection_records import ConnectionRecord
from dataflow.modules.ingestion.connections import Materialized
from dataflow.modules.ingestion.contracts import (
    Discovery,
    SqlColumn,
    SqlObject,
    SqlObjectInfo,
)
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

PASSWORD = "Contraseña-Secreta-123"
TABLE = {
    ("dbo", "ventas"): (
        [("id", "int"), ("fecha", "date"), ("importe", "decimal"), ("region", "nvarchar")],
        [
            [str(n), "2026-01-0" + str(n % 9 + 1), f"{n}.50", "Norte" if n % 2 else None]
            for n in range(1, 31)
        ],
    ),
    ("ventas", "secreta"): ([("x", "int")], [["1"]]),
}


class FakeServer:
    def __init__(self) -> None:
        self.extractions = 0

    def check(self, credentials: dict[str, Any]) -> None:
        if credentials["password"] != PASSWORD:
            raise ApplicationError("SQL_LOGIN_FAILED", "Usuario o contraseña no válidos.", 422)

    def discover(self, credentials: dict[str, Any], timeout: int) -> Discovery:
        self.check(credentials)
        return Discovery(
            objects=[SqlObjectInfo(schema_name=s, name=n, kind="table") for s, n in sorted(TABLE)],
            can_write=True,
            server_version="16.0.1000.6",
        )

    def extract(
        self,
        credentials: dict[str, Any],
        target: SqlObject,
        config: ProcessingConfig,
        max_bytes: int,
        truncate: bool,
    ) -> Materialized:
        self.check(credentials)
        self.extractions += 1
        columns, rows = TABLE[(target.schema_name, target.name)]
        rows = rows[: config.max_rows] if truncate else rows
        names = [name for name, _ in columns]
        buffer = io.BytesIO()
        pl.DataFrame(rows, schema={n: pl.String for n in names}, orient="row").write_parquet(buffer)
        return Materialized(
            parquet=buffer.getvalue(),
            columns=[SqlColumn(name=n, sql_type=t) for n, t in columns],
            rows=rows,
            row_count=len(rows),
            byte_count=sum(len(v or "") for r in rows for v in r),
            consistency="snapshot",
            server_version="16.0.1000.6",
        )


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    fake = FakeServer()
    monkeypatch.setattr(get_settings(), "sources_key", SecretStr(Fernet.generate_key().decode()))

    def override(db: Db, objects: Objects):  # type: ignore[no-untyped-def]
        return make_connections(db, objects, gateway=fake)

    app.dependency_overrides[connection_service] = override
    yield fake
    app.dependency_overrides.pop(connection_service, None)


def draft(**changes: Any) -> dict[str, Any]:
    return {
        "name": "ERP",
        "host": "sql.example.internal",
        "port": 1433,
        "database": "ventas",
        "username": "lector",
        "password": PASSWORD,
        **changes,
    }


def test_values_identifiers_and_connection_string_are_safe() -> None:
    assert canonical(Decimal("100.50"), "c") == "100.50"
    assert canonical(date(2026, 1, 2), "c") == "2026-01-02"
    assert canonical(True, "c") == "true" and canonical(None, "c") is None
    with pytest.raises(ApplicationError):
        canonical(b"\x00", "c")
    assert quote("a]b") == "[a]]b]"
    odbc = ConnectionParameters("h", 1433, "d", "u", "p}w;x").odbc(30)
    assert "PWD={p}}w;x}" in odbc and "Encrypt=yes" in odbc
    assert "TrustServerCertificate=no" in odbc and "ApplicationIntent=ReadOnly" in odbc


def test_connection_lifecycle_extraction_and_no_password_leak(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    server: FakeServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    headers = account(client)
    project_id = project(client, headers)
    base = f"/api/v1/projects/{project_id}/connections"
    bad = client.post(base + "/discover", json=draft(password="otra"), headers=headers)
    assert bad.status_code == 422 and bad.json()["code"] == "SQL_LOGIN_FAILED"
    found = client.post(base + "/discover", json=draft(), headers=headers)
    assert found.status_code == 200, found.text
    assert {o["name"] for o in found.json()["objects"]} == {"ventas", "secreta"}

    missing = client.post(
        base,
        json=draft(allowed_objects=[{"schema_name": "dbo", "name": "no_existe"}]),
        headers=headers,
    )
    assert missing.status_code == 422 and missing.json()["code"] == "SQL_OBJECT_NOT_FOUND"
    created = client.post(
        base,
        json=draft(allowed_objects=[{"schema_name": "dbo", "name": "ventas"}]),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    connection = created.json()
    assert "password" not in connection and connection["can_write"] is True
    listed = client.get(base, headers=headers)
    assert [c["id"] for c in listed.json()] == [connection["id"]]
    record = db.scalar(select(ConnectionRecord).where(ConnectionRecord.id == connection["id"]))
    assert record and PASSWORD not in record.password_ciphertext

    path = f"/api/v1/connections/{connection['id']}"
    denied = client.post(
        path + "/preview", json={"schema_name": "ventas", "name": "secreta"}, headers=headers
    )
    assert denied.status_code == 403 and denied.json()["code"] == "SQL_OBJECT_NOT_ALLOWED"
    preview = client.post(
        path + "/preview", json={"schema_name": "dbo", "name": "ventas"}, headers=headers
    ).json()
    assert len(preview["rows"]) == 20 and preview["consistency"] == "snapshot"

    key = str(uuid4())
    extraction = client.post(
        path + "/extractions",
        json={"schema_name": "dbo", "name": "ventas"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert extraction.status_code == 202, extraction.text
    calls = server.extractions
    again = client.post(
        path + "/extractions",
        json={"schema_name": "dbo", "name": "ventas"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert again.json()["id"] == extraction.json()["id"] and server.extractions == calls
    assert process(db, objects)
    version = extraction.json()["id"]
    state = client.get(f"/api/v1/versions/{version}", headers=headers).json()
    assert state["state"] == "succeeded", state
    assert state["file_name"] == "dbo.ventas.parquet"
    page = client.get(
        f"/api/v1/versions/{version}/preview", params={"limit": 100}, headers=headers
    ).json()
    assert page["total"] == 30
    assert page["rows"][0]["values"] == {
        "id": "1",
        "fecha": "2026-01-02",
        "importe": "1.50",
        "region": "Norte",
    }
    provenance = client.get(f"/api/v1/versions/{version}/extraction", headers=headers).json()
    assert provenance["row_count"] == 30 and provenance["consistency"] == "snapshot"
    assert provenance["columns"][2] == {"name": "importe", "sql_type": "decimal"}

    revoked = client.delete(path, headers=headers)
    assert revoked.status_code == 204
    assert client.get(base, headers=headers).json() == []
    gone = client.post(
        path + "/extractions",
        json={"schema_name": "dbo", "name": "ventas"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert gone.status_code == 404
    # Procedencia conservada tras revocar; contraseña cifrada borrada.
    assert client.get(f"/api/v1/versions/{version}/extraction", headers=headers).status_code == 200

    # La contraseña no aparece en auditoría, planes, ejecuciones ni registros.
    for table in (
        "audit_events",
        "execution_plan_revisions",
        "execution_runs",
        "execution_error_details",
        "ingestion_connections",
    ):
        exists = db.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar()
        if exists:
            dump = json.dumps(
                [list(map(str, r)) for r in db.execute(text(f"SELECT * FROM {table}"))]
            )
            assert PASSWORD not in dump, table
    assert PASSWORD not in caplog.text


def test_connections_need_the_server_key(
    client: TestClient, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "sources_key", None)
    headers = account(client)
    project_id = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json=draft(allowed_objects=[{"schema_name": "dbo", "name": "ventas"}]),
        headers=headers,
    )
    assert response.status_code == 503 and response.json()["code"] == "SOURCES_KEY_MISSING"


def test_server_messages_drop_driver_prefixes() -> None:
    from dataflow.integrations.sources.sqlserver_reader import server_message

    error = Exception(
        "42000",
        "[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]The SELECT permission "
        "was denied on the object 'ventas'. (229) (SQLExecDirectW)",
    )
    assert server_message(error) == (
        "The SELECT permission was denied on the object 'ventas'. (229)"
    )
