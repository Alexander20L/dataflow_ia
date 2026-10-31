from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.app import app
from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.dependencies import object_store
from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.infrastructure import (
    DatasetRecord,
    ImportBindingRecord,
    VersionRecord,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import (
    AttemptRecord,
    ExecutionRecord,
)
from dataflow.modules.identity.application import IdentityService
from dataflow.modules.identity.infrastructure import ArgonPasswords, SQLIdentityRepository
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.legacy_records import (
    LegacyArtifactRecord,
    LegacyExecutionRecord,
    LegacyVersionRecord,
)
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import get_db
from dataflow.platform.errors import ApplicationError
from dataflow.platform.runtime import RuntimeTransition

CSV = b"id,importe\r\n001,10.50\r\n002,\r\n"


@pytest.fixture
def migration_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Config]]:
    original = get_settings().database_url
    admin = create_engine(original, connect_args={"connect_timeout": 5})
    schema = "migration_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    target = make_url(original).update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setattr(
        get_settings(), "database_url", target.render_as_string(hide_password=False)
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(target, connect_args={"connect_timeout": 5})
    try:
        command.upgrade(config, "0002")
        yield engine, config
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def seed_legacy(engine: Engine, objects: LocalObjects):
    with Session(engine, expire_on_commit=False) as db:
        issued = IdentityService(SQLIdentityRepository(db), ArgonPasswords(), 12).authenticate(
            "migration@example.com", "Migration-password-123", "test", "Migration"
        )
        owner = issued.identity.user.id
        project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
            owner, "Proyecto previo", "", None
        )
        dataset = DatasetRecord(id=uuid4(), project_id=project.id, owner_id=owner)
        db.add(dataset)
        db.flush()
        versions, runs = [], []
        now = datetime.now(UTC)
        for number, state in enumerate(["succeeded", "failed", "cancelled"], 1):
            version_id = uuid4()
            reference = objects.put(f"originals/{owner}/{version_id}/legacy.csv", CSV)
            version = LegacyVersionRecord(
                id=version_id,
                dataset_id=dataset.id,
                number=number,
                file_name=f"legacy_{number}.csv",
                original_key=reference.key,
                sha256=reference.sha256,
                byte_size=reference.byte_size,
                created_at=now,
            )
            db.add(version)
            db.flush()
            run = LegacyExecutionRecord(
                id=uuid4(),
                version_id=version.id,
                project_id=project.id,
                owner_id=owner,
                request_key=uuid4(),
                separator=",",
                engine_version="csv-ingestion-1",
                state=state,
                attempts=2,
                row_count=2 if state == "succeeded" else None,
                column_count=2 if state == "succeeded" else None,
                error_code="CSV_SHAPE" if state == "failed" else None,
                error_message="Error histórico" if state == "failed" else None,
                correlation_id=str(uuid4()),
                created_at=now,
                updated_at=now,
            )
            db.add(run)
            db.flush()
            versions.append(version)
            runs.append(run)
        result = IsolatedAnalyzer(objects.root, 45, 100000, 128).analyze(CSV, ",")
        parquet = objects.put("artifacts/legacy/data.parquet", result.parquet)
        diagnostic = objects.put(
            "artifacts/legacy/diagnostic.json", result.diagnostic.model_dump_json().encode()
        )
        for kind, reference in [("parquet", parquet), ("diagnostic", diagnostic)]:
            db.add(
                LegacyArtifactRecord(
                    id=uuid4(),
                    version_id=versions[0].id,
                    execution_id=runs[0].id,
                    kind=kind,
                    object_key=reference.key,
                    sha256=reference.sha256,
                    byte_size=reference.byte_size,
                )
            )
        db.commit()
        return issued, project.id, versions, runs, result.diagnostic


def test_migration_preserves_history_endpoints_and_allows_independent_runs(
    migration_engine, tmp_path: Path
) -> None:
    engine, config = migration_engine
    objects = LocalObjects(tmp_path / "objects")
    issued, project_id, versions, legacy_runs, diagnostic = seed_legacy(engine, objects)
    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as db:
        report = cutover(db, objects, apply=False)
        assert report["legacy_versions"] == 3 and report["legacy_artifacts"] == 2
        assert db.scalar(select(func.count()).select_from(VersionRecord)) == 0
        first = cutover(db, objects, apply=True)
        second = cutover(db, objects, apply=True)
        assert first == second
        assert db.scalar(select(func.count()).select_from(AttemptRecord)) == 0
        for old in legacy_runs:
            new = db.get(ExecutionRecord, old.id)
            assert new and new.state == old.state and new.attempt_count == 2
            assert (
                new.plan_id is None
                and new.reproducibility == "legacy_partial"
                and new.finished_at is None
            )
        assert db.get(ImportBindingRecord, versions[0].id).execution_id == legacy_runs[0].id
    previous = dict(app.dependency_overrides)

    def sessions():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    app.dependency_overrides[object_store] = lambda: objects
    try:
        with TestClient(app, headers={"Origin": "http://localhost:3002"}) as client:
            client.cookies.set("dataflow_session", issued.token, path="/api/v1")
            headers = {"x-csrf-token": issued.identity.csrf_token}
            root = f"/api/v1/versions/{versions[0].id}"
            assert client.get(root + "/original").content == CSV
            assert client.get(root + "/diagnostic").json() == diagnostic.model_dump(mode="json")
            page = client.get(f"/api/v1/projects/{project_id}/versions").json()
            assert page["total"] == 3
            assert {v["state"] for v in page["items"]} == {"succeeded", "failed", "cancelled"}
            old_key = str(legacy_runs[0].request_key)
            retry = client.post(
                f"/api/v1/projects/{project_id}/imports",
                params={"file_name": versions[0].file_name, "separator": ","},
                content=CSV,
                headers={**headers, "Content-Type": "text/csv", "Idempotency-Key": old_key},
            )
            assert retry.status_code == 202 and retry.json()["execution_id"] == str(
                legacy_runs[0].id
            )
            representation = client.get(root + "/representations").json()[0]
            run_ids = []
            for kind in ["profile_quality", "quality_only"]:
                response = client.post(
                    root + "/analyses",
                    json={
                        "table_artifact_id": representation["id"],
                        "table_sha256": representation["sha256"],
                        "analysis_kind": kind,
                    },
                    headers={**headers, "Idempotency-Key": str(uuid4())},
                )
                assert response.status_code == 202, response.text
                run_ids.append(response.json()["id"])
            for _ in range(2):
                with Session(engine, expire_on_commit=False) as db:
                    assert make_runner(db, objects).run_once()
            for id in run_ids:
                assert client.get(f"/api/v1/executions/{id}").json()["state"] == "succeeded"
            assert client.get(root + "/diagnostic").json() == diagnostic.model_dump(mode="json")
            assert client.get("/api/v1/datasets/summary").json()["versions"] == 3
        with Session(engine) as db:
            assert cutover(db, objects, apply=True) == first
            with pytest.raises(IntegrityError, match="LEGACY_WRITE_FORBIDDEN"):
                db.execute(text("UPDATE dataset_versions SET file_name=file_name"))
            db.rollback()
            with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                db.execute(text("UPDATE dataset_version_records SET file_name=file_name"))
            db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0002")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_migration_refuses_active_jobs_and_rolls_back_missing_objects(
    migration_engine, tmp_path: Path
) -> None:
    engine, config = migration_engine
    objects = LocalObjects(tmp_path / "objects")
    _, _, versions, runs, _ = seed_legacy(engine, objects)
    command.upgrade(config, "head")
    with Session(engine) as db:
        old = db.get(LegacyExecutionRecord, runs[2].id)
        old.state = "queued"
        db.commit()
        with pytest.raises(ApplicationError, match="Deja terminar"):
            cutover(db, objects, apply=True)
        assert db.get(RuntimeTransition, 1).state == "expanded"
        old = db.get(LegacyExecutionRecord, runs[2].id)
        old.state = "cancelled"
        db.commit()
        objects.path(versions[0].original_key).write_bytes(b"corrupt")
        with pytest.raises(ApplicationError, match="tamaño"):
            cutover(db, objects, apply=True)
        assert db.scalar(select(func.count()).select_from(VersionRecord)) == 0
        assert db.get(RuntimeTransition, 1).state == "expanded"
        objects.path(versions[0].original_key).write_bytes(CSV)

        class InterruptedObjects(LocalObjects):
            calls = 0

            def read(self, reference):
                self.calls += 1
                if self.calls == 2:
                    raise OSError("Interrupción simulada tras copiar el primer objeto")
                return super().read(reference)

        with pytest.raises(OSError, match="Interrupción"):
            cutover(db, InterruptedObjects(objects.root), apply=True)
        assert db.scalar(select(func.count()).select_from(VersionRecord)) == 0
        assert db.get(RuntimeTransition, 1).state == "expanded"
        assert cutover(db, objects, apply=True)["legacy_versions"] == 3
