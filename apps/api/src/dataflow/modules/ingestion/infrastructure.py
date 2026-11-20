"""Intentos de conexión a bases de datos (Fase 32, ADR-050, migración 0029).

Sólo huellas SHA-256 de la cuenta, de la IP de origen y del destino (la dirección comprobada o
el nombre de un servidor de la lista): ni contraseñas ni nombres en claro. Los registros se
purgan a las 24 h.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from dataflow.modules.ingestion.application import AttemptLimits
from dataflow.modules.ingestion.contracts import DatabaseCopy, DataModel
from dataflow.platform.database import Base

WINDOW = timedelta(minutes=15)
DAY = timedelta(hours=24)


class ConnectionAttemptRecord(Base):
    __tablename__ = "database_attempts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    client_key: Mapped[str] = mapped_column(String(64))
    target_key: Mapped[str] = mapped_column(String(64), index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class SQLConnectionAttempts:
    def __init__(self, db: Session) -> None:
        self.db = db

    def count(self, *conditions: ColumnElement[bool]) -> int:
        query = select(func.count()).select_from(ConnectionAttemptRecord).where(*conditions)
        return int(self.db.scalar(query) or 0)

    def admit(self, user: UUID, client: str, target: str, limits: AttemptLimits) -> UUID | None:
        now = datetime.now(UTC)
        user_key, target_key = key(str(user)), key(target)
        # Serializar por cuenta y por destino para que los límites resistan peticiones a la vez
        # (como los intentos de inicio de sesión).
        for bucket in sorted({user_key, target_key}):
            lock = int.from_bytes(bytes.fromhex(bucket)[:8], signed=True)
            self.db.execute(select(func.pg_advisory_xact_lock(lock)))
        self.db.execute(
            delete(ConnectionAttemptRecord).where(ConnectionAttemptRecord.created_at < now - DAY)
        )
        recent = ConnectionAttemptRecord.created_at >= now - WINDOW
        if (
            self.count(ConnectionAttemptRecord.user_key == user_key, recent) >= limits.per_user
            or self.count(ConnectionAttemptRecord.target_key == target_key, recent)
            >= limits.per_target
            or self.count(
                ConnectionAttemptRecord.user_key == user_key,
                ConnectionAttemptRecord.succeeded.is_(False),
            )
            >= limits.failures_per_day
        ):
            return None
        record = ConnectionAttemptRecord(
            id=uuid4(),
            user_key=user_key,
            client_key=key(client),
            target_key=target_key,
            succeeded=False,
            created_at=now,
        )
        self.db.add(record)
        self.db.flush()
        return record.id

    def succeeded(self, attempt: UUID) -> None:
        self.db.execute(
            update(ConnectionAttemptRecord)
            .where(ConnectionAttemptRecord.id == attempt)
            .values(succeeded=True)
        )


# --- Fase 33 (ADR-051): copias de bases en segundo plano ---------------------------------------

# Una copia en curso late cada pocos segundos; sin latido durante este tiempo, la API que la
# hacía se reinició y la copia se perdió (la contraseña no se guarda: hay que volver a conectar).
STALE = timedelta(seconds=90)
INTERRUPTED = (
    "DATABASE_COPY_INTERRUPTED",
    "La copia se interrumpió. Vuelve a conectar: por seguridad la contraseña no se guarda.",
)


class DatabaseCopyRecord(Base):
    __tablename__ = "database_copies"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    engine: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20))
    server: Mapped[str] = mapped_column(String(300))
    database_name: Mapped[str] = mapped_column(String(128))
    schema_name: Mapped[str | None] = mapped_column(String(128))
    tables: Mapped[int | None]
    omitted: Mapped[int | None]
    version_id: Mapped[UUID | None] = mapped_column(Uuid)
    model: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def copy_view(record: DatabaseCopyRecord) -> DatabaseCopy:
    return DatabaseCopy(
        id=record.id,
        project_id=record.project_id,
        engine=record.engine,
        kind=record.kind,
        state=record.state,
        server=record.server,
        database=record.database_name,
        schema_name=record.schema_name,
        tables=record.tables,
        omitted=record.omitted,
        version_id=record.version_id,
        model=DataModel.model_validate(record.model) if record.model is not None else None,
        error_code=record.error_code,
        error_message=record.error_message,
        created_at=record.created_at,
        finished_at=record.finished_at,
    )


class SQLDatabaseCopies:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        owner: UUID,
        project: UUID,
        engine: str,
        kind: str,
        server: str,
        database: str,
        schema: str | None,
    ) -> DatabaseCopy:
        now = datetime.now(UTC)
        record = DatabaseCopyRecord(
            id=uuid4(),
            owner_id=owner,
            project_id=project,
            engine=engine,
            kind=kind,
            state="queued",
            server=server[:300],
            database_name=database[:128],
            schema_name=schema[:128] if schema else None,
            created_at=now,
            heartbeat_at=now,
        )
        self.db.add(record)
        self.db.flush()
        return copy_view(record)

    def get(self, owner: UUID, copy: UUID) -> DatabaseCopy | None:
        record = self.db.get(DatabaseCopyRecord, copy, populate_existing=True)
        if record is None or record.owner_id != owner:
            return None
        now = datetime.now(UTC)
        if record.state in {"queued", "running"} and record.heartbeat_at < now - STALE:
            record.state, record.finished_at = "failed", now
            record.error_code, record.error_message = INTERRUPTED
            self.db.flush()
        return copy_view(record)

    def heartbeat(self, copy: UUID) -> None:
        self.db.execute(
            update(DatabaseCopyRecord)
            .where(
                DatabaseCopyRecord.id == copy,
                DatabaseCopyRecord.state.in_(["queued", "running"]),
            )
            .values(heartbeat_at=datetime.now(UTC))
        )

    def running(self, copy: UUID) -> None:
        now = datetime.now(UTC)
        self.db.execute(
            update(DatabaseCopyRecord)
            .where(DatabaseCopyRecord.id == copy)
            .values(state="running", heartbeat_at=now)
        )

    def succeeded(
        self,
        copy: UUID,
        version: UUID | None,
        model: DataModel | None,
        tables: int,
        omitted: int,
    ) -> None:
        self.db.execute(
            update(DatabaseCopyRecord)
            .where(DatabaseCopyRecord.id == copy)
            .values(
                state="succeeded",
                version_id=version,
                model=model.model_dump(mode="json") if model is not None else None,
                tables=tables,
                omitted=omitted,
                finished_at=datetime.now(UTC),
            )
        )

    def failed(self, copy: UUID, code: str, message: str) -> None:
        self.db.execute(
            update(DatabaseCopyRecord)
            .where(DatabaseCopyRecord.id == copy)
            .values(
                state="failed",
                error_code=code[:80],
                error_message=message[:300],
                finished_at=datetime.now(UTC),
            )
        )
