"""Persistencia de dashboards (Fase 8): una familia por dashboard dentro de un proyecto, con
revisiones inmutables (trigger) y solicitudes idempotentes."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.dashboards.contracts import DashboardContent, DashboardRevision
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


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


NOT_FOUND = ("DASHBOARD_NOT_FOUND", "Dashboard no encontrado.", 404)


class SQLDashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, record: DashboardRevisionRecord) -> DashboardRevision:
        family = self.db.get(DashboardFamilyRecord, record.family_id)
        assert family
        return DashboardRevision(
            id=record.id,
            family_id=record.family_id,
            project_id=family.project_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            cause=record.cause,
            refreshed_version_id=record.refreshed_version_id,
            content=DashboardContent.model_validate(deepcopy(record.content)),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def lock_scope(self, scope: UUID) -> None:
        key = hashlib.sha256(b"dashboard" + scope.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def create_family(self, owner: UUID, project: UUID) -> UUID:
        family = DashboardFamilyRecord(
            id=uuid4(),
            project_id=project,
            owner_id=owner,
            head_revision=0,
            created_at=datetime.now(UTC),
        )
        self.db.add(family)
        self.db.flush()
        return family.id

    def lock_family(self, owner: UUID, family: UUID) -> tuple[UUID, int]:
        self.lock_scope(family)
        record = self.db.scalar(
            select(DashboardFamilyRecord)
            .where(DashboardFamilyRecord.id == family, DashboardFamilyRecord.owner_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return record.project_id, record.head_revision

    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> DashboardRevision | None:
        record = self.db.get(DashboardSaveRequest, (owner, scope, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(DashboardRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self, family: UUID, expected: int, revision: DashboardRevision, correlation: str
    ) -> None:
        record = self.db.get(DashboardFamilyRecord, family)
        assert record
        if record.head_revision != expected:
            raise ApplicationError("DASHBOARD_CONFLICT", "El dashboard cambió: recárgalo.", 409)
        self.db.add(
            DashboardRevisionRecord(
                id=revision.id,
                family_id=family,
                revision=revision.revision,
                previous_revision_id=revision.previous_revision_id,
                cause=revision.cause,
                refreshed_version_id=revision.refreshed_version_id,
                content=revision.content.model_dump(mode="json"),
                content_sha256=revision.content_sha256,
                created_by=revision.created_by,
                created_at=revision.created_at,
            )
        )
        self.db.flush()
        record.head_revision_id, record.head_revision = revision.id, revision.revision
        record_event(
            self.db, revision.created_by, revision.id, f"dashboards.{revision.cause}", correlation
        )
        self.db.flush()

    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None:
        self.db.add(
            DashboardSaveRequest(
                owner_id=owner,
                scope_id=scope,
                request_key=key,
                fingerprint=fingerprint,
                revision_id=revision,
            )
        )
        self.db.flush()

    def head(self, owner: UUID, family: UUID) -> tuple[DashboardRevision, int]:
        record = self.db.get(DashboardFamilyRecord, family, populate_existing=True)
        if not record or record.owner_id != owner or not record.head_revision_id:
            raise ApplicationError(*NOT_FOUND)
        revision = self.db.get(DashboardRevisionRecord, record.head_revision_id)
        assert revision
        return self.view(revision), record.head_revision

    def families(self, owner: UUID, project: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                select(DashboardFamilyRecord.id)
                .where(
                    DashboardFamilyRecord.owner_id == owner,
                    DashboardFamilyRecord.project_id == project,
                    DashboardFamilyRecord.head_revision_id.is_not(None),
                )
                .order_by(DashboardFamilyRecord.created_at, DashboardFamilyRecord.id)
            )
        )

    def revision(self, owner: UUID, revision: UUID) -> DashboardRevision:
        record = self.db.get(DashboardRevisionRecord, revision)
        family = self.db.get(DashboardFamilyRecord, record.family_id) if record else None
        if not record or not family or family.owner_id != owner:
            raise ApplicationError(*NOT_FOUND)
        return self.view(record)
