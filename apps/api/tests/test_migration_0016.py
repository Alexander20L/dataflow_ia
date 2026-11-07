from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import TABLES_AFTER_0012
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.services import make_templates
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.templates.contracts import MappingContent
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base

TABLES_UP_TO_0016 = {
    "analysis_sessions",
    "analysis_session_input_revisions",
    "automation_policy_families",
    "automation_policy_revisions",
    "automation_policy_save_requests",
    "automation_approvals",
    "automation_runs",
    "automation_step_attempts",
    "template_mapping_families",
    "template_mapping_revisions",
    "template_mapping_save_requests",
    "automation_run_interpretations",
}


def exists_at_0016(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in TABLES_AFTER_0012 - TABLES_UP_TO_0016


def test_0016_is_additive_and_mapping_revisions_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "mapping_migration_" + uuid4().hex
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
        command.upgrade(config, "0016")
        command.downgrade(config, "0015")  # sin mapeos: ida y vuelta
        command.upgrade(config, "0016")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0016}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="mapping-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Mapping migration", "", None
            )
            saved = make_templates(db, objects).save(
                owner, project.id, 0, MappingContent(template="generic@1"), uuid4(), "c"
            )
            assert saved.revision == 1
            for statement in [
                "UPDATE template_mapping_revisions SET revision = 9",
                "DELETE FROM template_mapping_revisions",
                "DELETE FROM template_mapping_save_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0015")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
