"""Verificar PostgreSQL, volumen y subproceso reales sin tocar datos del usuario."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from dataflow.bootstrap import models  # noqa: F401
from dataflow.bootstrap.services import make_ingestion, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base
from dataflow.platform.runtime import RuntimeTransition

settings = get_settings()
schema = "smoke_" + uuid4().hex
admin = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
with admin.begin() as connection:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
engine = create_engine(
    settings.database_url, connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"}
)
try:
    Base.metadata.create_all(engine)
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    with (
        TemporaryDirectory(dir=settings.storage_path) as directory,
        Session(engine, expire_on_commit=False) as db,
    ):
        owner = uuid4()
        correlation = str(uuid4())
        db.add(
            UserRecord(
                id=owner,
                email="smoke@example.com",
                name="Smoke",
                password_hash="not-an-auth-account",
            )
        )
        db.commit()
        project = ProjectService(SQLProjectRepository(db, correlation)).create(
            owner, "Smoke CSV", "", None
        )
        objects = LocalObjects(Path(directory))
        db.add(RuntimeTransition(id=1, state="active"))
        db.commit()
        ingestion = make_ingestion(db, objects)
        content = b"id,importe\r\n001,10.50\r\n002,\r\n"
        version = ingestion.submit(
            owner, project.id, "smoke.csv", content, ",", uuid4(), correlation
        )
        assert make_runner(db, objects).run_once()
        result = ingestion.diagnostic(owner, version.id)
        assert result.profile.row_count == 2 and result.profile.column_count == 2
        assert result.quality.missing_cells == 1
        assert ingestion.original(owner, version.id)[1] == content
        assert ingestion.preview(owner, version.id, 10, 0).rows[0].values["id"] == "001"
        print("CSV smoke OK: original íntegro, 2 registros y diagnóstico; entorno efímero.")
finally:
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
