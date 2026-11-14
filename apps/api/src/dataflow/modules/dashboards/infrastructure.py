"""Persistencia de dashboards (Fase 8): una familia por dashboard dentro de un proyecto, con
revisiones inmutables (trigger) y solicitudes idempotentes."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from dataflow.platform.database import Base


class DashboardFamilyRecord(Base):
    __tablename__ = "dashboard_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dashboard_revisions.id", use_alter=True, name="fk_dashboard_head")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DashboardRevisionRecord(Base):
    __tablename__ = "dashboard_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_dashboard_family_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("dashboard_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("dashboard_revisions.id"))
    cause: Mapped[str] = mapped_column(String(16))
    refreshed_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_version_records.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DashboardSaveRequest(Base):
    """Idempotencia: `scope_id` es el proyecto (alta) o la familia (revisión o actualización)."""

    __tablename__ = "dashboard_save_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("dashboard_revisions.id"))
