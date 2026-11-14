"""Migración 0028 (Fase 29): objetivo del análisis elegido por el usuario, aditiva, inmutable y
sólo de añadir; vale el último de la misma fuente y uno sin columna vuelve al propuesto."""

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
from dataflow.modules.comprehension.contracts import TargetChoice
from dataflow.modules.comprehension.infrastructure import SQLTargetRepository
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0028_is_additive_and_targets_are_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "analysis_targets_migration_" + uuid4().hex
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
        command.upgrade(config, "0027")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="analysis-targets-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Analysis targets migration", "", None
            )
            content = objects.put(f"originals/{owner}/x/a.csv", b"a,b\n1,2\n")
            version = SQLDatasetRepository(db).register(
                owner, project.id, uuid4(), "a.csv", content
            )
            db.commit()
            project_id, version_id = project.id, version.id

        command.upgrade(config, "0028")
        command.downgrade(config, "0027")  # sin objetivos elegidos: ida y vuelta
        assert "analysis_targets" not in inspect(engine).get_table_names()
        command.upgrade(config, "0028")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            targets = SQLTargetRepository(db)
            assert targets.for_source(owner, project_id, "a.csv") is None
            targets.add(owner, project_id, version_id, "a.csv", "activo", "No")
            db.commit()
            assert targets.for_source(owner, project_id, "a.csv") == TargetChoice(
                column="activo", value="No"
            )
            assert targets.for_source(owner, project_id, "b.csv") is None
            # Uno sin columna vuelve al propuesto (y no guarda valor).
            targets.add(owner, project_id, version_id, "a.csv", None, "x")
            db.commit()
            assert targets.for_source(owner, project_id, "a.csv") is None
            for statement in [
                "UPDATE analysis_targets SET column_name = 'otra'",
                "DELETE FROM analysis_targets",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0027")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
