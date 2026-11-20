"""Fase 33 (ADR-051): todas las tablas de una base, copia en segundo plano y espera del
presupuesto de IA.

- Se copian todas las tablas que caben, de menor a mayor; el tope de bytes, el tamaño de un
  original y la cuota omiten con su motivo en vez de fallar.
- «Analizar» y «Ver esquema» responden 202 con la copia; su estado se consulta aparte y una copia
  sin latido se da por interrumpida (la contraseña no se guarda).
- Con el presupuesto de IA agotado, los trabajos se aplazan hasta que se renueve, sin gastar
  intentos, y después siguen con IA.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase18b_sources import SECRET, copied
from test_phase19_comprehension import reference_csv
from test_phase31_related import pg_body, pg_connection, pg_source

from dataflow.bootstrap.database_copies import ThreadCopyRunner
from dataflow.bootstrap.services import make_runner
from dataflow.integrations.sources import sqlserver_reader
from dataflow.integrations.sources.sqlserver_reader import Candidate, Column
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions import application as executions_application
from dataflow.modules.executions.infrastructure import AttemptRecord, ExecutionRecord
from dataflow.modules.ingestion.infrastructure import DatabaseCopyRecord
from dataflow.platform.config import get_settings

__all__ = ["pg_source"]  # fixture compartida con la Fase 31


@pytest.fixture
def wide_source(pg_source: Any) -> Any:
    """El esquema de la Fase 31 con 25 tablas más (más de las 10 de antes)."""
    url, schema = pg_source
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    with admin.begin() as connection:
        for index in range(25):
            connection.execute(
                text(f'CREATE TABLE "{schema}".t{index:02d} (codigo integer, valor text)')
            )
            rows = ", ".join(f"({i}, '{'v' * (index + 1)}')" for i in range(2 + index))
            connection.execute(text(f'INSERT INTO "{schema}".t{index:02d} VALUES {rows}'))
    admin.dispose()
    return url, schema


def listed(monkeypatch: pytest.MonkeyPatch, url: Any) -> None:
    monkeypatch.setattr(get_settings(), "postgresql_allowed_hosts", [url.host or "127.0.0.1"])


# --- Todas las tablas ---------------------------------------------------------------------------


def test_every_table_is_chosen_from_the_smallest_up() -> None:
    tables = [
        Candidate("dbo", f"T{i}", 100 - i, [Column("a", "int"), Column("b", "int")])
        for i in range(30)
    ]
    chosen, omitted = sqlserver_reader.choose_all(tables, 1000, 128)
    assert len(chosen) == 30 and omitted == []
    assert [c.name for c in chosen][:3] == ["T29", "T28", "T27"]


def test_a_schema_with_many_tables_is_copied_whole(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, wide_source: Any
) -> None:
    url, schema = wide_source
    listed(monkeypatch, url)
    headers = account(client)
    pid = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=pg_body(pg_connection(url, schema)),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    copy = response.json()
    assert copy["tables"] == 27 and copy["omitted"] == 0
    main = copied(client, response)
    assert main["source_origin"]["rule"] == "relations-v1"
    versions = client.get(f"/api/v1/projects/{pid}/versions?limit=100").json()
    names = {v["file_name"] for v in versions["items"]}
    assert {f"{schema}.t{i:02d}.csv" for i in range(25)} <= names
    table = next(v for v in versions["items"] if v["file_name"] == f"{schema}.t00.csv")
    assert table["source_origin"]["rule"] == "postgresql-selection-v2"


def test_a_large_database_is_admitted_to_the_queue_as_a_whole(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, wide_source: Any
) -> None:
    """Las versiones de una misma base entran juntas aunque pasen del límite de pendientes
    (en la prueba real, 56 versiones contra un límite de 50)."""
    url, schema = wide_source
    listed(monkeypatch, url)
    monkeypatch.setattr(executions_application, "PENDING_LIMIT", 5)
    headers = account(client)
    pid = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=pg_body(pg_connection(url, schema)),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.json()["state"] == "succeeded", response.text
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["total"] > 5


def test_what_does_not_fit_the_account_quota_is_omitted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, wide_source: Any
) -> None:
    url, schema = wide_source
    listed(monkeypatch, url)
    # Sólo caben las primeras tablas (las más pequeñas); el resto se omite con su motivo.
    monkeypatch.setattr(get_settings(), "max_owner_storage_bytes", 400)
    headers = account(client)
    pid = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=pg_body(pg_connection(url, schema)),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    copy = response.json()
    assert copy["state"] == "succeeded", copy
    assert 0 < copy["tables"] < 27 and copy["omitted"] > 0
    main = copied(client, response)
    reasons = {o["reason"] for o in main["source_origin"]["omitted"]}
    assert any("cuota" in reason for reason in reasons)


# --- Copia en segundo plano ---------------------------------------------------------------------


def test_photo_and_copy_answer_at_once_and_are_read_later(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pg_source: Any
) -> None:
    url, schema = pg_source
    listed(monkeypatch, url)
    headers = account(client)
    pid = project(client, headers)
    photo = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql/inspect",
        json=pg_body(pg_connection(url, schema)),
        headers=headers,
    )
    assert photo.status_code == 202
    copy = photo.json()
    assert copy["kind"] == "photo" and copy["engine"] == "postgresql"
    again = client.get(f"/api/v1/database-copies/{copy['id']}", headers=headers)
    assert again.json()["state"] == "succeeded" and again.json()["model"]["tables"]
    assert client.get(f"/api/v1/projects/{pid}/versions").json()["items"] == []
    # La contraseña nunca está en la copia.
    assert SECRET not in photo.text and unquote_password(url) not in again.text
    # Otra cuenta no la ve.
    other = account(client)
    assert client.get(f"/api/v1/database-copies/{copy['id']}", headers=other).status_code == 404


def unquote_password(url: Any) -> str:
    from urllib.parse import unquote

    return unquote(url.password or "") or "sin-contraseña"


def test_a_failed_copy_keeps_its_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pg_source: Any
) -> None:
    url, schema = pg_source
    listed(monkeypatch, url)
    headers = account(client)
    pid = project(client, headers)
    response = client.post(
        f"/api/v1/projects/{pid}/imports/postgresql",
        json=pg_body(pg_connection(url, schema, SECRET)),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    copy = response.json()
    assert copy["state"] == "failed" and copy["error_code"] == "POSTGRESQL_CONNECTION"
    assert SECRET not in response.text


def test_a_copy_without_heartbeat_was_interrupted(client: TestClient, db: Session) -> None:
    headers = account(client)
    pid = project(client, headers)
    owner = client.get("/api/v1/auth/me").json()["user"]["id"]
    stale = datetime.now(UTC) - timedelta(minutes=5)
    record = DatabaseCopyRecord(
        id=uuid4(),
        owner_id=owner,
        project_id=pid,
        engine="postgresql",
        kind="import",
        state="running",
        server="db.example.com:5432",
        database_name="ventas",
        created_at=stale,
        heartbeat_at=stale,
    )
    db.add(record)
    db.flush()
    seen = client.get(f"/api/v1/database-copies/{record.id}", headers=headers).json()
    assert seen["state"] == "failed" and seen["error_code"] == "DATABASE_COPY_INTERRUPTED"
    assert "contraseña no se guarda" in seen["error_message"]


def test_the_thread_runner_does_one_copy_at_a_time_per_account() -> None:
    @contextmanager
    def sessions() -> Iterator[Any]:
        yield None

    runner = ThreadCopyRunner(4, sessions)  # type: ignore[arg-type]
    running: dict[str, int] = {"now": 0, "most": 0, "other": 0}
    lock = threading.Lock()
    done = threading.Event()
    finished: list[str] = []

    def job(name: str) -> Any:
        def work(db: Any) -> None:
            with lock:
                running["now"] += 1
                running["most"] = max(running["most"], running["now"])
            time.sleep(0.05)
            with lock:
                running["now"] -= 1
                finished.append(name)
                if len(finished) == 4:
                    done.set()

        return work

    owner, other = uuid4(), uuid4()
    for name in ("a", "b", "c"):
        runner.submit(owner, uuid4(), job(name))
    runner.submit(other, uuid4(), job("otra"))
    assert done.wait(5)
    # Las tres de la misma cuenta, una tras otra; la de otra cuenta, en paralelo.
    assert [n for n in finished if n != "otra"] == ["a", "b", "c"]
    assert running["most"] == 2


# --- Presupuesto de IA: esperar y seguir --------------------------------------------------------


def comprehension_run(db: Session, version: str) -> ExecutionRecord:
    record = db.scalar(
        select(ExecutionRecord).where(
            ExecutionRecord.version_id == version, ExecutionRecord.kind == "comprehension"
        )
    )
    assert record is not None
    db.refresh(record)
    return record


def deferred_until(db: Session, execution: Any) -> datetime | None:
    """Hasta cuándo espera un trabajo aplazado: el `lease_until` de su intento `deferred`."""
    return db.scalar(
        select(func.max(AttemptRecord.lease_until)).where(
            AttemptRecord.execution_id == execution, AttemptRecord.state == "deferred"
        )
    )


def drain(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def test_ai_jobs_wait_for_the_budget_and_then_continue_with_ai(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    monkeypatch.setattr(get_settings(), "ai_user_daily_tokens", 0)
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas.csv").json()["id"]
    drain(db, objects)
    run = comprehension_run(db, version)
    assert run.state == "queued" and run.error_code == "AI_BUDGET_WAITING"
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert deferred_until(db, run.id) == tomorrow
    progress = client.get(f"/api/v1/versions/{version}/progress", headers=headers).json()
    stage = next(s for s in progress["stages"] if s["id"] == "comprehension")
    assert stage["state"] == "queued" and "presupuesto de IA se renueva" in stage["detail"]
    # Cada vez que vuelve a probar y sigue sin presupuesto, se aplaza sin gastar intentos.
    for _ in range(4):
        db.execute(
            update(AttemptRecord)
            .where(AttemptRecord.execution_id == run.id, AttemptRecord.state == "deferred")
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.flush()
        drain(db, objects)
        assert comprehension_run(db, version).state == "queued"
    # Con presupuesto, sigue con IA.
    monkeypatch.setattr(get_settings(), "ai_user_daily_tokens", 1_000_000)
    db.execute(
        update(AttemptRecord)
        .where(AttemptRecord.execution_id == run.id, AttemptRecord.state == "deferred")
        .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.flush()
    drain(db, objects)
    view = client.get(f"/api/v1/versions/{version}/comprehension", headers=headers).json()
    assert view["state"] == "ready" and view["comprehension"]["ai_state"] == "ready"


def test_without_ai_configured_jobs_still_go_on_with_rules(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "disabled")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas.csv").json()["id"]
    drain(db, objects)
    view = client.get(f"/api/v1/versions/{version}/comprehension", headers=headers).json()
    assert view["state"] == "ready" and view["comprehension"]["ai_state"] == "unavailable"
