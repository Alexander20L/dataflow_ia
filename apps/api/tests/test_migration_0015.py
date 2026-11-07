from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import TABLES_AFTER_0012
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.pipeline_access import start_pipeline
from dataflow.bootstrap.services import make_automation, make_ingestion
from dataflow.modules.automation.contracts import PolicyContent
from dataflow.modules.automation.pipeline_infrastructure import AutomationRunRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base

TABLES_UP_TO_0015 = {
    "analysis_sessions",
    "analysis_session_input_revisions",
    "automation_policy_families",
    "automation_policy_revisions",
    "automation_policy_save_requests",
    "automation_approvals",
    "automation_runs",
    "automation_step_attempts",
}


def exists_at_0015(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in TABLES_AFTER_0012 - TABLES_UP_TO_0015


def test_0015_is_additive_and_step_attempts_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "run_migration_" + uuid4().hex
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
        command.upgrade(config, "0015")
        command.downgrade(config, "0014")  # sin pipelines: ida y vuelta
        command.upgrade(config, "0015")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0015}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="run-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Run migration", "", None
            )
            make_automation(db, objects).save(
                owner, project.id, 0, PolicyContent(enabled=True), uuid4(), "c"
            )
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", b"id,importe\n001,10\n", ",", uuid4(), "c"
            )
            start_pipeline(db, owner, project.id, version.id)
            start_pipeline(db, owner, project.id, version.id)  # idempotente por versión
            db.commit()
            assert db.scalar(select(func.count()).select_from(AutomationRunRecord)) == 1
            for statement in [
                "UPDATE automation_step_attempts SET sequence = 9",
                "DELETE FROM automation_step_attempts",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0014")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
