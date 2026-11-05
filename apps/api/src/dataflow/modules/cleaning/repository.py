from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.cleaning.contracts import ApprovalView, ApprovedEffect
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class CleaningApprovalRecord(Base):
    """Aprobación del efecto exacto de una vista previa. Inmutable salvo `revoked_at`
    (sólo NULL → fecha, por trigger). Como mucho una vigente por vista previa."""

    __tablename__ = "cleaning_approvals"
    __table_args__ = (
        Index(
            "uq_cleaning_approval_active",
            "preview_execution_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    plan_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plan_revisions.id"), index=True
    )
    preview_execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"))
    effect_sha256: Mapped[str] = mapped_column(String(64))
    input_artifact_sha256: Mapped[str] = mapped_column(String(64))
    semantic_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("semantic_revisions.id"))
    config_sha256: Mapped[str] = mapped_column(String(64))
    environment_sha256: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SQLApprovalSource:
    def __init__(self, db: Session) -> None:
        self.db = db

    def approved_effect(self, approval: UUID) -> ApprovedEffect | None:
        record = self.db.get(CleaningApprovalRecord, approval)
        if not record:
            return None
        return ApprovedEffect(
            record.id,
            record.plan_revision_id,
            record.preview_execution_id,
            record.effect_sha256,
            record.revoked_at is not None,
        )


def approval_view(record: CleaningApprovalRecord) -> ApprovalView:
    return ApprovalView(
        id=record.id,
        plan_revision_id=record.plan_revision_id,
        preview_execution_id=record.preview_execution_id,
        effect_sha256=record.effect_sha256,
        input_artifact_sha256=record.input_artifact_sha256,
        semantic_revision_id=record.semantic_revision_id,
        config_sha256=record.config_sha256,
        environment_sha256=record.environment_sha256,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        revoked_at=record.revoked_at,
        status="revoked" if record.revoked_at else "active",
    )


class SQLApprovalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, owner: UUID, approval: UUID) -> ApprovalView:
        record = self.db.scalar(
            select(CleaningApprovalRecord)
            .where(
                CleaningApprovalRecord.id == approval, CleaningApprovalRecord.approved_by == owner
            )
            .with_for_update()
        )
        if not record:
            raise ApplicationError("APPROVAL_NOT_FOUND", "Aprobación no encontrada.", 404)
        return approval_view(record)

    def active(self, preview: UUID) -> ApprovalView | None:
        record = self.db.scalar(
            select(CleaningApprovalRecord).where(
                CleaningApprovalRecord.preview_execution_id == preview,
                CleaningApprovalRecord.revoked_at.is_(None),
            )
        )
        return approval_view(record) if record else None

    def add(self, approval: ApprovalView, correlation: str) -> None:
        self.db.add(
            CleaningApprovalRecord(
                **approval.model_dump(exclude={"status"}),
            )
        )
        self.db.flush()
        record_event(self.db, approval.approved_by, approval.id, "cleaning.approved", correlation)

    def revoke(self, approval: UUID, at: datetime, correlation: str) -> None:
        record = self.db.get(CleaningApprovalRecord, approval)
        assert record is not None
        record.revoked_at = at
        self.db.flush()
        record_event(self.db, record.approved_by, approval, "cleaning.revoked", correlation)
