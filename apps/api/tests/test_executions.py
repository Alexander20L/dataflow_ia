import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import CSV, account, process, project, upload

from dataflow.bootstrap.services import (
    WORKER_KINDS,
    make_analysis,
    make_datasets,
    make_executions,
    make_ingestion,
    make_runner,
)
from dataflow.modules.datasets.infrastructure import (
    DatasetDefaultRecord,
    ImportBindingRecord,
    ObjectRecord,
    VersionRecord,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.contracts import Artifact, ArtifactOutput, Lease
from dataflow.modules.executions.infrastructure import (
    ArtifactRecord,
    ExecutionRecord,
    PlanRecord,
)
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.canonical import canonical, digest
from dataflow.platform.errors import ApplicationError


def test_multiple_plans_same_table_preserve_legacy_baseline(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    assert process(db, objects)
    path = f"/api/v1/versions/{version['id']}"
    baseline = client.get(path + "/diagnostic").json()
    original = client.get(path + "/original").content
    representation = client.get(path + "/representations").json()[0]
    assert "key" not in representation and "object_key" not in representation
    runs = []
    for kind in ["profile_quality", "quality_only"]:
        key = str(uuid4())
        body = {
            "table_artifact_id": representation["id"],
            "table_sha256": representation["sha256"],
            "analysis_kind": kind,
        }
        response = client.post(
            path + "/analyses", json=body, headers={**headers, "Idempotency-Key": key}
        )
        assert response.status_code == 202, response.text
        run = response.json()
        assert run["plan"]["content"]["input"]["artifact_id"] == representation["id"]
        assert run["plan"]["content"]["input"]["version_content_sha256"] == version["sha256"]
        assert run["plan"]["content"]["objective"] is None
        assert digest("plan", run["plan"]["content"]) == run["plan"]["content_sha256"]
        retry = client.post(
            path + "/analyses", json=body, headers={**headers, "Idempotency-Key": key}
        )
        assert retry.json()["id"] == run["id"]
        conflict = client.post(
            path + "/analyses",
            json={**body, "table_sha256": "0" * 64},
            headers={**headers, "Idempotency-Key": key},
        )
        assert conflict.status_code == 409
        runs.append(run)
    assert runs[0]["plan"]["content_sha256"] != runs[1]["plan"]["content_sha256"]
    assert process(db, objects) and process(db, objects)
    for run in runs:
        detail = client.get(f"/api/v1/executions/{run['id']}").json()
        assert detail["state"] == "succeeded" and detail["reproducibility"] == "complete"
        history = detail["attempt_history"]
        assert len(history) == 1 and history[0]["state"] == "succeeded"
        assert history[0]["environment"]["config_sha256"] == digest(
            "config", run["plan"]["content"]["config"]
        )
        assert history[0]["environment"]["dependency_lock_sha256"]
        assert "fencing_token" not in history[0]
        # Los análisis de tabla usan quality.evaluate@1: misma calidad técnica que la carga, sin
        # los hallazgos analíticos de quality.evaluate@3 (Fase 14).
        technical = {**baseline["quality"], "analytical": None}
        assert client.get(f"/api/v1/executions/{run['id']}/quality").json() == technical
    first_outputs = client.get(f"/api/v1/executions/{runs[0]['id']}/artifacts").json()
    second_outputs = client.get(f"/api/v1/executions/{runs[1]['id']}/artifacts").json()
    assert {a["kind"] for a in first_outputs} == {"profile", "quality"}
    assert {a["kind"] for a in second_outputs} == {"quality"}
    assert set(a["id"] for a in first_outputs).isdisjoint(a["id"] for a in second_outputs)
    assert client.get(f"/api/v1/executions/{runs[1]['id']}/profile").status_code == 404
    assert client.get(path + "/diagnostic").json() == baseline
    assert client.get(path + "/original").content == original
    assert (
        client.get(f"/api/v1/projects/{project_id}/versions").json()["items"][0]["execution_id"]
        == version["execution_id"]
    )
    assert client.get("/api/v1/datasets/summary").json()["versions"] == 1
    assert db.scalar(select(func.count()).select_from(VersionRecord)) == 1


def test_analysis_permissions_hash_and_archive(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    assert process(db, objects)
    path = f"/api/v1/versions/{version['id']}"
    table = client.get(path + "/representations").json()[0]
    body = {"table_artifact_id": table["id"], "table_sha256": table["sha256"]}
    assert client.post(path + "/analyses", json=body, headers=headers).status_code == 422
    request_headers = {**headers, "Idempotency-Key": str(uuid4())}
    assert (
        client.post(
            path + "/analyses", json={**body, "table_sha256": "0" * 64}, headers=request_headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/archive", json={"expected_revision": 1}, headers=headers
        ).status_code
        == 200
    )
    assert client.post(path + "/analyses", json=body, headers=request_headers).status_code == 409
    other = account(client)
    for suffix in ["executions", "representations"]:
        assert client.get(path + "/" + suffix).status_code == 404
    assert (
        client.post(
            path + "/analyses", json=body, headers={**other, "Idempotency-Key": str(uuid4())}
        ).status_code
        == 404
    )
    for suffix in ["", "/artifacts", "/quality", "/profile"]:
        assert (
            client.get(f"/api/v1/executions/{version['execution_id']}" + suffix).status_code == 404
        )


def test_register_source_and_enqueue_rollback_together(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = account(client)
    project_id = project(client, headers)
    owner = UUID(client.get("/api/v1/auth/me").json()["user"]["id"])
    service = make_ingestion(db, objects)

    def reject(*args, **kwargs):
        raise ApplicationError("TEST_QUEUE_REJECT", "Fallo de prueba.", 503)

    monkeypatch.setattr(service.executions, "enqueue", reject)
    with pytest.raises(ApplicationError, match="Fallo de prueba"):
        service.submit(owner, UUID(project_id), "test.csv", CSV, ",", uuid4(), str(uuid4()))
    for model in [VersionRecord, ObjectRecord, ExecutionRecord, PlanRecord, ImportBindingRecord]:
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_publication_rollback_includes_baseline_and_objects(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    version = upload(client, headers, project(client, headers)).json()
    runner = make_runner(db, objects)
    # Inyectar un fallo después de registrar artefactos y modificar el baseline.
    original = runner.publisher

    class FailingHook:
        def prepare(self, lease: Lease, outputs: list[ArtifactOutput]) -> None:
            original.prepare(lease, outputs)

        def published(self, lease: Lease, artifacts: list[Artifact]) -> None:
            original.published(lease, artifacts)
            raise ApplicationError("PUBLICATION_ABORTED", "Publicación rechazada en prueba.", 409)

    runner.publisher = FailingHook()
    assert runner.run_once()
    assert db.scalar(select(func.count()).select_from(ArtifactRecord)) == 0
    assert db.scalar(select(func.count()).select_from(DatasetDefaultRecord)) == 0
    assert db.scalar(select(func.count()).select_from(ObjectRecord)) == 1  # sólo el original
    binding = db.get(ImportBindingRecord, UUID(version["id"]))
    assert binding and binding.table_artifact_id is None
    assert (
        client.get(f"/api/v1/projects/{version['project_id']}/versions").json()["items"][0]["state"]
        == "failed"
    )


def test_python_canonical_matches_phase_one_examples() -> None:
    data = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/analysis/v1/examples.json").read_text(
            encoding="utf-8"
        )
    )
    for key, domain in [("plans", "plan"), ("semantic_contracts", "semantic")]:
        for value in data[key]:
            assert digest(domain, value["content"]) == value["content_sha256"]
    assert canonical({"z": [None, "001"], "b": "á", "a": 1}) == '{"a":1,"b":"á","z":[null,"001"]}'
    for value in [0.1, float("inf"), {"a": object()}]:
        with pytest.raises(ValueError):
            canonical(value)


def test_two_workers_claim_and_publish_independent_runs(
    committed_engine: Engine, tmp_path: Path
) -> None:
    store = LocalObjects(tmp_path / "concurrent_objects")
    owner = uuid4()
    with Session(committed_engine, expire_on_commit=False) as db:
        db.add(
            UserRecord(
                id=owner,
                name="Concurrency",
                email="concurrency@example.com",
                password_hash="not-a-login",
            )
        )
        db.commit()
        project_record = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
            owner, "Concurrency CSV", "", None
        )
        baseline = make_ingestion(db, store).submit(
            owner, project_record.id, "test.csv", CSV, ",", uuid4(), str(uuid4())
        )
        assert make_runner(db, store).run_once()
        table = next(
            a
            for a in make_executions(db).artifacts(owner, baseline.execution_id)
            if a.kind == "table"
        )
        runs = [
            make_analysis(db, store).submit(
                owner, baseline.id, table.id, table.content.sha256, kind, uuid4(), str(uuid4())
            )
            for kind in ["quality_only", "profile_quality"]
        ]
    barrier = Barrier(2)

    def worker() -> bool:
        with Session(committed_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            # La investigación de la carga (Fase 16) queda en cola: aquí compiten por los análisis.
            return make_runner(
                db,
                store,
                kinds=WORKER_KINDS
                - {"investigation", "comprehension", "exploration", "dashboard", "inspection"},
            ).run_once()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert all(future.result(timeout=90) for future in futures)
    with Session(committed_engine, expire_on_commit=False) as db:
        service = make_executions(db)
        for run in runs:
            assert service.get(owner, run.id).state == "succeeded"
            assert len(service.attempts(owner, run.id)) == 1
        assert make_datasets(db).binding(owner, baseline.id).execution_id == baseline.execution_id
        assert db.scalar(select(func.count()).select_from(VersionRecord)) == 1
        # Ahora dos workers compiten por UN único trabajo: sólo uno debe adquirirlo.
        last = make_analysis(db, store).submit(
            owner,
            baseline.id,
            table.id,
            table.content.sha256,
            "quality_only",
            uuid4(),
            str(uuid4()),
        )
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert sorted(future.result(timeout=90) for future in futures) == [False, True]
    with Session(committed_engine) as db:
        assert make_executions(db).get(owner, last.id).attempts == 1
        assert len(make_executions(db).artifacts(owner, last.id)) == 1
