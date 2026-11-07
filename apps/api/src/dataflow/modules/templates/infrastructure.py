"""Persistencia de los mapeos confirmados (Fase 11D): una familia por proyecto y molde, con
revisiones inmutables y solicitudes idempotentes (inmutables por trigger)."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.templates.contracts import MappingContent, MappingRevision
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError

NOT_FOUND = ("TEMPLATE_MAPPING_NOT_FOUND", "Mapeo no encontrado.", 404)


class TemplateMappingFamilyRecord(Base):
    __tablename__ = "template_mapping_families"
    __table_args__ = (
        UniqueConstraint("project_id", "template", name="uq_template_mapping_project_template"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    template: Mapped[str] = mapped_column(String(32))
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("template_mapping_revisions.id", use_alter=True, name="fk_template_mapping_head")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemplateMappingRevisionRecord(Base):
    __tablename__ = "template_mapping_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_template_mapping_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("template_mapping_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("template_mapping_revisions.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemplateMappingSaveRequest(Base):
    __tablename__ = "template_mapping_save_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("template_mapping_revisions.id"))


class SQLMappingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, record: TemplateMappingRevisionRecord) -> MappingRevision:
        family = self.db.get(TemplateMappingFamilyRecord, record.family_id)
        assert family
        return MappingRevision(
            id=record.id,
            family_id=family.id,
            project_id=family.project_id,
            template=family.template,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            content=MappingContent.model_validate(record.content),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at.astimezone(UTC),
        )

    def lock(self, project: UUID, template: str) -> None:
        key = hashlib.sha256(b"template_mapping" + project.bytes + template.encode()).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def family(
        self, owner: UUID, project: UUID, template: str
    ) -> TemplateMappingFamilyRecord | None:
        return self.db.scalar(
            select(TemplateMappingFamilyRecord).where(
                TemplateMappingFamilyRecord.project_id == project,
                TemplateMappingFamilyRecord.owner_id == owner,
                TemplateMappingFamilyRecord.template == template,
            )
        )

    def head(self, owner: UUID, project: UUID, template: str) -> MappingRevision | None:
        family = self.family(owner, project, template)
        if not family or not family.head_revision_id:
            return None
        record = self.db.get(TemplateMappingRevisionRecord, family.head_revision_id)
        return self.view(record) if record else None

    def heads(self, owner: UUID, project: UUID) -> list[MappingRevision]:
        families = self.db.scalars(
            select(TemplateMappingFamilyRecord)
            .where(
                TemplateMappingFamilyRecord.project_id == project,
                TemplateMappingFamilyRecord.owner_id == owner,
            )
            .order_by(TemplateMappingFamilyRecord.created_at)
        )
        result = []
        for family in families:
            if family.head_revision_id:
                record = self.db.get(TemplateMappingRevisionRecord, family.head_revision_id)
                if record:
                    result.append(self.view(record))
        return result

    def get(self, owner: UUID, revision: UUID) -> MappingRevision:
        record = self.db.scalar(
            select(TemplateMappingRevisionRecord)
            .join(
                TemplateMappingFamilyRecord,
                TemplateMappingFamilyRecord.id == TemplateMappingRevisionRecord.family_id,
            )
            .where(
                TemplateMappingRevisionRecord.id == revision,
                TemplateMappingFamilyRecord.owner_id == owner,
            )
        )
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return self.view(record)

    def replay(
        self, owner: UUID, project: UUID, key: UUID, fingerprint: str
    ) -> MappingRevision | None:
        record = self.db.get(TemplateMappingSaveRequest, (owner, project, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(TemplateMappingRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self,
        owner: UUID,
        project: UUID,
        content: MappingContent,
        content_sha256: str,
        key: UUID,
        fingerprint: str,
        correlation: str,
    ) -> MappingRevision:
        now = datetime.now(UTC)
        family = self.family(owner, project, content.template)
        if family is None:
            family = TemplateMappingFamilyRecord(
                id=uuid4(),
                project_id=project,
                owner_id=owner,
                template=content.template,
                head_revision=0,
                created_at=now,
            )
            self.db.add(family)
            self.db.flush()
        record = TemplateMappingRevisionRecord(
            id=uuid4(),
            family_id=family.id,
            revision=family.head_revision + 1,
            previous_revision_id=family.head_revision_id,
            content=content.model_dump(mode="json"),
            content_sha256=content_sha256,
            created_by=owner,
            created_at=now,
        )
        self.db.add(record)
        self.db.flush()
        family.head_revision, family.head_revision_id = record.revision, record.id
        self.db.add(
            TemplateMappingSaveRequest(
                owner_id=owner,
                scope_id=project,
                request_key=key,
                fingerprint=fingerprint,
                revision_id=record.id,
            )
        )
        record_event(self.db, owner, record.id, "template.mapping_saved", correlation)
        self.db.flush()
        return self.view(record)
