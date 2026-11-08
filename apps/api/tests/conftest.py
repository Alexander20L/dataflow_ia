import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from service_routes import router as service_routes
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from dataflow.bootstrap import models  # noqa: F401
from dataflow.bootstrap.app import app
from dataflow.bootstrap.dependencies import object_store
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base, get_db
from dataflow.platform.runtime import RuntimeTransition

# Rutas sólo de pruebas sobre los servicios conservados (Fase 13): nunca en la API real.
app.include_router(service_routes)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    # Esquema efímero: nunca truncate/delete sobre tablas del usuario.
    url = os.environ.get("DATAFLOW_TEST_DATABASE_URL", get_settings().database_url)
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    schema = "test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(RuntimeTransition(id=1, state="active"))
        session.commit()
    yield engine
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    with test_engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    def override_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, headers={"Origin": "http://localhost:3002"}) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def objects(client: TestClient, tmp_path: Path) -> LocalObjects:
    store = LocalObjects(tmp_path / "objects")
    app.dependency_overrides[object_store] = lambda: store
    return store


@pytest.fixture
def committed_engine() -> Iterator[Engine]:
    admin = create_engine(get_settings().database_url, connect_args={"connect_timeout": 5})
    schema = "concurrency_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        get_settings().database_url,
        connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"},
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(RuntimeTransition(id=1, state="active"))
            session.commit()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
