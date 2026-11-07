from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import TABLES_AFTER_0012
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.services import make_analysis, make_executions, make_ingestion, make_runner
from dataflow.modules.cleaning.repository import CleaningApprovalRecord
from dataflow.modules.datasets.infrastructure import VersionLineageRecord, VersionRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0006_is_additive_and_protects_approvals_and_lineage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "cleaning_migration_" + uuid4().hex
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
        command.upgrade(config, "0005")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="cleaning-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Cleaning migration", "", None
            )
            content = b"id,importe\n001, 10\n002,\n"
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
                owner, version.id, table.id, table.content.sha256, "quality_only", uuid4(), "c"
            )
            assert make_runner(db, objects).run_once()
            executions = make_executions(db)
            before = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            diagnostic = make_ingestion(db, objects).diagnostic(owner, version.id)

        command.upgrade(config, "0006")
        command.downgrade(config, "0005")  # sin datos de limpieza: ida y vuelta
        command.upgrade(config, "0006")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                # Sólo los objetos que existen hasta 0006; las tablas de migraciones
                # posteriores se comparan en su propia prueba.
                context = MigrationContext.configure(
                    connection, opts={"include_object": exists_at_0006}
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
            for record in (CleaningApprovalRecord, VersionLineageRecord):
                assert db.scalar(select(func.count()).select_from(record)) == 0

            source = db.get(VersionRecord, version.id)
            assert source
            derived = VersionRecord(
                id=uuid4(),
                dataset_id=source.dataset_id,
                number=2,
                kind="derived",
                file_name="existing.csv · limpieza",
                content_object_id=table.content.object_id,
                created_at=datetime.now(UTC),
            )
            db.add(derived)
            db.flush()
            db.add(
                VersionLineageRecord(
                    version_id=derived.id,
                    parent_version_id=version.id,
                    producer_execution_id=analysis.id,
                )
            )
            assert analysis.plan
            approval = CleaningApprovalRecord(
                id=uuid4(),
                plan_revision_id=analysis.plan.id,
                preview_execution_id=analysis.id,
                effect_sha256="a" * 64,
                input_artifact_sha256=table.content.sha256,
                config_sha256="b" * 64,
                environment_sha256="c" * 64,
                approved_by=owner,
                approved_at=datetime.now(UTC),
            )
            db.add(approval)
            db.commit()

            # Sólo una aprobación vigente por vista previa.
            second = CleaningApprovalRecord(
                **{
                    **{c.key: getattr(approval, c.key) for c in CleaningApprovalRecord.__table__.c},
                    "id": uuid4(),
                }
            )
            with pytest.raises(IntegrityError, match="uq_cleaning_approval_active"):
                db.add(second)
                db.flush()
            db.rollback()

            def change(**values: object) -> None:
                db.execute(
                    update(CleaningApprovalRecord)
                    .where(CleaningApprovalRecord.id == approval.id)
                    .values(**values)
                )

            with pytest.raises(IntegrityError, match="IMMUTABLE_APPROVAL"):
                change(effect_sha256="d" * 64)
            db.rollback()
            change(revoked_at=datetime.now(UTC))  # revocar está permitido una vez
            db.commit()
            with pytest.raises(IntegrityError, match="IMMUTABLE_APPROVAL"):
                change(revoked_at=None)
            db.rollback()
            with pytest.raises(IntegrityError, match="IMMUTABLE_APPROVAL"):
                db.execute(text("DELETE FROM cleaning_approvals"))
            db.rollback()
            # Revocada la anterior, la misma vista previa admite otra aprobación vigente.
            db.add(second)
            db.commit()
            with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                db.execute(text("DELETE FROM dataset_version_lineage"))
            db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0005")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


LATER_TABLES = {
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
    "copilot_text_audits",
}


def exists_at_0006(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in LATER_TABLES | TABLES_AFTER_0012
