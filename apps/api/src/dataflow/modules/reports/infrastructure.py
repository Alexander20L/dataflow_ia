"""Persistencia de informes (Fase 9): familias por proyecto, revisiones inmutables (trigger),
solicitudes idempotentes y el vínculo de cada PDF con la revisión exacta que lo generó."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.reports.contracts import ReportContent, ReportRevision
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class ReportFamilyRecord(Base):
    __tablename__ = "report_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("report_revisions.id", use_alter=True, name="fk_report_head")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportRevisionRecord(Base):
    __tablename__ = "report_revisions"
    __table_args__ = (UniqueConstraint("family_id", "revision", name="uq_report_family_revision"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("report_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("report_revisions.id"))
    cause: Mapped[str] = mapped_column(String(16))
    refreshed_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_version_records.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportSaveRequest(Base):
    """Idempotencia: `scope_id` es el proyecto (alta) o la familia (revisión o actualización)."""

    __tablename__ = "report_save_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("report_revisions.id"))


class ReportRenderRecord(Base):
    """PDF generado (ejecución `report_render`) a partir de una revisión exacta del informe."""

    __tablename__ = "report_renders"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("report_families.id"), index=True)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("report_revisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


NOT_FOUND = ("REPORT_NOT_FOUND", "Informe no encontrado.", 404)


class SQLReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, record: ReportRevisionRecord) -> ReportRevision:
        family = self.db.get(ReportFamilyRecord, record.family_id)
        assert family
        return ReportRevision(
            id=record.id,
            family_id=record.family_id,
            project_id=family.project_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            cause=record.cause,
            refreshed_version_id=record.refreshed_version_id,
            content=ReportContent.model_validate(deepcopy(record.content)),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def lock_scope(self, scope: UUID) -> None:
        key = hashlib.sha256(b"report" + scope.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def create_family(self, owner: UUID, project: UUID) -> UUID:
        family = ReportFamilyRecord(
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
            select(ReportFamilyRecord)
            .where(ReportFamilyRecord.id == family, ReportFamilyRecord.owner_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return record.project_id, record.head_revision

    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> ReportRevision | None:
        record = self.db.get(ReportSaveRequest, (owner, scope, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(ReportRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self, family: UUID, expected: int, revision: ReportRevision, correlation: str
    ) -> None:
        record = self.db.get(ReportFamilyRecord, family)
        assert record
        if record.head_revision != expected:
            raise ApplicationError("REPORT_CONFLICT", "El informe cambió: recárgalo.", 409)
        self.db.add(
            ReportRevisionRecord(
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
            self.db, revision.created_by, revision.id, f"reports.{revision.cause}", correlation
        )
        self.db.flush()

    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None:
        self.db.add(
            ReportSaveRequest(
                owner_id=owner,
                scope_id=scope,
                request_key=key,
                fingerprint=fingerprint,
                revision_id=revision,
            )
        )
        self.db.flush()

    def head(self, owner: UUID, family: UUID) -> tuple[ReportRevision, int]:
        record = self.db.get(ReportFamilyRecord, family, populate_existing=True)
        if not record or record.owner_id != owner or not record.head_revision_id:
            raise ApplicationError(*NOT_FOUND)
        revision = self.db.get(ReportRevisionRecord, record.head_revision_id)
        assert revision
        return self.view(revision), record.head_revision

    def families(self, owner: UUID, project: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                select(ReportFamilyRecord.id)
                .where(
                    ReportFamilyRecord.owner_id == owner,
                    ReportFamilyRecord.project_id == project,
                    ReportFamilyRecord.head_revision_id.is_not(None),
                )
                .order_by(ReportFamilyRecord.created_at, ReportFamilyRecord.id)
            )
        )

    def revision(self, owner: UUID, revision: UUID) -> ReportRevision:
        record = self.db.get(ReportRevisionRecord, revision)
        family = self.db.get(ReportFamilyRecord, record.family_id) if record else None
        if not record or not family or family.owner_id != owner:
            raise ApplicationError(*NOT_FOUND)
        return self.view(record)

    def revisions(self, owner: UUID, family: UUID) -> list[ReportRevision]:
        record = self.db.get(ReportFamilyRecord, family)
        if not record or record.owner_id != owner:
            raise ApplicationError(*NOT_FOUND)
        return [
            self.view(r)
            for r in self.db.scalars(
                select(ReportRevisionRecord)
                .where(ReportRevisionRecord.family_id == family)
                .order_by(ReportRevisionRecord.revision.desc())
            )
        ]

    def add_render(self, owner: UUID, family: UUID, revision: UUID, execution: UUID) -> None:
        if self.db.get(ReportRenderRecord, execution):
            return  # misma solicitud idempotente: la ejecución ya estaba vinculada
        self.db.add(
            ReportRenderRecord(
                execution_id=execution,
                owner_id=owner,
                family_id=family,
                revision_id=revision,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def renders(self, owner: UUID, family: UUID) -> list[tuple[UUID, UUID]]:
        rows = self.db.execute(
            select(ReportRenderRecord.execution_id, ReportRenderRecord.revision_id)
            .where(ReportRenderRecord.owner_id == owner, ReportRenderRecord.family_id == family)
            .order_by(ReportRenderRecord.created_at.desc())
        )
        return [(row[0], row[1]) for row in rows]

    def render_owner(self, owner: UUID, execution: UUID) -> tuple[UUID, UUID] | None:
        record = self.db.get(ReportRenderRecord, execution)
        if not record or record.owner_id != owner:
            return None
        return record.family_id, record.revision_id
