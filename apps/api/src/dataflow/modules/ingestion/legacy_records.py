"""Tablas 0.3 de sólo lectura tras cutover; nunca participan en trabajos nuevos."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from dataflow.platform.database import Base


class LegacyVersionRecord(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "number", name="uq_version_number"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id"), index=True)
    number: Mapped[int]
    file_name: Mapped[str] = mapped_column(String(255))
    original_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LegacyExecutionRecord(Base):
    __tablename__ = "import_executions"
    __table_args__ = (
        UniqueConstraint("project_id", "request_key", name="uq_import_request"),
        Index("ix_import_queue", "state", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_versions.id"), unique=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    request_key: Mapped[UUID] = mapped_column(Uuid)
    separator: Mapped[str] = mapped_column(String(8))
    engine_version: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column(Uuid)
    row_count: Mapped[int | None]
    column_count: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(300))
    correlation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LegacyArtifactRecord(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (UniqueConstraint("version_id", "kind", name="uq_artifact_kind"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_versions.id"))
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("import_executions.id"))
    kind: Mapped[str] = mapped_column(String(20))
    object_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
