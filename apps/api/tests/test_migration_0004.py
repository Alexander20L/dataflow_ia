from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.bootstrap.services import make_executions, make_ingestion, make_runner, make_semantics
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.understanding.semantic_repository import SemanticRevisionRecord
from dataflow.platform.config import get_settings


def test_0004_is_additive_does_not_confirm_existing_tables_and_protects_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "semantic_migration_" + uuid4().hex
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
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="semantic-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Semantic migration", "", None
            )
            content = b"id,importe\n001,10.50\n002,\n"
            version = make_ingestion(db, objects).submit(
                owner, project.id, "existing.csv", content, ",", uuid4(), str(uuid4())
            )
            assert make_runner(db, objects).run_once()
            before = make_ingestion(db, objects).diagnostic(owner, version.id)
            table = next(
                a
                for a in make_executions(db).artifacts(owner, version.execution_id)
                if a.kind == "table"
            )
        command.upgrade(config, "0004")
        with Session(engine, expire_on_commit=False) as db:
            semantics = make_semantics(db, objects)
            context = semantics.context(owner, table.id)
            assert context.head is None and context.revision_count == 0
            assert all(column.review_state == "pending" for column in context.editable.columns)
            assert [str(c.id) for c in context.columns] == [c["id"] for c in table.columns]
            result = semantics.save(
                owner, table.id, table.content.sha256, 0, context.editable, uuid4(), str(uuid4())
            )
            assert result.revision.revision == 1
            assert db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) == 1
            assert make_ingestion(db, objects).original(owner, version.id)[1] == content
            assert make_ingestion(db, objects).diagnostic(owner, version.id) == before
            assert (
                make_executions(db).get(owner, version.execution_id).plan.content["semantic_ref"]
                is None
            )
            with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                db.execute(text("UPDATE semantic_revisions SET content=content"))
            db.rollback()
            with pytest.raises(IntegrityError, match="IMMUTABLE_SEMANTIC_BINDING"):
                db.execute(text("UPDATE semantic_families SET table_sha256=repeat('0',64)"))
            db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0003")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
