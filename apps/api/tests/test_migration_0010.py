from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
from dataflow.modules.dashboards.application import content_sha256
from dataflow.modules.dashboards.contracts import DashboardContent, DashboardRevision
from dataflow.modules.dashboards.infrastructure import (
    DashboardRevisionRecord,
    SQLDashboardRepository,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0010_is_additive_and_dashboard_revisions_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "dashboards_migration_" + uuid4().hex
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
        command.upgrade(config, "0009")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="dashboards-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Dashboards migration", "", None
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

        command.upgrade(config, "0010")
        command.downgrade(config, "0009")  # sin dashboards: ida y vuelta
        command.upgrade(config, "0010")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0010}
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
            assert db.scalar(select(func.count()).select_from(DashboardRevisionRecord)) == 0

            repository = SQLDashboardRepository(db)
            family = repository.create_family(owner, project.id)
            content = DashboardContent(title="Ventas", project_id=project.id)
            revision = DashboardRevision(
                id=uuid4(),
                family_id=family,
                project_id=project.id,
                revision=1,
                previous_revision_id=None,
                cause="create",
                refreshed_version_id=None,
                content=content,
                content_sha256=content_sha256(content),
                created_by=owner,
                created_at=datetime.now(UTC),
            )
            repository.append(family, 0, revision, "c")
            repository.remember(owner, project.id, uuid4(), "f" * 64, revision.id)
            db.commit()
            assert repository.head(owner, family) == (revision, 1)
            for statement in [
                "UPDATE dashboard_revisions SET content_sha256 = 'x'",
                "DELETE FROM dashboard_revisions",
                "DELETE FROM dashboard_save_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0009")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {"report_families", "report_revisions", "report_save_requests", "report_renders"}


def exists_at_0010(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES
