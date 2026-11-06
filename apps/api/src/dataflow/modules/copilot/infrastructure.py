"""Persistencia del copiloto (migración 0012): conversaciones por proyecto, mensajes
inmutables, acciones registradas sobre una propuesta, solicitudes idempotentes y el registro de
cada llamada al proveedor (sólo metadatos: nunca contenido tabular ni texto del prompt)."""

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
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

from dataflow.modules.audit.public import record_event
from dataflow.modules.copilot.contracts import (
    ActionLink,
    AssistantContent,
    CallRecord,
    Conversation,
    Message,
)
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


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


NOT_FOUND = ("CONVERSATION_NOT_FOUND", "Conversación no encontrada.", 404)


def conversation_view(record: ConversationRecord) -> Conversation:
    return Conversation(
        id=record.id, project_id=record.project_id, title=record.title, created_at=record.created_at
    )


class SQLCopilotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_conversation(self, owner: UUID, project: UUID, title: str) -> Conversation:
        record = ConversationRecord(
            id=uuid4(),
            project_id=project,
            owner_id=owner,
            title=title,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        return conversation_view(record)

    def conversations(self, owner: UUID, project: UUID) -> list[Conversation]:
        records = self.db.scalars(
            select(ConversationRecord)
            .where(ConversationRecord.owner_id == owner, ConversationRecord.project_id == project)
            .order_by(ConversationRecord.created_at.desc(), ConversationRecord.id)
        )
        return [conversation_view(r) for r in records]

    def conversation(self, owner: UUID, conversation: UUID) -> Conversation:
        record = self.db.get(ConversationRecord, conversation)
        if record is None or record.owner_id != owner:
            raise ApplicationError(*NOT_FOUND)
        return conversation_view(record)

    def lock_conversation(self, owner: UUID, conversation: UUID) -> Conversation:
        record = self.db.scalar(
            select(ConversationRecord)
            .where(ConversationRecord.id == conversation, ConversationRecord.owner_id == owner)
            .with_for_update()
        )
        if record is None:
            raise ApplicationError(*NOT_FOUND)
        return conversation_view(record)

    def links(self, messages: list[UUID]) -> dict[UUID, list[ActionLink]]:
        result: dict[UUID, list[ActionLink]] = {m: [] for m in messages}
        if not messages:
            return result
        for record in self.db.scalars(
            select(ActionLinkRecord)
            .where(ActionLinkRecord.message_id.in_(messages))
            .order_by(ActionLinkRecord.created_at, ActionLinkRecord.kind)
        ):
            result[record.message_id].append(
                ActionLink(
                    kind=record.kind,
                    plan_revision_id=record.plan_revision_id,
                    execution_id=record.execution_id,
                    metric_revision_id=record.metric_revision_id,
                    created_at=record.created_at,
                )
            )
        return result

    def view(self, record: MessageRecord, links: list[ActionLink]) -> Message:
        content = deepcopy(record.content)
        role: Literal["user", "assistant"] = "user" if record.role == "user" else "assistant"
        return Message(
            id=record.id,
            conversation_id=record.conversation_id,
            seq=record.seq,
            role=role,
            version_id=record.version_id,
            text=content.get("text") if role == "user" else None,
            assistant=AssistantContent.model_validate(content) if role == "assistant" else None,
            links=links,
            created_at=record.created_at,
        )

    def messages(self, conversation: UUID) -> list[Message]:
        records = list(
            self.db.scalars(
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation)
                .order_by(MessageRecord.seq)
            )
        )
        links = self.links([r.id for r in records])
        return [self.view(r, links[r.id]) for r in records]

    def message(self, owner: UUID, message: UUID) -> Message:
        record = self.db.get(MessageRecord, message)
        if record is None:
            raise ApplicationError("MESSAGE_NOT_FOUND", "Mensaje no encontrado.", 404)
        conversation = self.db.get(ConversationRecord, record.conversation_id)
        if conversation is None or conversation.owner_id != owner:
            raise ApplicationError("MESSAGE_NOT_FOUND", "Mensaje no encontrado.", 404)
        return self.view(record, self.links([record.id])[record.id])

    def append(
        self,
        conversation: UUID,
        role: Literal["user", "assistant"],
        version: UUID | None,
        content: dict[str, Any],
        call: UUID | None,
        correlation: str,
    ) -> Message:
        last = self.db.scalar(
            select(func.max(MessageRecord.seq)).where(MessageRecord.conversation_id == conversation)
        )
        record = MessageRecord(
            id=uuid4(),
            conversation_id=conversation,
            seq=(last or 0) + 1,
            role=role,
            version_id=version,
            content=content,
            call_id=call,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        owner = self.db.get(ConversationRecord, conversation)
        assert owner
        if role == "assistant":
            record_event(self.db, owner.owner_id, record.id, "copilot.message.created", correlation)
        return self.view(record, [])

    def replay(self, owner: UUID, scope: UUID, key: UUID, fingerprint: str) -> UUID | None:
        request = self.db.get(CopilotRequest, (owner, scope, key))
        if request is None:
            return None
        if request.fingerprint != fingerprint:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT", "La clave ya corresponde a otra solicitud.", 409
            )
        return request.result_id

    def remember(self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, result: UUID) -> None:
        self.db.add(
            CopilotRequest(
                owner_id=owner,
                scope_id=scope,
                request_key=key,
                fingerprint=fingerprint,
                result_id=result,
            )
        )
        self.db.flush()

    def add_link(self, message: UUID, link: ActionLink) -> None:
        self.db.add(
            ActionLinkRecord(
                message_id=message,
                kind=link.kind,
                plan_revision_id=link.plan_revision_id,
                execution_id=link.execution_id,
                metric_revision_id=link.metric_revision_id,
                created_at=link.created_at,
            )
        )
        self.db.flush()

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
