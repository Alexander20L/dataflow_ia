"""Intentos de conexión a bases de datos (Fase 32, ADR-050, migración 0029).

Sólo huellas SHA-256 de la cuenta, de la IP de origen y del destino (la dirección comprobada o
el nombre de un servidor de la lista): ni contraseñas ni nombres en claro. Los registros se
purgan a las 24 h.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Uuid, delete, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from dataflow.modules.ingestion.application import AttemptLimits
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
