"""Persistencia del control de la investigación (Fase 25, migración 0026).

Peticiones de pausa o cancelación, inmutables y sólo de añadir. El trabajo de fondo las lee entre
una investigación y otra; la primera petición de una ejecución es la que vale.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.exploration.contracts import ControlAction
from dataflow.platform.database import Base


class InvestigationControlRecord(Base):
    __tablename__ = "investigation_controls"
    __table_args__ = (
        CheckConstraint("action IN ('pause', 'cancel')", name="ck_investigation_control_action"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLInvestigationControls:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, owner: UUID, execution: UUID, action: ControlAction) -> None:
        self.db.add(
            InvestigationControlRecord(
                id=uuid4(),
                owner_id=owner,
                execution_id=execution,
                action=action,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def requested(self, execution: UUID) -> ControlAction | None:
        found = self.db.scalar(
            select(InvestigationControlRecord.action)
            .where(InvestigationControlRecord.execution_id == execution)
            .order_by(InvestigationControlRecord.created_at, InvestigationControlRecord.id)
            .limit(1)
        )
        return "pause" if found == "pause" else "cancel" if found == "cancel" else None

    def for_executions(self, executions: list[UUID]) -> dict[UUID, ControlAction]:
        if not executions:
            return {}
        rows = self.db.execute(
            select(InvestigationControlRecord.execution_id, InvestigationControlRecord.action)
            .where(InvestigationControlRecord.execution_id.in_(executions))
            .order_by(InvestigationControlRecord.created_at.desc())
        ).all()
        found: dict[UUID, ControlAction] = {}
        for execution, action in rows:  # el último gana en el bucle: el primero registrado
            found[execution] = "pause" if action == "pause" else "cancel"
        return found
