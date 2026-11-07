from datetime import UTC, datetime
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
from dataflow.bootstrap.services import make_analysis, make_executions, make_ingestion, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import PlanBindingRecord, PlanRecord
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.planning.infrastructure import (
    PlanningCreateRequest,
    PlanningValidationRecord,
)
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.canonical import digest
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0005_is_additive_keeps_05_executions_and_protects_user_plans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "planning_migration_" + uuid4().hex
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
        command.upgrade(config, "0004")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="planning-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Planning migration", "", None
            )
            content = b"id,importe\n001,10.50\n002,\n002,\n"
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", content, ",", uuid4(), str(uuid4())
            )
            assert make_runner(db, objects).run_once()
            table = next(
                a
                for a in make_executions(db).artifacts(owner, version.execution_id)
                if a.kind == "table"
            )
            analysis = make_analysis(db, objects).submit(
                owner,
                version.id,
                table.id,
                table.content.sha256,
                "quality_only",
                uuid4(),
                str(uuid4()),
            )
            assert make_runner(db, objects).run_once()
            executions = make_executions(db)
            before = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            diagnostic = make_ingestion(db, objects).diagnostic(owner, version.id)
            assert {run.state for run, _ in before.values()} == {"succeeded"}

        command.upgrade(config, "0005")
        # Ida y vuelta sin planes de usuario: el downgrade conserva los datos 0.5.
        command.downgrade(config, "0004")
        command.upgrade(config, "0005")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                # Sólo los objetos que existen hasta 0005; las tablas de migraciones
                # posteriores se comparan en su propia prueba.
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0005}
                )
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            executions = make_executions(db)
            after = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            assert after == before and analysis.id in after
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == diagnostic
            assert make_ingestion(db, objects).original(owner, version.id)[1] == content
            for plan in db.scalars(select(PlanRecord)):
                assert digest("plan", plan.content) == plan.content_sha256
            for record in (PlanBindingRecord, PlanningValidationRecord, PlanningCreateRequest):
                assert db.scalar(select(func.count()).select_from(record)) == 0

            now = datetime.now(UTC)
            content = {"objective": None, "steps": []}
            plan = PlanRecord(
                id=uuid4(),
                family_id=uuid4(),
                revision=1,
                content=content,
                content_sha256=digest("plan", content),
                created_by=owner,
                created_at=now,
            )
            db.add(plan)
            db.flush()
            with pytest.raises(IntegrityError, match="input_artifact_id"):
                db.add(
                    PlanBindingRecord(
                        plan_revision_id=plan.id,
                        project_id=project.id,
                        input_artifact_sha256=table.content.sha256,
                    )
                )
                db.flush()
            db.rollback()
            db.add(plan)
            db.flush()
            db.add(
                PlanBindingRecord(
                    plan_revision_id=plan.id,
                    project_id=project.id,
                    input_artifact_id=table.id,
                    input_artifact_sha256=table.content.sha256,
                )
            )
            db.add(
                PlanningValidationRecord(
                    plan_revision_id=plan.id,
                    catalog_version="analysis-v1",
                    problems=[],
                    valid=True,
                    validated_at=now,
                )
            )
            db.add(
                PlanningCreateRequest(
                    project_id=project.id,
                    request_key=uuid4(),
                    owner_id=owner,
                    fingerprint="b" * 64,
                    plan_revision_id=plan.id,
                    created_at=now,
                )
            )
            db.commit()
            for table_name in [
                "execution_plan_revisions",
                "execution_plan_bindings",
                "planning_validations",
                "planning_create_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(f"DELETE FROM {table_name}"))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0004")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {
    "cleaning_approvals",
    "dataset_version_lineage",
    "execution_error_details",
    "quality_ruleset_families",
    "quality_ruleset_revisions",
    "quality_ruleset_save_requests",
    "analytics_metric_families",
    "analytics_metric_revisions",
    "analytics_metric_save_requests",
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


def exists_at_0005(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES | TABLES_AFTER_0012
