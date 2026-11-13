"""Migración 0026 (Fase 25): peticiones de pausa o cancelación de una investigación, aditiva,
inmutable y sólo de añadir."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import modelled_at_0026
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.exploration.infrastructure import SQLInvestigationControls
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0026_is_additive_and_investigation_controls_are_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "investigation_controls_migration_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(original_url).update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setattr(get_settings(), "database_url", url.render_as_string(hide_password=False))
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    objects = LocalObjects(tmp_path / "migration_objects")
    try:
        command.upgrade(config, "0003")
        with Session(engine, expire_on_commit=False) as db:
            cutover(db, objects, apply=True)
        command.upgrade(config, "0025")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="investigation-controls-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Investigation controls migration", "", None
            )
            content = objects.put(f"originals/{owner}/x/a.csv", b"a,b\n1,2\n")
            version = SQLDatasetRepository(db).register(
                owner, project.id, uuid4(), "a.csv", content
            )
            now = datetime.now(UTC)
            run = ExecutionRecord(
                id=uuid4(),
                version_id=version.id,
                project_id=project.id,
                owner_id=owner,
                plan_id=None,
                kind="exploration",
                request_key=uuid4(),
                request_fingerprint="f" * 64,
                state="queued",
                attempt_count=0,
                reproducibility="complete",
                correlation_id=str(uuid4()),
                created_at=now,
                updated_at=now,
            )
            db.add(run)
            db.commit()

        command.upgrade(config, "0026")
        command.downgrade(config, "0025")  # sin peticiones: ida y vuelta
        assert "investigation_controls" not in inspect(engine).get_table_names()
        command.upgrade(config, "0026")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": modelled_at_0026}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            controls = SQLInvestigationControls(db)
            assert controls.requested(run.id) is None
            controls.add(owner, run.id, "pause")
            controls.add(owner, run.id, "cancel")
            db.commit()
            # Vale la primera petición.
            assert controls.requested(run.id) == "pause"
            assert controls.for_executions([run.id]) == {run.id: "pause"}
            for statement in [
                "UPDATE investigation_controls SET action = 'cancel'",
                "DELETE FROM investigation_controls",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
            with pytest.raises(IntegrityError):
                db.execute(
                    text(
                        "INSERT INTO investigation_controls VALUES "
                        "(:id, :owner, :run, 'resume', now())"
                    ),
                    {"id": uuid4(), "owner": owner, "run": run.id},
                )
            db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0025")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
