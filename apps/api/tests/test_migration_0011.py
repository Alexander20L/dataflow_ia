from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import TABLES_AFTER_0012, insert_report
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.services import make_executions, make_ingestion, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.reports.infrastructure import ReportRenderRecord, ReportRevisionRecord
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0011_is_additive_and_report_revisions_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "reports_migration_" + uuid4().hex
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
        command.upgrade(config, "0010")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="reports-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Reports migration", "", None
            )
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", b"id,importe\n001,10\n", ",", uuid4(), "c"
            )
            assert make_runner(db, objects).run_once()
            executions = make_executions(db)
            before = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            diagnostic = make_ingestion(db, objects).diagnostic(owner, version.id)

        command.upgrade(config, "0011")
        command.downgrade(config, "0010")  # sin informes: ida y vuelta
        command.upgrade(config, "0011")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0011}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            executions = make_executions(db)
            after = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            assert after == before
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == diagnostic
            assert db.scalar(select(func.count()).select_from(ReportRevisionRecord)) == 0

            revision = insert_report(db, owner, project.id)
            family = db.get(ReportRevisionRecord, revision)
            assert family is not None
            db.add(
                ReportRenderRecord(
                    execution_id=next(iter(after)),
                    owner_id=owner,
                    family_id=family.family_id,
                    revision_id=revision,
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()
            for statement in [
                "UPDATE report_revisions SET content_sha256 = 'x'",
                "DELETE FROM report_revisions",
                "DELETE FROM report_save_requests",
                "DELETE FROM report_renders",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0010")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {
    "copilot_conversations",
    "copilot_ai_calls",
    "copilot_messages",
    "copilot_action_links",
    "copilot_requests",
    "copilot_text_audits",
}


def exists_at_0011(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES | TABLES_AFTER_0012
