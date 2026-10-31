from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class RuntimeTransition(Base):
    __tablename__ = "runtime_transitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(20))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)


def require_ready(db: Session) -> None:
    transition = db.get(RuntimeTransition, 1)
    if not transition or transition.state != "active":
        raise ApplicationError(
            "MIGRATION_REQUIRED", "La migración de datasets y ejecuciones está pendiente.", 503
        )
