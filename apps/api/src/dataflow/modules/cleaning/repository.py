from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.cleaning.contracts import ApprovedEffect
from dataflow.platform.database import Base


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
