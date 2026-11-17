from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Select,
    String,
    UniqueConstraint,
    Uuid,
    and_,
    case,
    exists,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, aliased, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.contracts import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Execution,
    Lease,
    PlanBinding,
    PlanRevision,
    RunKind,
    RunState,
    UserPlan,
)
from dataflow.modules.executions.domain import BACKGROUND_KINDS, RUNNING_LIMIT, failure_state
from dataflow.platform.canonical import digest
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError

CLAIM_LOCK = 0x0DF1_3C00


class PlanRecord(Base):
    __tablename__ = "execution_plan_revisions"
    __table_args__ = (UniqueConstraint("family_id", "revision", name="uq_execution_plan_revision"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(Uuid)
    revision: Mapped[int]
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanBindingRecord(Base):
    """Vínculo 1:1 de un plan de usuario con su proyecto y entrada exacta.

    Tabla aparte para que los planes de sistema y el código 0.5 no dependan de columnas nuevas.
    """

    __tablename__ = "execution_plan_bindings"
    plan_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plan_revisions.id"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    input_artifact_id: Mapped[UUID] = mapped_column(ForeignKey("execution_artifacts.id"))
    input_artifact_sha256: Mapped[str] = mapped_column(String(64))
    semantic_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("semantic_revisions.id"))


class ExecutionRecord(Base):
    __tablename__ = "execution_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "kind", "request_key", name="uq_execution_request"),
        Index("ix_execution_run_queue", "state", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_plan_revisions.id"))
    kind: Mapped[str] = mapped_column(String(30))
    request_key: Mapped[UUID] = mapped_column(Uuid)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    input_artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("execution_artifacts.id", use_alter=True, name="fk_run_input_artifact")
    )
    input_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20))
    attempt_count: Mapped[int]
    active_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("execution_attempts.id", use_alter=True, name="fk_run_active_attempt")
    )
    row_count: Mapped[int | None]
    column_count: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(300))
    reproducibility: Mapped[str] = mapped_column(String(30))
    legacy_separator: Mapped[str | None] = mapped_column(String(8))
    correlation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttemptRecord(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("execution_id", "number", name="uq_execution_attempt_number"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), index=True)
    number: Mapped[int]
    state: Mapped[str] = mapped_column(String(20))
    fencing_token: Mapped[UUID] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    environment: Mapped[dict[str, Any]] = mapped_column(JSON)
    environment_sha256: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(300))


class ErrorDetailRecord(Base):
    """Detalle estructurado de un intento fallido (p. ej. valores que no convierten). Uno por
    intento, inmutable. Executions no interpreta su contenido."""

    __tablename__ = "execution_error_details"
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("execution_attempts.id"), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArtifactRecord(Base):
    __tablename__ = "execution_artifacts"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_id", "slot", name="uq_execution_artifact_slot"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), index=True)
    attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_attempts.id"))
    step_id: Mapped[str] = mapped_column(String(80))
    slot: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_objects.id"))
    row_count: Mapped[int | None]
    column_count: Mapped[int | None]
    column_schema: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    logical_content_sha256: Mapped[str | None] = mapped_column(String(64))


def plan_view(plan: PlanRecord) -> PlanRevision:
    return PlanRevision(
        plan.id,
        plan.family_id,
        plan.revision,
        deepcopy(plan.content),
        plan.content_sha256,
        plan.created_by,
        plan.created_at,
    )


class SQLExecutionRepository:
    def __init__(self, db: Session, objects: Datasets) -> None:
        self.db, self.objects = db, objects

    def view(self, record: ExecutionRecord) -> Execution:
        plan = self.db.get(PlanRecord, record.plan_id) if record.plan_id else None
        snapshot = plan_view(plan) if plan else None
        return Execution(
            record.id,
            record.project_id,
            record.owner_id,
            record.version_id,
            cast(RunKind, record.kind),
            cast(RunState, record.state),
            record.attempt_count,
            snapshot,
            record.input_artifact_id,
            record.input_artifact_sha256,
            record.row_count,
            record.column_count,
            record.error_code,
            record.error_message,
            cast(Literal["complete", "legacy_partial"], record.reproducibility),
            record.created_at,
            record.finished_at,
            record.request_key,
        )

    def find_request(
        self, owner: UUID, project: UUID, kind: RunKind, key: UUID, fingerprint: str
    ) -> Execution | None:
        record = self.db.scalar(
            select(ExecutionRecord).where(
                ExecutionRecord.owner_id == owner,
                ExecutionRecord.project_id == project,
                ExecutionRecord.kind == kind,
                ExecutionRecord.request_key == key,
            )
        )
        if not record:
            return None
        if record.request_fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave ya corresponde a otra solicitud.", 409
            )
        return self.view(record)

    def active_count(
        self, owner: UUID, project: UUID | None = None, kind: RunKind | None = None
    ) -> int:
        query = (
            select(func.count())
            .select_from(ExecutionRecord)
            .where(
                ExecutionRecord.owner_id == owner, ExecutionRecord.state.in_(["queued", "running"])
            )
        )
        if project:
            query = query.where(ExecutionRecord.project_id == project)
        if kind:
            query = query.where(ExecutionRecord.kind == kind)
        return int(self.db.scalar(query) or 0)

    def counts(self, owner: UUID, kind: RunKind) -> dict[str, int]:
        return {
            state: int(count)
            for state, count in self.db.execute(
                select(ExecutionRecord.state, func.count())
                .where(ExecutionRecord.owner_id == owner, ExecutionRecord.kind == kind)
                .group_by(ExecutionRecord.state)
            )
        }

    def enqueue(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        kind: RunKind,
        key: UUID,
        fingerprint: str,
        plan: PlanRevision,
        correlation: str,
        input_artifact: UUID | None = None,
        input_sha256: str | None = None,
    ) -> Execution:
        self.add_plan(plan)
        return self.queue(
            owner,
            project,
            version,
            kind,
            key,
            fingerprint,
            plan.id,
            correlation,
            input_artifact,
            input_sha256,
        )

    def enqueue_existing_plan(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        key: UUID,
        fingerprint: str,
        plan: UUID,
        correlation: str,
        input_artifact: UUID,
        input_sha256: str,
        kind: RunKind = "plan",
    ) -> Execution:
        return self.queue(
            owner,
            project,
            version,
            kind,
            key,
            fingerprint,
            plan,
            correlation,
            input_artifact,
            input_sha256,
        )

    def add_plan(self, plan: PlanRevision) -> None:
        self.db.add(
            PlanRecord(
                id=plan.id,
                family_id=plan.family_id,
                revision=plan.revision,
                content=plan.content,
                content_sha256=plan.content_sha256,
                created_by=plan.created_by,
                created_at=plan.created_at,
            )
        )
        self.db.flush()

    def save_plan_revision(self, plan: PlanRevision, binding: PlanBinding) -> None:
        self.add_plan(plan)
        self.db.add(
            PlanBindingRecord(
                plan_revision_id=plan.id,
                project_id=binding.project_id,
                input_artifact_id=binding.input_artifact_id,
                input_artifact_sha256=binding.input_artifact_sha256,
                semantic_revision_id=binding.semantic_revision_id,
            )
        )
        self.db.flush()

    def user_plans(self, owner: UUID) -> Select[PlanRecord, PlanBindingRecord]:
        return (
            select(PlanRecord, PlanBindingRecord)
            .join(PlanBindingRecord, PlanBindingRecord.plan_revision_id == PlanRecord.id)
            .where(PlanRecord.created_by == owner)
        )

    def user_plan(self, plan: PlanRecord, binding: PlanBindingRecord) -> UserPlan:
        head = self.db.scalar(
            select(func.max(PlanRecord.revision)).where(PlanRecord.family_id == plan.family_id)
        )
        return UserPlan(
            plan_view(plan),
            PlanBinding(
                binding.project_id,
                binding.input_artifact_id,
                binding.input_artifact_sha256,
                binding.semantic_revision_id,
            ),
            int(head or plan.revision),
        )

    def plan_revision(self, owner: UUID, revision: UUID) -> UserPlan:
        row = self.db.execute(self.user_plans(owner).where(PlanRecord.id == revision)).first()
        if not row:
            raise ApplicationError("PLAN_NOT_FOUND", "Plan no encontrado.", 404)
        return self.user_plan(row[0], row[1])

    def lock_plan_family(self, owner: UUID, family: UUID) -> UserPlan:
        # Se bloquea siempre la revisión 1 (fila estable de la familia) y después se lee la
        # cabeza: dos guardados concurrentes se serializan y el segundo ve la cabeza nueva.
        root = self.db.scalar(
            self.user_plans(owner)
            .where(PlanRecord.family_id == family, PlanRecord.revision == 1)
            .with_for_update(of=PlanRecord)
        )
        if not root:
            raise ApplicationError("PLAN_NOT_FOUND", "Plan no encontrado.", 404)
        row = self.db.execute(
            self.user_plans(owner)
            .where(PlanRecord.family_id == family)
            .order_by(PlanRecord.revision.desc())
            .limit(1)
        ).one()
        return self.user_plan(row[0], row[1])

    def plans_for_project(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[UserPlan], int]:
        heads = (
            select(PlanRecord.family_id, func.max(PlanRecord.revision).label("revision"))
            .join(PlanBindingRecord, PlanBindingRecord.plan_revision_id == PlanRecord.id)
            .where(PlanRecord.created_by == owner, PlanBindingRecord.project_id == project)
            .group_by(PlanRecord.family_id)
            .subquery()
        )
        total = int(self.db.scalar(select(func.count()).select_from(heads)) or 0)
        rows = self.db.execute(
            self.user_plans(owner)
            .join(
                heads,
                and_(
                    heads.c.family_id == PlanRecord.family_id,
                    heads.c.revision == PlanRecord.revision,
                ),
            )
            .order_by(PlanRecord.created_at.desc(), PlanRecord.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [self.user_plan(row[0], row[1]) for row in rows], total

    def queue(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        kind: RunKind,
        key: UUID,
        fingerprint: str,
        plan: UUID,
        correlation: str,
        input_artifact: UUID | None,
        input_sha256: str | None,
    ) -> Execution:
        now = datetime.now(UTC)
        record = ExecutionRecord(
            id=uuid4(),
            version_id=version,
            project_id=project,
            owner_id=owner,
            plan_id=plan,
            kind=kind,
            request_key=key,
            request_fingerprint=fingerprint,
            input_artifact_id=input_artifact,
            input_artifact_sha256=input_sha256,
            state="queued",
            attempt_count=0,
            reproducibility="complete",
            correlation_id=correlation,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        record_event(self.db, owner, record.id, "execution.queued", correlation)
        return self.view(record)

    def get(self, owner: UUID, execution: UUID) -> Execution:
        record = self.db.scalar(
            select(ExecutionRecord).where(
                ExecutionRecord.id == execution, ExecutionRecord.owner_id == owner
            )
        )
        if not record:
            raise ApplicationError("EXECUTION_NOT_FOUND", "Ejecución no encontrada.", 404)
        return self.view(record)

    def for_version(self, owner: UUID, version: UUID) -> list[Execution]:
        return [
            self.view(r)
            for r in self.db.scalars(
                select(ExecutionRecord)
                .where(ExecutionRecord.owner_id == owner, ExecutionRecord.version_id == version)
                .order_by(ExecutionRecord.created_at.desc(), ExecutionRecord.id.desc())
                .limit(50)
            )
        ]

    def artifact_view(self, record: ArtifactRecord, owner: UUID) -> Artifact:
        return Artifact(
            record.id,
            record.execution_id,
            record.version_id,
            record.attempt_id,
            record.step_id,
            record.slot,
            cast(ArtifactKind, record.kind),
            self.objects.object(owner, record.object_id),
            record.row_count,
            record.column_count,
            deepcopy(record.column_schema),
            record.logical_content_sha256,
        )

    def representations(self, owner: UUID, version: UUID) -> list[Artifact]:
        records = self.db.scalars(
            select(ArtifactRecord)
            .join(ExecutionRecord, ExecutionRecord.id == ArtifactRecord.execution_id)
            .where(
                ArtifactRecord.version_id == version,
                ArtifactRecord.kind == "table",
                ExecutionRecord.owner_id == owner,
                ExecutionRecord.state == "succeeded",
            )
            .order_by(ExecutionRecord.created_at.desc(), ArtifactRecord.id)
            .limit(100)
        )
        return [self.artifact_view(record, owner) for record in records]

    def artifact(self, owner: UUID, artifact: UUID) -> Artifact:
        row = self.db.execute(
            select(ArtifactRecord, ExecutionRecord)
            .join(ExecutionRecord, ExecutionRecord.id == ArtifactRecord.execution_id)
            .where(
                ArtifactRecord.id == artifact,
                ExecutionRecord.owner_id == owner,
                ExecutionRecord.state == "succeeded",
            )
        ).first()
        if not row:
            raise ApplicationError("ARTIFACT_NOT_FOUND", "Artefacto publicado no encontrado.", 404)
        return self.artifact_view(row[0], owner)

    def artifacts(self, owner: UUID, execution: UUID) -> list[Artifact]:
        run = self.get(owner, execution)
        if run.state != "succeeded":
            return []
        return [
            self.artifact_view(row, owner)
            for row in self.db.scalars(
                select(ArtifactRecord)
                .where(ArtifactRecord.execution_id == execution)
                .order_by(ArtifactRecord.step_id, ArtifactRecord.slot)
            )
        ]

    def error_details(self, owner: UUID, execution: UUID) -> tuple[str, dict[str, Any]] | None:
        self.get(owner, execution)  # propietario o 404
        row = self.db.scalars(
            select(ErrorDetailRecord)
            .where(ErrorDetailRecord.execution_id == execution)
            .order_by(ErrorDetailRecord.created_at.desc())
            .limit(1)
        ).first()
        return (row.code, row.details) if row else None

    def attempts(self, owner: UUID, execution: UUID) -> list[dict[str, Any]]:
        self.get(owner, execution)
        return [
            {
                "id": str(a.id),
                "number": a.number,
                "state": a.state,
                "environment": a.environment,
                "environment_sha256": a.environment_sha256,
                "started_at": a.started_at,
                "finished_at": a.finished_at,
                "error_code": a.error_code,
                "error_message": a.error_message,
            }
            for a in self.db.scalars(
                select(AttemptRecord)
                .where(AttemptRecord.execution_id == execution)
                .order_by(AttemptRecord.number)
            )
        ]

    def cancel(self, owner: UUID, execution: UUID) -> Execution:
        record = self.db.scalar(
            select(ExecutionRecord)
            .where(ExecutionRecord.id == execution, ExecutionRecord.owner_id == owner)
            .with_for_update()
        )
        if not record:
            raise ApplicationError("EXECUTION_NOT_FOUND", "Ejecución no encontrada.", 404)
        if record.state not in {"queued", "running"}:
            raise ApplicationError("EXECUTION_FINISHED", "La ejecución ya ha terminado.", 409)
        now = datetime.now(UTC)
        if record.active_attempt_id:
            attempt = self.db.get(AttemptRecord, record.active_attempt_id)
            assert attempt
            attempt.state, attempt.finished_at, attempt.lease_until = "cancelled", now, None
        record.state, record.active_attempt_id, record.finished_at, record.updated_at = (
            "cancelled",
            None,
            now,
            now,
        )
        record_event(self.db, owner, execution, "execution.cancelled", record.correlation_id)
        self.db.flush()
        return self.view(record)

    def claim(self, kinds: set[RunKind], environment: dict[str, Any]) -> Lease | None:
        now = datetime.now(UTC)
        # Serializa las reclamaciones entre workers para que los límites de concurrencia se
        # evalúen sobre un estado estable (la transacción de reclamación es corta).
        self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CLAIM_LOCK})
        expired = select(AttemptRecord.execution_id).where(
            AttemptRecord.state == "running", AttemptRecord.lease_until < now
        )
        other = aliased(ExecutionRecord)
        live = and_(other.state == "running", other.id.not_in(expired))
        owner_running = (
            select(func.count())
            .select_from(other)
            .where(other.owner_id == ExecutionRecord.owner_id, live)
            .scalar_subquery()
        )
        project_importing = exists().where(
            other.project_id == ExecutionRecord.project_id,
            other.kind == "csv_import",
            live,
        )
        # Un trabajo en cola espera si su propietario ya tiene RUNNING_LIMIT en marcha o, si
        # es una importación, mientras otra importación del mismo proyecto se procesa (las
        # versiones se procesan en orden de llegada). Una concesión vencida se recupera siempre.
        waiting = or_(
            owner_running >= RUNNING_LIMIT,
            and_(ExecutionRecord.kind == "csv_import", project_importing),
        )
        record = self.db.scalar(
            select(ExecutionRecord)
            .where(
                ExecutionRecord.kind.in_(kinds),
                ExecutionRecord.plan_id.is_not(None),
                or_(
                    and_(ExecutionRecord.state == "queued", ~waiting),
                    and_(ExecutionRecord.state == "running", ExecutionRecord.id.in_(expired)),
                ),
            )
            # Trabajo de fondo (investigación, Fase 16) después de lo demás: nunca retrasa una
            # carga, una limpieza o un plan del mismo propietario. Fase 21: el informe, el
            # último de todos, para incluir el dashboard de su carga.
            .order_by(
                case(
                    (ExecutionRecord.kind == "automatic_report", 2),
                    (ExecutionRecord.kind.in_(BACKGROUND_KINDS), 1),
                    else_=0,
                ),
                ExecutionRecord.created_at,
                ExecutionRecord.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not record:
            return None
        snapshot = self.view(record)
        assert snapshot.plan
        if digest("plan", snapshot.plan.content) != snapshot.plan.content_sha256:
            record.state, record.error_code, record.error_message = (
                "failed",
                "PLAN_HASH_MISMATCH",
                "El plan inmutable no coincide.",
            )
            record.finished_at = now
            self.db.flush()
            return None
        config = snapshot.plan.config
        if record.active_attempt_id:
            previous = self.db.get(AttemptRecord, record.active_attempt_id)
            assert previous
            previous.state, previous.finished_at, previous.lease_until = "expired", now, None
            previous.error_code = "LEASE_EXPIRED"
            record_event(
                self.db,
                record.owner_id,
                record.id,
                "execution.lease_expired",
                record.correlation_id,
            )
        if record.attempt_count >= config.max_attempts:
            record.state, record.active_attempt_id, record.finished_at = "failed", None, now
            record.error_code, record.error_message = (
                "ATTEMPTS_EXHAUSTED",
                "Se agotaron los intentos de recuperación del trabajo.",
            )
            record_event(
                self.db,
                record.owner_id,
                record.id,
                "execution.attempts_exhausted",
                record.correlation_id,
            )
            self.db.flush()
            return None
        record.attempt_count += 1
        effective_environment = {
            **environment,
            "config_sha256": digest("config", config.model_dump()),
        }
        attempt = AttemptRecord(
            id=uuid4(),
            execution_id=record.id,
            number=record.attempt_count,
            state="running",
            fencing_token=uuid4(),
            lease_until=now + timedelta(seconds=config.lease_seconds),
            environment=effective_environment,
            environment_sha256=digest("environment", effective_environment),
            started_at=now,
        )
        self.db.add(attempt)
        self.db.flush()
        record.active_attempt_id, record.state, record.updated_at = attempt.id, "running", now
        record_event(
            self.db,
            record.owner_id,
            record.id,
            f"execution.attempt_{attempt.number}.started",
            record.correlation_id,
        )
        self.db.flush()
        return Lease(self.view(record), attempt.id, attempt.fencing_token, effective_environment)

    def current(self, lease: Lease) -> tuple[ExecutionRecord, AttemptRecord] | None:
        record = self.db.scalar(
            select(ExecutionRecord)
            .where(
                ExecutionRecord.id == lease.execution_id,
                ExecutionRecord.state == "running",
                ExecutionRecord.active_attempt_id == lease.attempt_id,
            )
            .with_for_update()
        )
        if not record:
            return None
        attempt = self.db.scalar(
            select(AttemptRecord)
            .where(
                AttemptRecord.id == lease.attempt_id,
                AttemptRecord.state == "running",
                AttemptRecord.fencing_token == lease.token,
                AttemptRecord.lease_until > datetime.now(UTC),
            )
            .with_for_update()
        )
        return (record, attempt) if attempt else None

    def stage(self, lease: Lease, outputs: list[ArtifactOutput]) -> list[Artifact] | None:
        current = self.current(lease)
        if not current:
            return None
        record, _ = current
        result = []
        for output in outputs:
            self.objects.register_object(record.owner_id, output.content, output.media_type)
            artifact = ArtifactRecord(
                id=output.id,
                version_id=output.version_id or record.version_id,
                execution_id=record.id,
                attempt_id=lease.attempt_id,
                step_id=output.step_id,
                slot=output.slot,
                kind=output.kind,
                object_id=output.content.object_id,
                row_count=output.row_count,
                column_count=output.column_count,
                column_schema=output.columns,
                logical_content_sha256=output.logical_content_sha256,
            )
            self.db.add(artifact)
            result.append(self.artifact_view(artifact, record.owner_id))
        if outputs:
            record.row_count, record.column_count = outputs[0].row_count, outputs[0].column_count
        self.db.flush()
        return result

    def succeed(self, lease: Lease) -> bool:
        current = self.current(lease)
        if not current:
            return False
        record, attempt = current
        now = datetime.now(UTC)
        attempt.state, attempt.finished_at, attempt.lease_until = "succeeded", now, None
        record.state, record.active_attempt_id, record.finished_at, record.updated_at = (
            "succeeded",
            None,
            now,
            now,
        )
        record.error_code = record.error_message = None
        record_event(
            self.db, record.owner_id, record.id, "execution.succeeded", record.correlation_id
        )
        self.db.flush()
        return True

    def fail(
        self,
        lease: Lease,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        current = self.current(lease)
        if not current:
            return
        record, attempt = current
        assert lease.execution.plan
        now = datetime.now(UTC)
        if details is not None:
            self.db.add(
                ErrorDetailRecord(
                    attempt_id=attempt.id,
                    execution_id=record.id,
                    code=code,
                    details=details,
                    created_at=now,
                )
            )
        attempt.state, attempt.finished_at, attempt.lease_until = "failed", now, None
        attempt.error_code, attempt.error_message = code, message[:300]
        record.state = failure_state(
            record.attempt_count, lease.execution.plan.config.max_attempts, retryable
        )
        record.active_attempt_id, record.updated_at = None, now
        record.finished_at = now if record.state == "failed" else None
        record.error_code, record.error_message = code, message[:300]
        record_event(
            self.db,
            record.owner_id,
            record.id,
            "execution.retry_queued" if record.state == "queued" else "execution.failed",
            record.correlation_id,
        )
        self.db.flush()
