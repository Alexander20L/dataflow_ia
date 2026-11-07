from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from migration_support import TABLES_AFTER_0017
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def exists_at_0017(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    # En 0017 existen todas las tablas de la Fase 11 hasta 11E (no las de 11F).
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in TABLES_AFTER_0017


def test_0017_is_additive_and_reversible_without_dashboards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "analysis_migration_" + uuid4().hex
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
        command.downgrade(config, "0016")  # sin dashboards automáticos: ida y vuelta
        command.upgrade(config, "0017")
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"include_object": exists_at_0017}
            )
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
