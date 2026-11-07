"""Persistencia del pipeline automático (Fase 11C): el pipeline es un registro mutable (estado,
paso y referencias a lo que creó) y cada transición queda en un registro inmutable (trigger)."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.automation.pipeline_contracts import (
    AutomationRunPage,
    AutomationRunView,
    PipelineReason,
    PipelineRun,
    StepAttempt,
)
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError

NOT_FOUND = ("AUTOMATION_RUN_NOT_FOUND", "Pipeline no encontrado.", 404)
REFERENCES = (
    "plan_revision_id",
    "preview_execution_id",
    "approval_id",
    "apply_execution_id",
    "derived_version_id",
    "rules_execution_id",
    "result_version_id",
)


class AutomationRunRecord(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("version_id", name="uq_automation_run_version"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    policy_revision_id: Mapped[UUID] = mapped_column(ForeignKey("automation_policy_revisions.id"))
    state: Mapped[str] = mapped_column(String(16), index=True)
    step: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    plan_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    preview_execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    approval_id: Mapped[UUID | None] = mapped_column(Uuid)
    apply_execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    derived_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    rules_execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    result_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationStepAttemptRecord(Base):
    __tablename__ = "automation_step_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_automation_step_attempt_sequence"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("automation_runs.id"), index=True)
    sequence: Mapped[int]
    step: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value else None


def lock_key(run: UUID) -> int:
    return int.from_bytes(hashlib.sha256(b"automation_run" + run.bytes).digest()[:8], signed=True)


class SQLRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- creación (dentro de la transacción de publicación de la importación) ---

    def create(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        policy_revision: UUID,
        state: str = "running",
        reasons: list[dict[str, Any]] | None = None,
    ) -> UUID:
        now = datetime.now(UTC)
        record = AutomationRunRecord(
            id=uuid4(),
            project_id=project,
            owner_id=owner,
            version_id=version,
            policy_revision_id=policy_revision,
            state=state,
            step="propose",
            reasons=reasons or [],
            created_at=now,
            updated_at=now,
            finished_at=now if state != "running" else None,
        )
        self.db.add(record)
        self.db.flush()
        self.log(
            record.id,
            "ingest",
            "succeeded" if state == "running" else "blocked",
            {
                "version_id": str(version),
                "reasons": reasons or [],
            },
        )
        record_event(self.db, owner, record.id, "automation.run_started", str(version))
        return record.id

    def exists_for_version(self, version: UUID) -> bool:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(AutomationRunRecord)
                .where(AutomationRunRecord.version_id == version)
            )
            or 0
        ) > 0

    def running_count(self, owner: UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AutomationRunRecord)
                .where(
                    AutomationRunRecord.owner_id == owner, AutomationRunRecord.state == "running"
                )
            )
            or 0
        )

    # --- avance ---

    def try_lock(self, run: UUID) -> bool:
        # Lock de sesión: sobrevive a los commits de los casos de uso que el paso invoca.
        return bool(self.db.scalar(select(func.pg_try_advisory_lock(lock_key(run)))))

    def unlock(self, run: UUID) -> None:
        self.db.execute(select(func.pg_advisory_unlock(lock_key(run))))

    def load(self, run: UUID) -> PipelineRun | None:
        record = self.db.get(AutomationRunRecord, run, populate_existing=True)
        if not record:
            return None
        return PipelineRun(
            id=record.id,
            owner_id=record.owner_id,
            project_id=record.project_id,
            version_id=record.version_id,
            policy_revision_id=record.policy_revision_id,
            state=record.state,
            step=record.step,
            reasons=list(record.reasons),
            **{name: getattr(record, name) for name in REFERENCES},
        )

    def save(self, run: PipelineRun) -> None:
        record = self.db.get(AutomationRunRecord, run.id)
        assert record
        now = datetime.now(UTC)
        changed = record.state != run.state
        record.state, record.step, record.reasons = run.state, run.step, run.reasons
        for name in REFERENCES:
            setattr(record, name, getattr(run, name))
        record.updated_at = now
        if changed and run.state != "running":
            record.finished_at = now
            record_event(self.db, run.owner_id, run.id, f"automation.{run.state}", str(run.id))
        self.db.flush()

    def log(self, run: UUID, step: str, outcome: str, detail: dict[str, Any]) -> None:
        sequence = (
            self.db.scalar(
                select(func.coalesce(func.max(AutomationStepAttemptRecord.sequence), 0)).where(
                    AutomationStepAttemptRecord.run_id == run
                )
            )
            or 0
        ) + 1
        self.db.add(
            AutomationStepAttemptRecord(
                id=uuid4(),
                run_id=run,
                sequence=sequence,
                step=step,
                outcome=outcome,
                detail=detail,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def running_ids(self, limit: int) -> list[UUID]:
        return list(
            self.db.scalars(
                select(AutomationRunRecord.id)
                .where(AutomationRunRecord.state == "running")
                .order_by(AutomationRunRecord.updated_at)
                .limit(limit)
            )
        )

    # --- lectura ---

    def to_view(self, record: AutomationRunRecord, attempts: bool) -> AutomationRunView:
        logged = (
            [
                StepAttempt(
                    sequence=item.sequence,
                    step=item.step,
                    outcome=item.outcome,
                    detail=item.detail,
                    created_at=item.created_at.astimezone(UTC),
                )
                for item in self.db.scalars(
                    select(AutomationStepAttemptRecord)
                    .where(AutomationStepAttemptRecord.run_id == record.id)
                    .order_by(AutomationStepAttemptRecord.sequence)
                )
            ]
            if attempts
            else []
        )
        return AutomationRunView(
            id=record.id,
            project_id=record.project_id,
            version_id=record.version_id,
            policy_revision_id=record.policy_revision_id,
            state=record.state,
            step=record.step,
            reasons=[PipelineReason.model_validate(item) for item in record.reasons],
            **{name: getattr(record, name) for name in REFERENCES},
            created_at=record.created_at.astimezone(UTC),
            updated_at=record.updated_at.astimezone(UTC),
            finished_at=utc(record.finished_at),
            attempts=logged,
        )

    def owned(self, owner: UUID, run: UUID) -> AutomationRunRecord:
        record = self.db.scalar(
            select(AutomationRunRecord).where(
                AutomationRunRecord.id == run, AutomationRunRecord.owner_id == owner
            )
        )
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return record

    def view(self, owner: UUID, run: UUID) -> AutomationRunView:
        return self.to_view(self.owned(owner, run), attempts=True)

    def page(self, owner: UUID, project: UUID, limit: int, offset: int) -> AutomationRunPage:
        where = (AutomationRunRecord.owner_id == owner) & (
            AutomationRunRecord.project_id == project
        )
        total = self.db.scalar(select(func.count()).select_from(AutomationRunRecord).where(where))
        records = self.db.scalars(
            select(AutomationRunRecord)
            .where(where)
            .order_by(AutomationRunRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return AutomationRunPage(
            items=[self.to_view(record, attempts=False) for record in records],
            total=int(total or 0),
        )

    def for_version(self, owner: UUID, version: UUID) -> AutomationRunView | None:
        record = self.db.scalar(
            select(AutomationRunRecord).where(
                AutomationRunRecord.version_id == version, AutomationRunRecord.owner_id == owner
            )
        )
        return self.to_view(record, attempts=True) if record else None

    def attention(self, owner: UUID, limit: int) -> list[AutomationRunView]:
        records = self.db.scalars(
            select(AutomationRunRecord)
            .where(
                AutomationRunRecord.owner_id == owner,
                AutomationRunRecord.state.in_(("needs_review", "failed")),
            )
            .order_by(AutomationRunRecord.updated_at.desc())
            .limit(limit)
        )
        return [self.to_view(record, attempts=False) for record in records]
