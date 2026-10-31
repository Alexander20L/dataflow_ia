"""Crear, sin vaciar, la base exclusiva para pruebas de navegador locales."""

import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from dataflow.platform.config import get_settings

url = make_url(os.environ.get("DATAFLOW_E2E_DATABASE_URL", get_settings().database_url))
name = url.database if os.environ.get("DATAFLOW_E2E_DATABASE_URL") else "dataflow_e2e"
if not name or not name.endswith("_e2e") or not re.fullmatch(r"[a-z0-9_]+", name):
    raise SystemExit("La base de pruebas debe terminar en _e2e y contener sólo a-z, 0-9, _.")
engine = create_engine(
    url.set(database="postgres"), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5}
)
with engine.connect() as connection:
    exists = connection.execute(
        text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
    ).scalar()
    if not exists:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
print(f"Base E2E preparada: {name}; las migraciones se aplican al iniciar Playwright.")
engine.dispose()
