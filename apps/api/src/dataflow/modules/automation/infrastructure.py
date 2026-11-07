"""Persistencia de la política de automatización (Fase 11B): una familia por proyecto con
revisiones inmutables, solicitudes idempotentes y el vínculo de cada aprobación automática con la
revisión de política que la autorizó (todas inmutables por trigger salvo la cabeza)."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.automation.contracts import (
    ApprovalOrigin,
    Evaluation,
    PolicyContent,
    PolicyRevision,
)
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError

NOT_FOUND = ("AUTOMATION_POLICY_NOT_FOUND", "Política de automatización no encontrada.", 404)


class AutomationPolicyFamilyRecord(Base):
    __tablename__ = "automation_policy_families"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    head_revision: Mapped[int]
    head_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "automation_policy_revisions.id", use_alter=True, name="fk_automation_policy_head"
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AutomationPolicyRevisionRecord(Base):
    __tablename__ = "automation_policy_revisions"
    __table_args__ = (
        UniqueConstraint("family_id", "revision", name="uq_automation_policy_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("automation_policy_families.id"), index=True)
    revision: Mapped[int]
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("automation_policy_revisions.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AutomationPolicySaveRequest(Base):
    __tablename__ = "automation_policy_save_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("automation_policy_revisions.id"))


class AutomationApprovalRecord(Base):
    """Una aprobación de limpieza concedida por una política: actor humano (quien guardó la
    revisión, en `cleaning_approvals.approved_by`), ejecutor (manual o pipeline), revisión exacta
    de la política, efecto autorizado y evaluación."""

    __tablename__ = "automation_approvals"
    approval_id: Mapped[UUID] = mapped_column(ForeignKey("cleaning_approvals.id"), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    policy_revision_id: Mapped[UUID] = mapped_column(ForeignKey("automation_policy_revisions.id"))
    preview_execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"))
    effect_sha256: Mapped[str] = mapped_column(String(64))
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON)
    executor: Mapped[str] = mapped_column(String(16))
    pipeline_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLPolicyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, record: AutomationPolicyRevisionRecord) -> PolicyRevision:
        family = self.db.get(AutomationPolicyFamilyRecord, record.family_id)
        assert family
        return PolicyRevision(
            id=record.id,
            family_id=record.family_id,
            project_id=family.project_id,
            revision=record.revision,
            previous_revision_id=record.previous_revision_id,
            content=PolicyContent.model_validate(record.content),
            content_sha256=record.content_sha256,
            created_by=record.created_by,
            created_at=record.created_at.astimezone(UTC),
        )

    def lock_project(self, project: UUID) -> None:
        key = hashlib.sha256(b"automation_policy" + project.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def family(self, owner: UUID, project: UUID) -> AutomationPolicyFamilyRecord | None:
        return self.db.scalar(
            select(AutomationPolicyFamilyRecord).where(
                AutomationPolicyFamilyRecord.project_id == project,
                AutomationPolicyFamilyRecord.owner_id == owner,
            )
        )

    def head(self, owner: UUID, project: UUID) -> PolicyRevision | None:
        family = self.family(owner, project)
        if not family or not family.head_revision_id:
            return None
        record = self.db.get(AutomationPolicyRevisionRecord, family.head_revision_id)
        return self.view(record) if record else None

    def get(self, owner: UUID, revision: UUID) -> PolicyRevision:
        record = self.db.scalar(
            select(AutomationPolicyRevisionRecord)
            .join(
                AutomationPolicyFamilyRecord,
                AutomationPolicyFamilyRecord.id == AutomationPolicyRevisionRecord.family_id,
            )
            .where(
                AutomationPolicyRevisionRecord.id == revision,
                AutomationPolicyFamilyRecord.owner_id == owner,
            )
        )
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return self.view(record)

    def replay(
        self, owner: UUID, project: UUID, key: UUID, fingerprint: str
    ) -> PolicyRevision | None:
        record = self.db.get(AutomationPolicySaveRequest, (owner, project, key))
        if not record:
            return None
        if record.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave de guardado corresponde a otros cambios.", 409
            )
        revision = self.db.get(AutomationPolicyRevisionRecord, record.revision_id)
        assert revision
        return self.view(revision)

    def append(
        self,
        owner: UUID,
        project: UUID,
        content: PolicyContent,
        content_sha256: str,
        key: UUID,
        fingerprint: str,
        correlation: str,
    ) -> PolicyRevision:
        now = datetime.now(UTC)
        family = self.family(owner, project)
        if family is None:
            family = AutomationPolicyFamilyRecord(
                id=uuid4(), project_id=project, owner_id=owner, head_revision=0, created_at=now
            )
            self.db.add(family)
            self.db.flush()
        record = AutomationPolicyRevisionRecord(
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
            AutomationPolicySaveRequest(
                owner_id=owner,
                scope_id=project,
                request_key=key,
                fingerprint=fingerprint,
                revision_id=record.id,
            )
        )
        record_event(self.db, owner, record.id, "automation.policy_saved", correlation)
        self.db.flush()
        return self.view(record)

    def record_approval(
        self,
        approval: UUID,
        policy: PolicyRevision,
        preview: UUID,
        effect_sha256: str,
        evaluation: Evaluation,
        executor: str,
        pipeline_run_id: UUID | None,
    ) -> None:
        self.db.add(
            AutomationApprovalRecord(
                approval_id=approval,
                project_id=policy.project_id,
                policy_revision_id=policy.id,
                preview_execution_id=preview,
                effect_sha256=effect_sha256,
                evaluation=evaluation.model_dump(mode="json"),
                executor=executor,
                pipeline_run_id=pipeline_run_id,
                created_at=datetime.now(UTC),
            )
        )
        record_event(self.db, policy.created_by, approval, "automation.approved", str(preview))
        self.db.flush()

    def approval_origin(self, owner: UUID, approval: UUID) -> ApprovalOrigin:
        record = self.db.scalar(
            select(AutomationApprovalRecord)
            .join(
                AutomationPolicyFamilyRecord,
                AutomationPolicyFamilyRecord.project_id == AutomationApprovalRecord.project_id,
            )
            .where(
                AutomationApprovalRecord.approval_id == approval,
                AutomationPolicyFamilyRecord.owner_id == owner,
            )
        )
        if record is None:
            return ApprovalOrigin(approval_id=approval, automatic=False)
        policy = self.db.get(AutomationPolicyRevisionRecord, record.policy_revision_id)
        assert policy
        return ApprovalOrigin(
            approval_id=approval,
            automatic=True,
            policy_revision_id=policy.id,
            policy_revision=policy.revision,
            executor=record.executor,
            pipeline_run_id=record.pipeline_run_id,
            evaluation=Evaluation.model_validate(record.evaluation),
            created_at=record.created_at.astimezone(UTC),
        )

    def pending_automatic_approvals(self, owner: UUID, project: UUID) -> list[UUID]:
        family = self.family(owner, project)
        if family is None:
            return []
        return list(
            self.db.scalars(
                select(AutomationApprovalRecord.approval_id)
                .where(AutomationApprovalRecord.project_id == project)
                .order_by(AutomationApprovalRecord.created_at)
            )
        )
