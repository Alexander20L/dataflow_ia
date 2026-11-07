"""Migración 0018 (Fase 11F): auditorías textuales guardadas, aditiva e inmutable."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.copilot.contracts import AuditCard, AuditContent, CallRecord, TextAudit
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.dashboards.infrastructure import (
    DashboardFamilyRecord,
    DashboardRevisionRecord,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0018_is_additive_and_text_audits_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "audit_migration_" + uuid4().hex
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
        command.upgrade(config, "0017")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="audit-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Audit migration", "", None
            )
            family, revision = uuid4(), uuid4()
            now = datetime.now(UTC)
            db.add(
                DashboardFamilyRecord(
                    id=family,
                    project_id=project.id,
                    owner_id=owner,
                    head_revision=1,
                    head_revision_id=None,
                    created_at=now,
                )
            )
            db.flush()
            db.add(
                DashboardRevisionRecord(
                    id=revision,
                    family_id=family,
                    revision=1,
                    previous_revision_id=None,
                    cause="create",
                    refreshed_version_id=None,
                    content={"title": "D", "cards": []},
                    content_sha256="d" * 64,
                    created_by=owner,
                    created_at=now,
                )
            )
            db.commit()

        command.upgrade(config, "0018")
        command.downgrade(config, "0017")  # sin auditorías: ida y vuelta
        command.upgrade(config, "0018")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            assert db.get(DashboardRevisionRecord, revision) is not None  # nada cambia

            repository = SQLCopilotRepository(db)
            call = repository.log_call(
                CallRecord(
                    owner_id=owner,
                    project_id=project.id,
                    conversation_id=None,
                    task="text_audit",
                    provider="fake",
                    model="fake",
                    parameters={},
                    prompt_id="copilot-audit",
                    prompt_version="v1",
                    context_sha256="c" * 64,
                    input_tokens=10,
                    output_tokens=5,
                    cache_read_tokens=0,
                    cache_write_tokens=0,
                    cost_usd=Decimal("0"),
                    latency_ms=1,
                    outcome="accepted",
                )
            )
            audit = TextAudit(
                id=uuid4(),
                dashboard_revision_id=revision,
                project_id=project.id,
                audit_key="k" * 64,
                result_sha256="r" * 64,
                provider="fake",
                model="fake",
                prompt_id="copilot-audit",
                prompt_version="v1",
                config={"max_output_tokens": 4000},
                cards=[AuditCard(card_id=uuid4(), title="T", execution_id=None, included=False)],
                content=AuditContent(
                    resumen_ejecutivo=[],
                    alertas_criticas=[],
                    recomendaciones=[[], []],
                    unverified_numbers=0,
                ),
                created_by=owner,
                created_at=now,
            )
            saved = repository.save_audit(audit, call, "c")
            # Misma revisión y clave: se devuelve la guardada, no se duplica.
            assert (
                repository.save_audit(audit.model_copy(update={"id": uuid4()}), call, "c") == saved
            )
            db.commit()
            assert repository.audits(owner, revision) == [saved]
            for statement in [
                "UPDATE copilot_text_audits SET model = 'x'",
                "DELETE FROM copilot_text_audits",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0017")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
