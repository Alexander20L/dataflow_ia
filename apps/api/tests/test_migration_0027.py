"""Migración 0027 (Fase 26): versiones personalizadas del dashboard, aditiva, inmutable y sólo de
añadir; la revisión esperada evita pisar una edición ajena."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import modelled_at_0027
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.curation.public import (
    CustomSection,
    CustomWidget,
    SQLDashboardCustomizations,
)
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


def test_0027_is_additive_and_dashboard_customizations_are_revisions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "dashboard_customizations_migration_" + uuid4().hex
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
        command.upgrade(config, "0026")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="dashboard-customizations-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Dashboard customizations migration", "", None
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
                kind="dashboard",
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
            project_id, version_id, run_id = project.id, version.id, run.id

        command.upgrade(config, "0027")
        command.downgrade(config, "0026")  # sin versiones personalizadas: ida y vuelta
        assert "dashboard_customizations" not in inspect(engine).get_table_names()
        command.upgrade(config, "0027")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": modelled_at_0027}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            custom = SQLDashboardCustomizations(db)
            assert custom.latest(owner, version_id) is None
            sections = [
                CustomSection(title="Lo mío", widgets=[CustomWidget(item="x", type="table")])
            ]
            first = custom.add(owner, project_id, version_id, run_id, 0, sections)
            db.commit()
            assert first.revision == 1
            # Sin cambios no hay revisión nueva.
            assert custom.add(owner, project_id, version_id, run_id, 1, sections).revision == 1
            # Una edición sobre una revisión antigua no pisa la vigente.
            with pytest.raises(ApplicationError, match="cambió"):
                custom.add(owner, project_id, version_id, run_id, 0, sections)
            renamed = [sections[0].model_copy(update={"title": "Otro"})]
            assert custom.add(owner, project_id, version_id, run_id, 1, renamed).revision == 2
            db.commit()
            latest = custom.latest(owner, version_id)
            assert latest is not None and latest.sections[0].title == "Otro"
            for statement in [
                "UPDATE dashboard_customizations SET revision = 9",
                "DELETE FROM dashboard_customizations",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0026")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
