"""Migración 0029 (Fase 32): intentos de conexión a bases de datos, aditiva, con ida y vuelta, y
límites por cuenta, por destino y de fallidos por día."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion.application import AttemptLimits
from dataflow.modules.ingestion.infrastructure import ConnectionAttemptRecord, SQLConnectionAttempts
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base


def test_0029_is_additive_and_limits_connection_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_url = get_settings().database_url
    admin = create_engine(original_url, connect_args={"connect_timeout": 5})
    schema = "database_attempts_migration_" + uuid4().hex
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
        command.upgrade(config, "0029")
        command.downgrade(config, "0028")
        assert "database_attempts" not in inspect(engine).get_table_names()
        command.upgrade(config, "0029")

        with Session(engine, expire_on_commit=False) as db:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection, opts={})
                diff = compare_metadata(context, Base.metadata)
            assert diff == [], diff

            attempts = SQLConnectionAttempts(db)
            limits = AttemptLimits(per_user=2, failures_per_day=3, per_target=3)
            ana, luis, eva = uuid4(), uuid4(), uuid4()
            first = attempts.admit(ana, "10.0.0.1", "203.0.113.10", limits)
            assert first is not None
            attempts.succeeded(first)
            assert attempts.admit(ana, "10.0.0.1", "203.0.113.10", limits) is not None
            db.commit()
            # Dos por cuenta en 15 min.
            assert attempts.admit(ana, "10.0.0.1", "198.51.100.7", limits) is None
            # Tres hacia el mismo destino, sumando todas las cuentas.
            assert attempts.admit(luis, "10.0.0.2", "203.0.113.10", limits) is not None
            assert attempts.admit(eva, "10.0.0.3", "203.0.113.10", limits) is None
            db.commit()
            # Sin contraseñas ni nombres en claro: sólo huellas.
            stored = db.query(ConnectionAttemptRecord).all()
            assert len(stored) == 3
            assert all(len(r.target_key) == 64 and "203.0.113" not in r.target_key for r in stored)
            assert [r.succeeded for r in stored].count(True) == 1
            # Los fallidos del día cuentan aunque hayan pasado los 15 min.
            db.execute(
                text("UPDATE database_attempts SET created_at = created_at - interval '1 hour'")
            )
            db.commit()
            ok = attempts.admit(luis, "10.0.0.2", "192.0.2.1", limits)
            assert ok is not None
            db.commit()
            loose = AttemptLimits(per_user=10, failures_per_day=2, per_target=10)
            assert attempts.admit(luis, "10.0.0.2", "192.0.2.2", loose) is None
            # Pasadas 24 h se purgan.
            db.execute(
                text("UPDATE database_attempts SET created_at = created_at - interval '25 hours'")
            )
            db.commit()
            assert attempts.admit(luis, "10.0.0.2", "192.0.2.2", loose) is not None
            db.commit()
            assert db.query(ConnectionAttemptRecord).count() == 1
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
