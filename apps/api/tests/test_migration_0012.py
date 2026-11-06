from datetime import UTC, datetime
from decimal import Decimal
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
from dataflow.modules.copilot.contracts import ActionLink, CallRecord
from dataflow.modules.copilot.infrastructure import MessageRecord, SQLCopilotRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0012_is_additive_and_copilot_records_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "copilot_migration_" + uuid4().hex
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
        command.upgrade(config, "0011")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="copilot-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Copilot migration", "", None
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

        command.upgrade(config, "0012")
        command.downgrade(config, "0011")  # sin conversaciones: ida y vuelta
        command.upgrade(config, "0012")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff
            executions = make_executions(db)
            after = {
                run.id: (run, executions.artifacts(owner, run.id))
                for run in executions.for_version(owner, version.id)
            }
            assert after == before
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == diagnostic
            assert db.scalar(select(func.count()).select_from(MessageRecord)) == 0

            repository = SQLCopilotRepository(db)
            conversation = repository.create_conversation(owner, project.id, "Ventas")
            call = repository.log_call(
                CallRecord(
                    owner_id=owner,
                    project_id=project.id,
                    conversation_id=conversation.id,
                    task="copilot_turn",
                    provider="fake",
                    model="fake",
                    parameters={},
                    prompt_id="copilot-turn",
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
            message = repository.append(
                conversation.id, "user", version.id, {"text": "hola"}, None, "c"
            )
            repository.add_link(
                message.id,
                ActionLink(
                    kind="metric",
                    plan_revision_id=None,
                    execution_id=None,
                    metric_revision_id=uuid4(),
                    created_at=datetime.now(UTC),
                ),
            )
            repository.remember(owner, conversation.id, uuid4(), "f" * 64, message.id)
            db.commit()
            assert call and repository.messages(conversation.id)[0].text == "hola"
            for statement in [
                "UPDATE copilot_messages SET seq = 9",
                "DELETE FROM copilot_messages",
                "UPDATE copilot_conversations SET title = 'x'",
                "UPDATE copilot_ai_calls SET input_tokens = 0",
                "DELETE FROM copilot_action_links",
                "DELETE FROM copilot_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0011")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
