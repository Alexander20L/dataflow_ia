from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from dataflow.platform.config import get_settings


class Base(DeclarativeBase):
    pass


class SQLUnitOfWork:
    def __init__(self, db: Session) -> None:
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()


engine = create_engine(
    get_settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
)
session_factory = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with session_factory() as session:
        yield session
