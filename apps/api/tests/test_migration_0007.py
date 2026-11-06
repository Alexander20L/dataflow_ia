from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.services import make_executions, make_ingestion, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ErrorDetailRecord
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0007_is_additive_and_error_details_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "error_details_migration_" + uuid4().hex
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
        command.upgrade(config, "0006")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="error-details-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Error details migration", "", None
            )
            content = b"id,importe\n001, 10\n002,\n"
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", content, ",", uuid4(), str(uuid4())
            )
            assert make_runner(db, objects).run_once()
            executions = make_executions(db)
            before = {
                run.id: (
                    run,
                    executions.artifacts(owner, run.id),
                    executions.attempts(owner, run.id),
                )
                for run in executions.for_version(owner, version.id)
            }
            diagnostic = make_ingestion(db, objects).diagnostic(owner, version.id)

        command.upgrade(config, "0007")
        command.downgrade(config, "0006")  # sin detalles: ida y vuelta
        command.upgrade(config, "0007")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0007}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            executions = make_executions(db)
            after = {
                run.id: (
                    run,
                    executions.artifacts(owner, run.id),
                    executions.attempts(owner, run.id),
                )
                for run in executions.for_version(owner, version.id)
            }
            assert after == before
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == diagnostic
            assert db.scalar(select(func.count()).select_from(ErrorDetailRecord)) == 0
            # Los datos existentes no tienen detalle: la lectura no inventa ninguno.
            assert executions.error_details(owner, version.execution_id) is None

            attempt = UUID(executions.attempts(owner, version.execution_id)[0]["id"])
            db.add(
                ErrorDetailRecord(
                    attempt_id=attempt,
                    execution_id=version.execution_id,
                    code="CONVERSION_FAILED",
                    details={"total": 1, "samples": []},
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()
            assert executions.error_details(owner, version.execution_id) == (
                "CONVERSION_FAILED",
                {"total": 1, "samples": []},
            )
            with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                db.execute(text("UPDATE execution_error_details SET code = 'X'"))
            db.rollback()
            with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                db.execute(text("DELETE FROM execution_error_details"))
            db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0006")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {
    "quality_ruleset_families",
    "quality_ruleset_revisions",
    "quality_ruleset_save_requests",
    "analytics_metric_families",
    "analytics_metric_revisions",
    "analytics_metric_save_requests",
    "dashboard_families",
    "dashboard_revisions",
    "dashboard_save_requests",
    "report_families",
    "report_revisions",
    "report_save_requests",
    "report_renders",
    "copilot_conversations",
    "copilot_ai_calls",
    "copilot_messages",
    "copilot_action_links",
    "copilot_requests",
}


def exists_at_0007(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES
