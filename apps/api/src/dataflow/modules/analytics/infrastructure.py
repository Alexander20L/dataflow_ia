"""Persistencia de métricas (Fase 7A): una familia por métrica, anclada a una tabla base del
proyecto, con revisiones inmutables."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.analytics.contracts import BaseTable, MetricContent, MetricRevision
from dataflow.modules.audit.public import record_event
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class MetricFamilyRecord(Base):
    __tablename__ = "analytics_metric_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    base_version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    base_artifact_id: Mapped[UUID] = mapped_column(ForeignKey("execution_artifacts.id"))
    base_sha256: Mapped[str] = mapped_column(String(64))
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analytics_metric_revisions.id", use_alter=True, name="fk_analytics_metric_head")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MetricRevisionRecord(Base):
    __tablename__ = "analytics_metric_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_analytics_metric_family_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("analytics_metric_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analytics_metric_revisions.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MetricSaveRequest(Base):
    """Idempotencia: `scope_id` es la tabla (alta de métrica) o la familia (nueva revisión)."""

    __tablename__ = "analytics_metric_save_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("analytics_metric_revisions.id"))


class SQLMetricRepository:
    def __init__(self, db: Session, owner: UUID | None = None) -> None:
        self.db = db
        self.owner = owner

    def view(self, record: MetricRevisionRecord) -> MetricRevision:
        family = self.db.get(MetricFamilyRecord, record.family_id)
        assert family
        return MetricRevision(
            id=record.id,
            family_id=record.family_id,
            project_id=family.project_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            content=MetricContent.model_validate(deepcopy(record.content)),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def lock_scope(self, scope: UUID) -> None:
        key = hashlib.sha256(b"analytics-metric" + scope.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def create_family(self, owner: UUID, project: UUID, base: BaseTable) -> UUID:
        family = MetricFamilyRecord(
            id=uuid4(),
            project_id=project,
            owner_id=owner,
            base_version_id=base.version_id,
            base_artifact_id=base.artifact_id,
            base_sha256=base.artifact_sha256,
            head_revision=0,
            created_at=datetime.now(UTC),
        )
        self.db.add(family)
        self.db.flush()
        return family.id

    def lock_family(self, owner: UUID, family: UUID) -> tuple[BaseTable, int]:
        self.lock_scope(family)
        record = self.db.scalar(
            select(MetricFamilyRecord)
            .where(MetricFamilyRecord.id == family, MetricFamilyRecord.owner_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not record:
            raise ApplicationError("METRIC_NOT_FOUND", "Métrica no encontrada.", 404)
        base = BaseTable(
            version_id=record.base_version_id,
            artifact_id=record.base_artifact_id,
            artifact_sha256=record.base_sha256,
        )
        return base, record.head_revision

    def replay(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str
    ) -> MetricRevision | None:
        record = self.db.get(MetricSaveRequest, (owner, scope, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(MetricRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self, family: UUID, expected: int, revision: MetricRevision, correlation: str
    ) -> None:
        record = self.db.get(MetricFamilyRecord, family)
        assert record
        if record.head_revision != expected:
            raise ApplicationError("METRIC_CONFLICT", "La métrica cambió: recarga.", 409)
        self.db.add(
            MetricRevisionRecord(
                id=revision.id,
                family_id=family,
                revision=revision.revision,
                previous_revision_id=revision.previous_revision_id,
                content=revision.content.model_dump(mode="json"),
                content_sha256=revision.content_sha256,
                created_by=revision.created_by,
                created_at=revision.created_at,
            )
        )
        self.db.flush()
        record.head_revision_id, record.head_revision = revision.id, revision.revision
        record_event(
            self.db, revision.created_by, revision.id, "analytics.metric_saved", correlation
        )
        self.db.flush()

    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, revision: UUID
    ) -> None:
        self.db.add(
            MetricSaveRequest(
                owner_id=owner,
                scope_id=scope,
                request_key=key,
                fingerprint=fingerprint,
                revision_id=revision,
            )
        )
        self.db.flush()

    def head(self, family: UUID) -> tuple[MetricRevision, int] | None:
        record = self.db.get(MetricFamilyRecord, family, populate_existing=True)
        if not record or not record.head_revision_id:
            return None
        revision = self.db.get(MetricRevisionRecord, record.head_revision_id)
        assert revision
        return self.view(revision), record.head_revision

    def families(self, owner: UUID, project: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                select(MetricFamilyRecord.id)
                .where(
                    MetricFamilyRecord.owner_id == owner, MetricFamilyRecord.project_id == project
                )
                .order_by(MetricFamilyRecord.created_at, MetricFamilyRecord.id)
            )
        )

    def revision(self, owner: UUID, revision: UUID) -> MetricRevision:
        record = self.db.get(MetricRevisionRecord, revision)
        family = self.db.get(MetricFamilyRecord, record.family_id) if record else None
        if not record or not family or family.owner_id != owner:
            raise ApplicationError("METRIC_NOT_FOUND", "Métrica no encontrada.", 404)
        return self.view(record)
