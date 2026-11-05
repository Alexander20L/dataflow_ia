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
    make_rulesets,
    make_runner,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.quality.infrastructure import QualityRulesetRevisionRecord
from dataflow.modules.quality.rules_contracts import RulesetDraft
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0008_is_additive_and_ruleset_revisions_are_immutable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "rulesets_migration_" + uuid4().hex
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
        command.upgrade(config, "0007")
        with Session(engine, expire_on_commit=False) as db:
            owner = uuid4()
            db.add(
                UserRecord(
                    id=owner,
                    email="rulesets-migration@example.com",
                    name="Migration",
                    password_hash="not-a-login",
                )
            )
            db.commit()
            project = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
                owner, "Rulesets migration", "", None
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

        command.upgrade(config, "0008")
        command.downgrade(config, "0007")  # sin reglas: ida y vuelta
        command.upgrade(config, "0008")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
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
            assert db.scalar(select(func.count()).select_from(QualityRulesetRevisionRecord)) == 0
            table = executions.representations(owner, version.id)[0]
            rulesets = make_rulesets(db, objects)
            draft = RulesetDraft.model_validate(
                {
                    "name": "Reglas",
                    "rules": [
                        {"id": "id", "kind": "required", "column_id": table.columns[0]["id"]}
                    ],
                }
            )
            saved = rulesets.save(
                owner, table.id, table.content.sha256, 0, draft, uuid4(), "c"
            ).revision
            assert saved.revision == 1
            assert rulesets.revision(owner, saved.id) == saved
            for statement in [
                "UPDATE quality_ruleset_revisions SET content_sha256 = 'x'",
                "DELETE FROM quality_ruleset_revisions",
                "DELETE FROM quality_ruleset_save_requests",
            ]:
                with pytest.raises(IntegrityError, match="IMMUTABLE_RECORD"):
                    db.execute(text(statement))
                db.rollback()
        with pytest.raises(RuntimeError, match="ROLL_FORWARD_REQUIRED"):
            command.downgrade(config, "0007")
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
