"""Fase 12B contra un SQL Server real (contenedor de CI). Se omite si no hay servidor:
DATAFLOW_TEST_SQLSERVER_HOST, _PORT, _USER y _PASSWORD (administrador sólo para preparar)."""

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session
from test_csv_ingestion import account, process, project

from dataflow.integrations.sources.sqlserver_reader import ConnectionParameters, connect
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings

HOST = os.environ.get("DATAFLOW_TEST_SQLSERVER_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="Sin SQL Server de pruebas")
DATABASE = "dataflow_test"
READER, READER_PASSWORD = "dataflow_lector", "Lector-Seguro-2026!"


def admin(database: str = "master") -> Any:
    return connect(
        ConnectionParameters(
            HOST or "",
            int(os.environ.get("DATAFLOW_TEST_SQLSERVER_PORT", "1433")),
            database,
            os.environ.get("DATAFLOW_TEST_SQLSERVER_USER", "sa"),
            os.environ.get("DATAFLOW_TEST_SQLSERVER_PASSWORD", ""),
            trust_server_certificate=True,
        ),
        30,
    )


@pytest.fixture(scope="module")
def sqlserver() -> Iterator[None]:
    connection = admin()
    cursor = connection.cursor()
    cursor.execute(f"IF DB_ID('{DATABASE}') IS NULL CREATE DATABASE [{DATABASE}]")
    cursor.execute(f"ALTER DATABASE [{DATABASE}] SET ALLOW_SNAPSHOT_ISOLATION ON")
    cursor.execute(
        f"IF SUSER_ID('{READER}') IS NULL CREATE LOGIN [{READER}] "
        f"WITH PASSWORD = '{READER_PASSWORD}', CHECK_POLICY = OFF"
    )
    connection.close()
    connection = admin(DATABASE)
    cursor = connection.cursor()
    for statement in [
        "IF OBJECT_ID('dbo.ventas') IS NOT NULL DROP TABLE dbo.ventas",
        "IF OBJECT_ID('dbo.secreta') IS NOT NULL DROP TABLE dbo.secreta",
        "CREATE TABLE dbo.ventas (id int, fecha date, importe decimal(10,2), "
        "region nvarchar(40), activo bit)",
        "INSERT INTO dbo.ventas VALUES (1, '2026-01-01', 100.50, N'Norte', 1), "
        "(2, '2026-01-02', NULL, N'Sur', 0), (3, '2026-01-03', 80.00, N'Peñas', NULL)",
        "CREATE TABLE dbo.secreta (x int)",
        f"IF USER_ID('{READER}') IS NULL CREATE USER [{READER}] FOR LOGIN [{READER}]",
        f"ALTER ROLE db_datareader ADD MEMBER [{READER}]",
    ]:
        cursor.execute(statement)
    connection.close()
    yield


def test_real_extraction_is_exact_read_only_and_rejects_unlisted_objects(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    sqlserver: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "sources_key", SecretStr(Fernet.generate_key().decode()))
    headers = account(client)
    project_id = project(client, headers)
    body = {
        "name": "CI",
        "host": HOST,
        "port": int(os.environ.get("DATAFLOW_TEST_SQLSERVER_PORT", "1433")),
        "database": DATABASE,
        "username": READER,
        "password": READER_PASSWORD,
        "trust_server_certificate": True,
    }
    base = f"/api/v1/projects/{project_id}/connections"
    discovery = client.post(base + "/discover", json=body, headers=headers)
    assert discovery.status_code == 200, discovery.text
    assert {"ventas", "secreta"} <= {o["name"] for o in discovery.json()["objects"]}
    assert discovery.json()["can_write"] is False  # sólo db_datareader
    created = client.post(
        base,
        json={**body, "allowed_objects": [{"schema_name": "dbo", "name": "ventas"}]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert READER_PASSWORD not in created.text
    path = f"/api/v1/connections/{created.json()['id']}"
    denied = client.post(
        path + "/extractions",
        json={"schema_name": "dbo", "name": "secreta"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert denied.status_code == 403
    extraction = client.post(
        path + "/extractions",
        json={"schema_name": "dbo", "name": "ventas"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert extraction.status_code == 202, extraction.text
    assert process(db, objects)
    version = extraction.json()["id"]
    rows = client.get(f"/api/v1/versions/{version}/preview", headers=headers).json()["rows"]
    names = ["id", "fecha", "importe", "region", "activo"]
    assert [r["values"] for r in rows] == [
        dict(zip(names, ["1", "2026-01-01", "100.50", "Norte", "true"], strict=True)),
        dict(zip(names, ["2", "2026-01-02", None, "Sur", "false"], strict=True)),
        dict(zip(names, ["3", "2026-01-03", "80.00", "Peñas", None], strict=True)),
    ]
    provenance = client.get(f"/api/v1/versions/{version}/extraction", headers=headers).json()
    assert provenance["consistency"] == "snapshot" and provenance["row_count"] == 3
