"""Persistencia de conjuntos de reglas (csv-quality-v2): familias y revisiones inmutables."""

import hashlib
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.quality.rules_contracts import (
    BaseTable,
    RulesetContent,
    RulesetReference,
    RulesetRevision,
)
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class QualityRulesetFamilyRecord(Base):
    """Un conjunto de reglas por tabla base; la cabeza avanza con cada revisión."""

    __tablename__ = "quality_ruleset_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    base_version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    base_artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_artifacts.id"), unique=True
    )
    base_sha256: Mapped[str] = mapped_column(String(64))
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("quality_ruleset_revisions.id", use_alter=True, name="fk_quality_ruleset_head")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QualityRulesetRevisionRecord(Base):
    __tablename__ = "quality_ruleset_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_quality_ruleset_family_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("quality_ruleset_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("quality_ruleset_revisions.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QualityRulesetSaveRequest(Base):
    __tablename__ = "quality_ruleset_save_requests"
    family_id: Mapped[UUID] = mapped_column(
        ForeignKey("quality_ruleset_families.id"), primary_key=True
    )
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("quality_ruleset_revisions.id"))


class SQLRulesetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, record: QualityRulesetRevisionRecord) -> RulesetRevision:
        family = self.db.get(QualityRulesetFamilyRecord, record.family_id)
        assert family
        return RulesetRevision(
            id=record.id,
            family_id=record.family_id,
            project_id=family.project_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            content=RulesetContent.model_validate(deepcopy(record.content)),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def family_for_table(self, owner: UUID, artifact: UUID) -> UUID | None:
        return self.db.scalar(
            select(QualityRulesetFamilyRecord.id).where(
                QualityRulesetFamilyRecord.owner_id == owner,
                QualityRulesetFamilyRecord.base_artifact_id == artifact,
            )
        )

    def lock_family(self, owner: UUID, project: UUID, base: BaseTable) -> tuple[UUID, int]:
        key = hashlib.sha256(b"quality-ruleset-family" + base.artifact_id.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))
        family = self.db.scalar(
            select(QualityRulesetFamilyRecord)
            .where(
                QualityRulesetFamilyRecord.base_artifact_id == base.artifact_id,
                QualityRulesetFamilyRecord.owner_id == owner,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not family:
            family = QualityRulesetFamilyRecord(
                id=uuid4(),
                project_id=project,
                owner_id=owner,
                base_version_id=base.version_id,
                base_artifact_id=base.artifact_id,
                base_sha256=base.artifact_sha256,
                head_revision=0,
                created_at=datetime.now().astimezone(),
            )
            self.db.add(family)
            self.db.flush()
        elif family.base_sha256 != base.artifact_sha256:
            raise ApplicationError(
                "INPUT_MISMATCH", "La tabla no coincide con la de este conjunto de reglas.", 409
            )
        return family.id, family.head_revision

    def replay(self, family: UUID, key: UUID, fingerprint: str) -> RulesetRevision | None:
        record = self.db.get(QualityRulesetSaveRequest, (family, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(QualityRulesetRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self, family: UUID, expected: int, revision: RulesetRevision, correlation: str
    ) -> None:
        record = self.db.get(QualityRulesetFamilyRecord, family)
        assert record
        if record.head_revision != expected:
            raise ApplicationError(
                "QUALITY_RULESET_CONFLICT", "El conjunto de reglas cambió: recarga.", 409
            )
        self.db.add(
            QualityRulesetRevisionRecord(
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
            self.db, revision.created_by, revision.id, "quality.ruleset_saved", correlation
        )
        self.db.flush()

    def remember(self, family: UUID, key: UUID, fingerprint: str, revision: UUID) -> None:
        self.db.add(
            QualityRulesetSaveRequest(
                family_id=family, request_key=key, fingerprint=fingerprint, revision_id=revision
            )
        )
        self.db.flush()

    def head(self, family: UUID) -> tuple[RulesetRevision, int] | None:
        record = self.db.get(QualityRulesetFamilyRecord, family, populate_existing=True)
        if not record or not record.head_revision_id:
            return None
        revision = self.db.get(QualityRulesetRevisionRecord, record.head_revision_id)
        assert revision
        return self.view(revision), record.head_revision

    def families(self, owner: UUID, project: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                select(QualityRulesetFamilyRecord.id)
                .where(
                    QualityRulesetFamilyRecord.owner_id == owner,
                    QualityRulesetFamilyRecord.project_id == project,
                )
                .order_by(QualityRulesetFamilyRecord.created_at, QualityRulesetFamilyRecord.id)
            )
        )

    def revision(self, owner: UUID, revision: UUID) -> RulesetRevision:
        record = self.db.get(QualityRulesetRevisionRecord, revision)
        family = self.db.get(QualityRulesetFamilyRecord, record.family_id) if record else None
        if not record or not family or family.owner_id != owner:
            raise ApplicationError(
                "QUALITY_RULESET_NOT_FOUND", "Conjunto de reglas no encontrado.", 404
            )
        return self.view(record)

    def history(self, owner: UUID, family: UUID) -> list[RulesetReference]:
        record = self.db.get(QualityRulesetFamilyRecord, family)
        if not record or record.owner_id != owner:
            raise ApplicationError(
                "QUALITY_RULESET_NOT_FOUND", "Conjunto de reglas no encontrado.", 404
            )
        return [
            RulesetReference(id=r.id, revision=r.revision, content_sha256=r.content_sha256)
            for r in self.db.scalars(
                select(QualityRulesetRevisionRecord)
                .where(QualityRulesetRevisionRecord.family_id == family)
                .order_by(QualityRulesetRevisionRecord.revision.desc())
            )
        ]
