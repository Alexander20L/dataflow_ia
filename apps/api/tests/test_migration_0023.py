"""Migración 0023 (Fase 23): textos nulos declarados y decisión sobre datos personales, aditiva,
inmutable y sólo de añadir (completa cada corrección del diccionario)."""

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


def test_0023_is_additive_and_annotation_details_are_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "annotation_details_migration_" + uuid4().hex
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
        command.upgrade(config, "0022")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="annotation-details-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Annotation details migration", "", None
            )
            content = objects.put(f"originals/{owner}/x/a.csv", b"a,b\n1,2\n")
            version = SQLDatasetRepository(db).register(
                owner, project.id, uuid4(), "a.csv", content
            )
            db.commit()
            # Una corrección de la Fase 22 (sin detalle): sigue valiendo tras la migración.
            db.execute(
                text(
                    "INSERT INTO column_annotations (id, owner_id, project_id, version_id, "
                    "source_key, column_name, role, nature, time_format, notes, confirmed, "
                    "created_at) VALUES (:id, :owner, :project, :version, 'a.csv|{}', 'b', "
                    "'dimension', NULL, NULL, NULL, false, now())"
                ),
                {"id": uuid4(), "owner": owner, "project": project.id, "version": version.id},
            )
            db.commit()

        command.upgrade(config, "0023")
        command.downgrade(config, "0022")  # sin detalles: ida y vuelta
        assert "column_annotation_details" not in inspect(engine).get_table_names()
        command.upgrade(config, "0023")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            repository = SQLColumnAnnotations(db)
            source = "a.csv|{}"
            column = uuid4()
            assert repository.for_source(owner, project.id, source)["b"].role == "dimension"
            repository.add(
                owner,
                project.id,
                version.id,
                source,
                "a",
                AnnotationRequest(column_id=column, null_tokens=["N/A", "N/A", "-"]),
            )
            repository.add(
                owner,
                project.id,
                version.id,
                source,
                "c",
                AnnotationRequest(column_id=column, personal=False),
            )
            db.commit()
            latest = repository.for_source(owner, project.id, source)
            # Los textos repetidos se guardan una vez; decidir sobre datos personales cuenta
            # como corrección aunque el resto esté vacío.
            assert latest["a"].null_tokens == ["N/A", "-"] and latest["a"].personal is None
            assert latest["c"].personal is False and latest["c"].null_tokens == []
            repository.add(
                owner, project.id, version.id, source, "c", AnnotationRequest(column_id=column)
            )
            db.commit()
            assert "c" not in repository.for_source(owner, project.id, source)
            for statement in [
                "UPDATE column_annotation_details SET personal = true",
                "DELETE FROM column_annotation_details",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0022")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
