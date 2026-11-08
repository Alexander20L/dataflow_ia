"""Migración 0019 (Fase 13, ADR-026): retira las tablas del pipeline por política."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import RETIRED_IN_0019
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0019_drops_the_policy_pipeline_and_keeps_everything_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "retire_migration_" + uuid4().hex
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
        command.upgrade(config, "0018")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="retire-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Retire migration", "", None
            )
            now = datetime.now(UTC)
            # Un dato del pipeline retirado: la migración lo elimina (decisión de la Fase 13).
            db.execute(
                text(
                    "INSERT INTO analysis_sessions "
                    "(id, project_id, owner_id, revision, head_input_id, created_at, updated_at) "
                    "VALUES (:id, :project, :owner, 0, NULL, :now, :now)"
                ),
                {"id": uuid4(), "project": project.id, "owner": owner, "now": now},
            )
            db.commit()

        command.upgrade(config, "0019")
        tables = set(inspect(engine).get_table_names())
        assert not tables & RETIRED_IN_0019
        assert {"projects", "cleaning_approvals", "dashboard_revisions"} <= tables
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={})
            assert compare_metadata(context, Base.metadata) == []
        with Session(engine) as db:
            assert ProjectService(SQLProjectRepository(db, str(uuid4()))).get(owner, project.id)

        # El downgrade recrea las tablas vacías: los datos borrados no vuelven.
        command.downgrade(config, "0018")
        assert RETIRED_IN_0019 <= set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM analysis_sessions")) == 0
        command.upgrade(config, "0019")
        assert not set(inspect(engine).get_table_names()) & RETIRED_IN_0019
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
