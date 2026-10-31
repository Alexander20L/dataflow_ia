import hashlib
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.understanding.semantic_contracts import (
    Representation,
    RevisionPage,
    SemanticContent,
    SemanticReference,
    SemanticRevision,
)
from dataflow.platform.canonical import digest
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class SemanticFamilyRecord(Base):
    __tablename__ = "semantic_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    table_artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_artifacts.id"), unique=True
    )
    table_sha256: Mapped[str] = mapped_column(String(64))
    schema_sha256: Mapped[str] = mapped_column(String(64))
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("semantic_revisions.id", use_alter=True, name="fk_semantic_head")
    )


class SemanticRevisionRecord(Base):
    __tablename__ = "semantic_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_semantic_family_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("semantic_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("semantic_revisions.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SemanticSaveRequest(Base):
    __tablename__ = "semantic_save_requests"
    family_id: Mapped[UUID] = mapped_column(ForeignKey("semantic_families.id"), primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("semantic_revisions.id"))


class SQLSemanticRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def view(record: SemanticRevisionRecord) -> SemanticRevision:
        return SemanticRevision(
            id=record.id,
            family_id=record.family_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            content=SemanticContent.model_validate(deepcopy(record.content)),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def head(self, owner: UUID, artifact: UUID) -> SemanticRevision | None:
        family = self.db.scalar(
            select(SemanticFamilyRecord)
            .where(
                SemanticFamilyRecord.owner_id == owner,
                SemanticFamilyRecord.table_artifact_id == artifact,
            )
            .execution_options(populate_existing=True)
        )
        if not family or not family.head_revision_id:
            return None
        record = self.db.get(SemanticRevisionRecord, family.head_revision_id)
        assert record
        return self.view(record)

    def lock_family(self, representation: Representation) -> tuple[UUID, int]:
        key = hashlib.sha256(
            b"semantic-family" + representation.table_ref.artifact_id.bytes
        ).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))
        family = self.db.scalar(
            select(SemanticFamilyRecord)
            .where(
                SemanticFamilyRecord.table_artifact_id == representation.table_ref.artifact_id,
                SemanticFamilyRecord.owner_id == representation.owner_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        schema_hash = digest("schema", [c.model_dump(mode="json") for c in representation.columns])
        if not family:
            family = SemanticFamilyRecord(
                id=uuid4(),
                project_id=representation.project_id,
                owner_id=representation.owner_id,
                version_id=representation.table_ref.version_id,
                table_artifact_id=representation.table_ref.artifact_id,
                table_sha256=representation.table_ref.artifact_sha256,
                schema_sha256=schema_hash,
                head_revision=0,
            )
            self.db.add(family)
            self.db.flush()
        elif (
            family.table_sha256 != representation.table_ref.artifact_sha256
            or family.schema_sha256 != schema_hash
        ):
            raise ApplicationError(
                "SEMANTIC_SCHEMA_MISMATCH",
                "La tabla o su esquema no coincide con esta familia semántica.",
                409,
            )
        return family.id, family.head_revision

    def replay(self, family: UUID, key: UUID, fingerprint: str) -> SemanticRevision | None:
        record = self.db.get(SemanticSaveRequest, (family, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(SemanticRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self, family: UUID, expected: int, revision: SemanticRevision, correlation: str
    ) -> None:
        record = self.db.get(SemanticFamilyRecord, family)
        assert record
        if record.head_revision != expected:
            raise ApplicationError("SEMANTIC_REVISION_CONFLICT", "La revisión actual cambió.", 409)
        self.db.add(
            SemanticRevisionRecord(
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
            self.db, revision.created_by, revision.id, "semantic.revision_saved", correlation
        )
        self.db.flush()

    def remember(self, family: UUID, key: UUID, fingerprint: str, revision: UUID) -> None:
        self.db.add(
            SemanticSaveRequest(
                family_id=family, request_key=key, fingerprint=fingerprint, revision_id=revision
            )
        )
        self.db.flush()

    def get(self, owner: UUID, revision: UUID) -> SemanticRevision:
        record = self.db.scalar(
            select(SemanticRevisionRecord)
            .join(SemanticFamilyRecord, SemanticFamilyRecord.id == SemanticRevisionRecord.family_id)
            .where(SemanticRevisionRecord.id == revision, SemanticFamilyRecord.owner_id == owner)
        )
        if not record:
            raise ApplicationError(
                "SEMANTIC_REVISION_NOT_FOUND", "Revisión semántica no encontrada.", 404
            )
        return self.view(record)

    def page(self, owner: UUID, artifact: UUID, limit: int, offset: int) -> RevisionPage:
        query = (
            select(SemanticRevisionRecord)
            .join(SemanticFamilyRecord, SemanticFamilyRecord.id == SemanticRevisionRecord.family_id)
            .where(
                SemanticFamilyRecord.owner_id == owner,
                SemanticFamilyRecord.table_artifact_id == artifact,
            )
        )
        total = int(self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        records = self.db.scalars(
            query.order_by(SemanticRevisionRecord.revision.desc()).limit(limit).offset(offset)
        )
        return RevisionPage(
            items=[
                SemanticReference(id=r.id, revision=r.revision, content_sha256=r.content_sha256)
                for r in records
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
