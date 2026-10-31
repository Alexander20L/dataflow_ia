import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import DateTime, ForeignKey, String, Uuid, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.identity.contracts import SessionIdentity, User
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class UserRecord(Base):
    __tablename__ = "identity_users"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(256))


class SessionRecord(Base):
    __tablename__ = "identity_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AttemptRecord(Base):
    __tablename__ = "identity_attempts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email_key: Mapped[str] = mapped_column(String(64), index=True)
    ip_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ArgonPasswords:
    def __init__(self) -> None:
        self.hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return self.hasher.verify(encoded, password)
        except (VerificationError, InvalidHashError):
            return False


class SQLIdentityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def user(record: UserRecord) -> User:
        return User(record.id, record.email, record.name)

    def find_credentials(self, email: str) -> tuple[User, str] | None:
        record = self.db.scalar(select(UserRecord).where(UserRecord.email == email))
        return (self.user(record), record.password_hash) if record else None

    def create_user(self, user: User, password_hash: str) -> None:
        self.db.add(
            UserRecord(id=user.id, email=user.email, name=user.name, password_hash=password_hash)
        )
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ApplicationError(
                "ACCOUNT_UNAVAILABLE", "No se puede crear esta cuenta.", 409
            ) from exc

    def save_session(self, identity: SessionIdentity) -> None:
        self.db.add(
            SessionRecord(
                token_hash=identity.session_hash,
                user_id=identity.user.id,
                csrf_token=identity.csrf_token,
                expires_at=identity.expires_at,
            )
        )
        self.db.commit()

    def find_session(self, token_hash: str) -> SessionIdentity | None:
        row = self.db.execute(
            select(SessionRecord, UserRecord)
            .join(UserRecord)
            .where(SessionRecord.token_hash == token_hash)
        ).first()
        if not row:
            return None
        record, user = row
        return SessionIdentity(
            self.user(user), record.token_hash, record.csrf_token, record.expires_at
        )

    def delete_session(self, token_hash: str) -> None:
        self.db.execute(delete(SessionRecord).where(SessionRecord.token_hash == token_hash))
        self.db.commit()

    def record_attempt(self, email: str, ip: str) -> bool:
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=15)
        email_key = hashlib.sha256(email.encode()).hexdigest()
        ip_key = hashlib.sha256(ip.encode()).hexdigest()
        # Serializar buckets compartidos para que los límites resistan solicitudes concurrentes.
        for key in sorted([email_key, ip_key]):
            lock_id = int.from_bytes(bytes.fromhex(key)[:8], signed=True)
            self.db.execute(select(func.pg_advisory_xact_lock(lock_id)))
        self.db.execute(delete(AttemptRecord).where(AttemptRecord.created_at < cutoff))
        email_count = (
            self.db.scalar(
                select(func.count())
                .select_from(AttemptRecord)
                .where(
                    AttemptRecord.email_key == email_key,
                    AttemptRecord.created_at >= cutoff,
                )
            )
            or 0
        )
        ip_count = (
            self.db.scalar(
                select(func.count())
                .select_from(AttemptRecord)
                .where(
                    AttemptRecord.ip_key == ip_key,
                    AttemptRecord.created_at >= cutoff,
                )
            )
            or 0
        )
        allowed = email_count < 15 and ip_count < 100
        if allowed:
            self.db.add(AttemptRecord(email_key=email_key, ip_key=ip_key, created_at=now))
        # Persistir también cuando la posterior autenticación falla.
        self.db.commit()
        return allowed
