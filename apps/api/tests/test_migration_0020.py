"""Migración 0020 (Fase 19): valoraciones de relaciones, aditiva, inmutable y sólo de añadir."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.comprehension.infrastructure import SQLFeedbackRepository
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0020_is_additive_and_feedback_is_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "feedback_migration_" + uuid4().hex
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
        command.upgrade(config, "0019")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="feedback-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Feedback migration", "", None
            )
            content = objects.put(f"originals/{owner}/x/a.csv", b"a,b\n1,2\n")
            version = SQLDatasetRepository(db).register(
                owner, project.id, uuid4(), "a.csv", content
            )
            db.commit()

        command.upgrade(config, "0020")
        command.downgrade(config, "0019")  # sin valoraciones: ida y vuelta
        assert "comprehension_feedback" not in inspect(engine).get_table_names()
        command.upgrade(config, "0020")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            repository = SQLFeedbackRepository(db)
            repository.add(owner, project.id, version.id, "a.csv|{}", "association:a|b", "relevant")
            repository.add(
                owner, project.id, version.id, "a.csv|{}", "association:a|b", "not_relevant"
            )
            db.commit()
            # Vale la última valoración; el historial se conserva.
            assert repository.for_source(owner, project.id, "a.csv|{}") == {
                "association:a|b": "not_relevant"
            }
            assert [i.verdict for i in repository.for_version(owner, version.id)] == [
                "not_relevant"
            ]
            for statement in [
                "UPDATE comprehension_feedback SET verdict = 'relevant'",
                "DELETE FROM comprehension_feedback",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0019")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
