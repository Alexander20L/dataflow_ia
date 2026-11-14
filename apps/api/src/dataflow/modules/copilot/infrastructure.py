"""Persistencia del copiloto (migración 0012): conversaciones por proyecto, mensajes
inmutables, acciones registradas sobre una propuesta, solicitudes idempotentes y el registro de
cada llamada al proveedor (sólo metadatos: nunca contenido tabular ni texto del prompt)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.copilot.contracts import (
    CallRecord,
)
from dataflow.platform.database import Base


class ConversationRecord(Base):
    __tablename__ = "copilot_conversations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AICallRecord(Base):
    __tablename__ = "copilot_ai_calls"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("copilot_conversations.id"))
    task: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(80))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    prompt_id: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    context_sha256: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer)
    cache_write_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(16))
    validation: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MessageRecord(Base):
    __tablename__ = "copilot_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_copilot_message_seq"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("copilot_conversations.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    version_id: Mapped[UUID | None] = mapped_column(ForeignKey("dataset_version_records.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    call_id: Mapped[UUID | None] = mapped_column(ForeignKey("copilot_ai_calls.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActionLinkRecord(Base):
    __tablename__ = "copilot_action_links"
    message_id: Mapped[UUID] = mapped_column(ForeignKey("copilot_messages.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    plan_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    metric_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CopilotRequest(Base):
    """Idempotencia: `scope_id` es el proyecto (alta de conversación) o la conversación."""

    __tablename__ = "copilot_requests"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    result_id: Mapped[UUID] = mapped_column(Uuid)


class TextAuditRecord(Base):
    """Auditoría textual guardada (11F, migración 0020): inmutable; una por revisión de dashboard
    y clave de contenido (`audit_key`)."""

    __tablename__ = "copilot_text_audits"
    __table_args__ = (
        UniqueConstraint("dashboard_revision_id", "audit_key", name="uq_copilot_text_audit_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    dashboard_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("dashboard_revisions.id"), index=True
    )
    audit_key: Mapped[str] = mapped_column(String(64))
    result_sha256: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(80))
    prompt_id: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    call_id: Mapped[UUID] = mapped_column(ForeignKey("copilot_ai_calls.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLCopilotRepository:
    """Registro de llamadas a la IA y consumo (presupuestos). Las demás tablas del copiloto
    (conversaciones, mensajes, auditorías textuales) se conservan sin uso desde la Fase 13."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def log_call(self, record: CallRecord) -> UUID:
        identifier = uuid4()
        self.db.add(
            AICallRecord(
                id=identifier,
                owner_id=record.owner_id,
                project_id=record.project_id,
                conversation_id=record.conversation_id,
                task=record.task,
                provider=record.provider,
                model=record.model,
                parameters=record.parameters,
                prompt_id=record.prompt_id,
                prompt_version=record.prompt_version,
                context_sha256=record.context_sha256,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cache_read_tokens=record.cache_read_tokens,
                cache_write_tokens=record.cache_write_tokens,
                cost_usd=record.cost_usd,
                latency_ms=record.latency_ms,
                outcome=record.outcome,
                validation=record.validation,
                error_code=record.error_code,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()
        return identifier

    def user_tokens_since(self, owner: UUID, since: datetime) -> int:
        total = self.db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        AICallRecord.input_tokens
                        + AICallRecord.output_tokens
                        + AICallRecord.cache_read_tokens
                        + AICallRecord.cache_write_tokens
                    ),
                    0,
                )
            ).where(AICallRecord.owner_id == owner, AICallRecord.created_at >= since)
        )
        return int(total or 0)

    def project_cost_since(self, project: UUID, since: datetime) -> Decimal:
        total = self.db.scalar(
            select(func.coalesce(func.sum(AICallRecord.cost_usd), 0)).where(
                AICallRecord.project_id == project, AICallRecord.created_at >= since
            )
        )
        return Decimal(total or 0).quantize(Decimal("0.000001"))
