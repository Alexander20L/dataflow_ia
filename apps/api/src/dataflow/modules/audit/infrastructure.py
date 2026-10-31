from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from dataflow.platform.database import Base


class AuditRecord(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    entity_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
