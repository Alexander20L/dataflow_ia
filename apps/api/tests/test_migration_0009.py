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
from dataflow.bootstrap.services import (
    make_executions,
    make_ingestion,
    make_metrics,
    make_runner,
)
from dataflow.modules.analytics.contracts import MetricDraft
from dataflow.modules.analytics.infrastructure import MetricRevisionRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0009_is_additive_and_metric_revisions_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "metrics_migration_" + uuid4().hex
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
        command.upgrade(config, "0008")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="metrics-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Metrics migration", "", None
            )
            content = b"id,importe\n001, 10\n002,\n"
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", content, ",", uuid4(), str(uuid4())
            )
            assert make_runner(db, objects).run_once()
            executions = make_executions(db)
            before = {
                run.id: (
                    run,
                    executions.artifacts(owner, run.id),
                    executions.attempts(owner, run.id),
                )
                for run in executions.for_version(owner, version.id)
            }
            diagnostic = make_ingestion(db, objects).diagnostic(owner, version.id)

        command.upgrade(config, "0009")
        command.downgrade(config, "0008")  # sin métricas: ida y vuelta
        command.upgrade(config, "0009")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0009}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            executions = make_executions(db)
            after = {
                run.id: (
                    run,
                    executions.artifacts(owner, run.id),
                    executions.attempts(owner, run.id),
                )
                for run in executions.for_version(owner, version.id)
            }
            assert after == before
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == diagnostic
            assert db.scalar(select(func.count()).select_from(MetricRevisionRecord)) == 0
            table = executions.representations(owner, version.id)[0]
            metrics = make_metrics(db, objects)
            draft = MetricDraft.model_validate(
                {
                    "label": "Registros",
                    "measure_column_id": table.columns[0]["id"],
                    "aggregation": "count",
                }
            )
            saved = metrics.save(
                owner, table.id, table.content.sha256, None, 0, draft, uuid4(), "c"
            ).revision
            assert saved.revision == 1
            assert metrics.revision(owner, saved.id) == saved
            for statement in [
                "UPDATE analytics_metric_revisions SET content_sha256 = 'x'",
                "DELETE FROM analytics_metric_revisions",
                "DELETE FROM analytics_metric_save_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0008")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {
    "dashboard_families",
    "dashboard_revisions",
    "dashboard_save_requests",
    "report_families",
    "report_revisions",
    "report_save_requests",
    "report_renders",
    "copilot_conversations",
    "copilot_ai_calls",
    "copilot_messages",
    "copilot_action_links",
    "copilot_requests",
}


def exists_at_0009(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES
