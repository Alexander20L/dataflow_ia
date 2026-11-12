"""Migración 0022 (Fase 22): correcciones del diccionario, aditiva, inmutable y sólo de añadir."""

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
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.inspection.contracts import AnnotationRequest
from dataflow.modules.inspection.infrastructure import SQLColumnAnnotations
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0022_is_additive_and_column_annotations_are_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "column_annotations_migration_" + uuid4().hex
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
        command.upgrade(config, "0021")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="column-annotations-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Column annotations migration", "", None
            )
            content = objects.put(f"originals/{owner}/x/a.csv", b"a,b\n1,2\n")
            version = SQLDatasetRepository(db).register(
                owner, project.id, uuid4(), "a.csv", content
            )
            db.commit()

        command.upgrade(config, "0022")
        command.downgrade(config, "0021")  # sin correcciones: ida y vuelta
        assert "column_annotations" not in inspect(engine).get_table_names()
        command.upgrade(config, "0022")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            repository = SQLColumnAnnotations(db)
            source = "a.csv|{}"
            column = uuid4()
            for request in [
                AnnotationRequest(column_id=column, role="dimension"),
                AnnotationRequest(column_id=column, role="identifier", notes="clave"),
                AnnotationRequest(column_id=column, confirmed=True),
            ]:
                repository.add(owner, project.id, version.id, source, "a", request)
            repository.add(
                owner, project.id, version.id, source, "b", AnnotationRequest(column_id=column)
            )
            db.commit()
            # Vale la última corrección; una vacía devuelve la columna a la automática.
            latest = repository.for_source(owner, project.id, source)
            assert list(latest) == ["a"] and latest["a"].confirmed and latest["a"].role is None
            assert repository.for_source(owner, project.id, "otro.csv|{}") == {}
            for statement in [
                "UPDATE column_annotations SET notes = 'x'",
                "DELETE FROM column_annotations",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0021")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
