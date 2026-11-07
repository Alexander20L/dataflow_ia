"""Persistencia de la sesión de análisis (Fase 11A): la sesión es una referencia mutable con
`revision`; cada selección de fuente es una fila inmutable (trigger)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.analysis_sessions.contracts import (
    ReadyInput,
    SessionInput,
    SessionState,
)
from dataflow.modules.audit.public import record_event
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError

NOT_FOUND = ("ANALYSIS_SESSION_NOT_FOUND", "Sesión de análisis no encontrada.", 404)


class AnalysisSessionRecord(Base):
    __tablename__ = "analysis_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    revision: Mapped[int]
    head_input_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "analysis_session_input_revisions.id",
            use_alter=True,
            name="fk_analysis_session_head",
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisSessionInputRecord(Base):
    __tablename__ = "analysis_session_input_revisions"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_analysis_session_input_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_sessions.id"), index=True)
    revision: Mapped[int]
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    version_number: Mapped[int]
    version_kind: Mapped[str] = mapped_column(String(16))
    file_name: Mapped[str] = mapped_column(String(255))
    table_artifact_id: Mapped[UUID] = mapped_column(ForeignKey("execution_artifacts.id"))
    table_sha256: Mapped[str] = mapped_column(String(64))
    selected_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def state(record: AnalysisSessionRecord) -> SessionState:
    return SessionState(
        id=record.id,
        project_id=record.project_id,
        owner_id=record.owner_id,
        revision=record.revision,
        created_at=record.created_at.astimezone(UTC),
    )


def view(record: AnalysisSessionInputRecord) -> SessionInput:
    return SessionInput(
        revision=record.revision,
        version_id=record.version_id,
        version_number=record.version_number,
        version_kind="derived" if record.version_kind == "derived" else "imported",
        file_name=record.file_name,
        table_artifact_id=record.table_artifact_id,
        table_sha256=record.table_sha256,
        selected_by=record.selected_by,
        selected_at=record.selected_at.astimezone(UTC),
    )


class SQLAnalysisSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def by_project(self, owner: UUID, project: UUID) -> SessionState | None:
        record = self.db.scalar(
            select(AnalysisSessionRecord).where(
                AnalysisSessionRecord.project_id == project,
                AnalysisSessionRecord.owner_id == owner,
            )
        )
        return state(record) if record else None

    def create(self, owner: UUID, project: UUID) -> SessionState:
        now = datetime.now(UTC)
        record = AnalysisSessionRecord(
            id=uuid4(),
            project_id=project,
            owner_id=owner,
            revision=0,
            head_input_id=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        return state(record)

    def get(self, owner: UUID, session: UUID, lock: bool = False) -> SessionState:
        statement = select(AnalysisSessionRecord).where(
            AnalysisSessionRecord.id == session, AnalysisSessionRecord.owner_id == owner
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if not record:
            raise ApplicationError(*NOT_FOUND)
        return state(record)

    def head(self, session: SessionState) -> SessionInput | None:
        record = self.db.get(AnalysisSessionRecord, session.id)
        if not record or not record.head_input_id:
            return None
        head = self.db.get(AnalysisSessionInputRecord, record.head_input_id)
        return view(head) if head else None

    def append(
        self, session: SessionState, ready: ReadyInput, actor: UUID, correlation: str
    ) -> SessionInput:
        record = self.db.get(AnalysisSessionRecord, session.id)
        assert record
        now = datetime.now(UTC)
        selection = AnalysisSessionInputRecord(
            id=uuid4(),
            session_id=record.id,
            revision=record.revision + 1,
            version_id=ready.version_id,
            version_number=ready.version_number,
            version_kind=ready.version_kind,
            file_name=ready.file_name,
            table_artifact_id=ready.table_artifact_id,
            table_sha256=ready.table_sha256,
            selected_by=actor,
            selected_at=now,
        )
        self.db.add(selection)
        self.db.flush()
        record.revision, record.head_input_id, record.updated_at = (
            selection.revision,
            selection.id,
            now,
        )
        record_event(self.db, actor, record.id, "analysis_session.input_selected", correlation)
        self.db.flush()
        return view(selection)

    def history(
        self, session: SessionState, limit: int, offset: int
    ) -> tuple[list[SessionInput], int]:
        where = AnalysisSessionInputRecord.session_id == session.id
        total = self.db.scalar(
            select(func.count()).select_from(AnalysisSessionInputRecord).where(where)
        )
        records = self.db.scalars(
            select(AnalysisSessionInputRecord)
            .where(where)
            .order_by(AnalysisSessionInputRecord.revision.desc())
            .limit(limit)
            .offset(offset)
        )
        return [view(record) for record in records], int(total or 0)
