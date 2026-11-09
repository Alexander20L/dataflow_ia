import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from dataflow.bootstrap.provenance import environment_snapshot
from dataflow.bootstrap.services import make_datasets, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import (
    ArtifactRecord,
    AttemptRecord,
    ExecutionRecord,
    SQLExecutionRepository,
)
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.processor import parse_csv
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

CSV = (
    b"\xef\xbb\xbfid,importe,region,unidades\r\n"
    b"001,10.50,Norte,1\r\n002,,Sur,2\r\n001,10.50,Norte,1\r\n003, ,Sur,4\r\n"
)


def account(client: TestClient) -> dict[str, str]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Analista",
            "email": f"{uuid4().hex}@example.com",
            "password": "Prueba-de-integracion-123",
        },
    )
    assert response.status_code == 201
    return {"x-csrf-token": response.json()["csrf_token"]}


def project(client: TestClient, headers: dict[str, str]) -> str:
    return str(
        client.post("/api/v1/projects", json={"name": "Proyecto CSV"}, headers=headers).json()["id"]
    )


def upload(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    content: bytes = CSV,
    key: str | None = None,
    name: str = "ventas.csv",
):
    return client.post(
        f"/api/v1/projects/{project_id}/imports",
        params={"file_name": name},
        content=content,
        headers={**headers, "Content-Type": "text/csv", "Idempotency-Key": key or str(uuid4())},
    )


def process(db: Session, objects: LocalObjects) -> bool:
    return make_runner(db, objects, IsolatedAnalyzer(objects.root, 45, 100_000, 128)).run_once()


def claim(repo: SQLExecutionRepository):
    return repo.claim({"csv_import", "table_analysis"}, environment_snapshot())


def test_end_to_end_csv_integrity_quality_versions_and_reproducibility(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    key = str(uuid4())
    first = upload(client, headers, project_id, key=key)
    assert first.status_code == 202, first.text
    version = first.json()
    assert version["state"] == "queued"
    assert version["sha256"] == hashlib.sha256(CSV).hexdigest()
    assert upload(client, headers, project_id, key=key).json()["id"] == version["id"]
    assert upload(client, headers, project_id, content=b"id\n1\n", key=key).status_code == 409
    path = f"/api/v1/versions/{version['id']}"
    assert client.get(path + "/original").content == CSV
    assert client.get(path + "/diagnostic").status_code == 409
    assert process(db, objects)
    diagnostic = client.get(path + "/diagnostic")
    assert diagnostic.status_code == 200, diagnostic.text
    result = diagnostic.json()
    assert result["profile"]["row_count"] == 4
    assert result["profile"]["column_count"] == 4
    assert result["profile"]["columns"][0]["suggested_type"] == "string"
    assert result["profile"]["columns"][3]["numeric"]["total"] == "8"
    assert result["quality"]["missing_cells"] == 1
    assert result["quality"]["duplicate_rows"] == 1
    assert result["quality"]["whitespace_cells"] == 1
    assert result["quality"]["completeness_percent"] == 93.75
    preview = client.get(path + "/preview", params={"limit": 1, "offset": 1}).json()
    assert preview["total"] == 4 and preview["rows"][0]["values"]["id"] == "002"
    assert preview["rows"][0]["values"]["importe"] is None
    for issue, expected in [("Q-001-1", 2), ("Q-002", 3), ("Q-003-1", 4)]:
        affected = client.get(path + "/preview", params={"issue_id": issue}).json()
        assert affected["total"] == 1 and affected["rows"][0]["row_number"] == expected
    assert client.get(path + "/original").content == CSV
    second = upload(client, headers, project_id).json()
    assert second["number"] == 2 and second["dataset_id"] == version["dataset_id"]
    assert process(db, objects)
    assert client.get(f"/api/v1/versions/{second['id']}/diagnostic").json() == result
    assert client.get(f"/api/v1/projects/{project_id}/versions").json()["total"] == 2
    assert (
        db.scalar(select(func.count()).select_from(ArtifactRecord)) == 8
    )  # tabla, perfil, calidad y análisis automático (Fase 15)


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"id,id\n1,2\n", "CSV_DUPLICATE_HEADERS"),
        (b"id,nombre\n1\n", "CSV_SHAPE"),
        (b'id,nombre\n1,"sin cierre\n', "CSV_MALFORMED"),
        (b"id,nombre\n1,\xff\n", "CSV_ENCODING"),
        (b"id,nombre\n", "CSV_NO_ROWS"),
        (b"id\n\x00\n", "CSV_BINARY"),
    ],
)
def test_failed_csv_never_publishes_artifacts(
    client: TestClient, db: Session, objects: LocalObjects, content: bytes, code: str
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id, content=content).json()
    assert process(db, objects)
    status = client.get(f"/api/v1/projects/{project_id}/versions").json()["items"][0]
    assert status["state"] == "failed" and status["error_code"] == code
    assert db.scalar(select(func.count()).select_from(ArtifactRecord)) == 0
    assert client.get(f"/api/v1/versions/{version['id']}/original").content == content


def test_limits_archived_project_and_cross_account_access(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    assert upload(client, headers, project_id, content=b"").status_code == 422
    assert upload(client, headers, project_id, name="../ventas.csv").status_code == 422
    assert upload(client, headers, project_id, name="ventas.xlsx").status_code == 422
    assert (
        upload(client, headers, project_id, content=b"a" * (5 * 1024 * 1024 + 1)).status_code == 413
    )
    version = upload(client, headers, project_id).json()
    # Fase 13C: una segunda carga del mismo proyecto espera en cola en vez de rechazarse.
    assert upload(client, headers, project_id).status_code == 202
    assert process(db, objects)
    assert process(db, objects)
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/archive", json={"expected_revision": 1}, headers=headers
        ).status_code
        == 200
    )
    assert upload(client, headers, project_id).status_code == 409
    other = account(client)
    assert upload(client, other, project_id).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}/versions").status_code == 404
    for suffix in ["original", "preview", "diagnostic"]:
        assert client.get(f"/api/v1/versions/{version['id']}/{suffix}").status_code == 404
    assert (
        client.post(
            f"/api/v1/executions/{version['execution_id']}/cancel", headers=other
        ).status_code
        == 404
    )


def test_lease_recovery_and_stale_worker_fencing(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    repo = SQLExecutionRepository(db, make_datasets(db))
    first = claim(repo)
    assert first
    db.execute(
        update(AttemptRecord)
        .where(AttemptRecord.execution_id == first.execution_id)
        .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    second = claim(repo)
    assert second and second.execution_id == first.execution_id and second.token != first.token
    assert repo.stage(first, []) is None
    repo.fail(first, "OLD_WORKER", "No debe publicarse", False)
    repo.fail(second, "PROCESSING_TIMEOUT", "Reintento controlado", True)
    assert process(db, objects)
    result = repo.get(
        UUID(client.get("/api/v1/auth/me").json()["user"]["id"]), UUID(version["execution_id"])
    )
    assert result.state == "succeeded" and result.attempts == 3
    assert (
        db.scalar(select(func.count()).select_from(ArtifactRecord)) == 4
    )  # tabla, perfil, calidad y análisis automático (Fase 15)


def test_cancel_fences_running_worker(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    repo = SQLExecutionRepository(db, make_datasets(db))
    lease = claim(repo)
    assert lease
    assert (
        client.post(f"/api/v1/executions/{version['execution_id']}/cancel", headers=headers).json()[
            "state"
        ]
        == "cancelled"
    )
    assert repo.stage(lease, []) is None
    assert db.scalar(select(func.count()).select_from(ArtifactRecord)) == 0


def test_object_integrity_and_immutable_publication(tmp_path: Path) -> None:
    objects = LocalObjects(tmp_path)
    reference = objects.put("originals/test.csv", b"id\n1\n")
    assert objects.read(reference) == b"id\n1\n"
    with pytest.raises(ApplicationError, match="inmutable"):
        objects.put(reference.key, b"id\n2\n")
    objects.path(reference.key).write_bytes(b"id\n2\n")
    with pytest.raises(ApplicationError, match="integridad"):
        objects.read(reference)


def test_csv_quoting_separators_and_limits() -> None:
    headers, rows, separator = parse_csv(
        'id;nota\r\n001;"hola; mundo\nsegunda línea"\r\n'.encode(), ";", 100, 10
    )
    assert (
        headers == ["id", "nota"]
        and rows == [["001", "hola; mundo\nsegunda línea"]]
        and separator == ";"
    )
    with pytest.raises(ApplicationError, match="límite de registros"):
        parse_csv(b"id\n1\n2\n", ",", 1, 10)


def test_repeated_worker_loss_exhausts_attempts(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    repo = SQLExecutionRepository(db, make_datasets(db))
    for _ in range(3):
        lease = claim(repo)
        assert lease
        db.execute(
            update(AttemptRecord)
            .where(AttemptRecord.execution_id == lease.execution_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
    assert claim(repo) is None
    item = client.get(f"/api/v1/projects/{project_id}/versions").json()["items"][0]
    assert item["id"] == version["id"] and item["state"] == "failed"
    assert item["error_code"] == "ATTEMPTS_EXHAUSTED"
    assert db.scalar(select(func.count()).select_from(ArtifactRecord)) == 0


def test_account_queue_and_storage_limits(
    client: TestClient, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dataflow.modules.executions.application.PENDING_LIMIT", 3)
    headers = account(client)
    projects = [project(client, headers) for _ in range(4)]
    versions = [upload(client, headers, id).json() for id in projects[:3]]
    rejected = upload(client, headers, projects[3])
    assert rejected.status_code == 409 and rejected.json()["code"] == "QUEUE_LIMIT"
    summary = client.get("/api/v1/datasets/summary").json()
    assert summary == {"datasets": 3, "versions": 3, "processed": 0, "pending": 3, "failed": 0}
    for version in versions:
        assert (
            client.post(
                f"/api/v1/executions/{version['execution_id']}/cancel", headers=headers
            ).status_code
            == 200
        )
    monkeypatch.setattr(get_settings(), "max_owner_storage_bytes", len(CSV) * 3)
    rejected = upload(client, headers, projects[3])
    assert rejected.status_code == 413 and rejected.json()["code"] == "STORAGE_QUOTA"
    account(client)
    assert client.get("/api/v1/datasets/summary").json()["versions"] == 0


def test_uploads_wait_in_queue_instead_of_being_rejected(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    """Fase 13C: una carga nunca se rechaza por haber otras en curso; espera su turno."""
    headers = account(client)
    busy = project(client, headers)
    first = upload(client, headers, busy, name="v1.csv")
    second = upload(client, headers, busy, name="v2.csv")
    assert first.status_code == 202 and second.status_code == 202
    others = [project(client, headers) for _ in range(3)]
    queued = [upload(client, headers, id) for id in others]
    assert all(response.status_code == 202 for response in queued)
    repo = SQLExecutionRepository(db, make_datasets(db))
    leases = []
    while lease := claim(repo):
        db.commit()
        leases.append(lease.execution_id)
    db.commit()
    expected = [first.json()["execution_id"], *(r.json()["execution_id"] for r in queued[:2])]
    # Un máximo de tres trabajos a la vez por propietario y una importación por proyecto:
    # la v2 espera a la v1 y el tercer proyecto espera a que se libere un hueco.
    assert [str(id) for id in leases] == expected
    db.execute(
        update(AttemptRecord)
        .where(AttemptRecord.execution_id == UUID(first.json()["execution_id"]))
        .values(state="succeeded", finished_at=datetime.now(UTC), lease_until=None)
    )
    db.execute(
        update(ExecutionRecord)
        .where(ExecutionRecord.id == UUID(first.json()["execution_id"]))
        .values(state="succeeded", active_attempt_id=None, finished_at=datetime.now(UTC))
    )
    db.commit()
    nxt = claim(repo)
    db.commit()
    # Libre el hueco, la v2 (llegó antes) pasa por delante del último proyecto.
    assert nxt and str(nxt.execution_id) == second.json()["execution_id"]
    assert claim(repo) is None
    db.commit()


def test_queued_uploads_are_processed_in_order(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    names = ["v1.csv", "v2.csv", "v3.csv"]
    for name in names:
        assert upload(client, headers, project_id, name=name).status_code == 202
    while process(db, objects):
        pass
    items = client.get(f"/api/v1/projects/{project_id}/versions").json()["items"]
    assert {item["state"] for item in items} == {"succeeded"}
    assert sorted(item["number"] for item in items) == [1, 2, 3]
