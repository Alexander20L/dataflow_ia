"""Casos de uso del copiloto (Fase 10, ADR-022).

El copiloto no tiene poderes propios: traduce una petición a una propuesta estructurada, la
valida con planning y la muestra. Ejecutar una consulta, crear una métrica o abrir un plan de
limpieza son acciones explícitas de la persona y pasan por los mismos casos de uso que la
interfaz; un plan de limpieza nunca se aplica sin la vista previa y la aprobación de la Fase 5.
Ninguna cifra sale del modelo: las explicaciones citan evidencias y el servidor las sustituye.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID, uuid5

from pydantic import BaseModel

from dataflow.integrations.ai import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResult,
    estimated_cost,
)
from dataflow.modules.copilot import prompts
from dataflow.modules.copilot.contracts import (
    ActionLink,
    ActionResult,
    AssistantContent,
    CallRecord,
    ClarificationCard,
    CleaningCard,
    Conversation,
    ConversationView,
    CopilotRepository,
    CopilotSources,
    CopilotStatus,
    CopilotUsage,
    ExplainOutput,
    MetricCard,
    MetricFact,
    ProposalProblem,
    QueryCard,
    Segment,
    TableContext,
    TurnOutput,
    TurnResponse,
)
from dataflow.modules.copilot.domain import (
    MAX_HISTORY,
    MAX_RESULT_CELLS,
    authorized_context,
    clarification_target,
    plain_text,
    resolve_cleaning,
    resolve_metric,
    resolve_query,
    result_context,
    serialize,
    verify_explanation,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

DISCARDED = "La respuesta del copiloto no era válida y se descartó."
UNAVAILABLE_MESSAGES = {
    "disabled": "El copiloto de IA está desactivado en este servidor.",
    "missing_key": "El copiloto de IA no tiene una clave configurada.",
}


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@dataclass(frozen=True)
class CopilotConfig:
    provider: str  # disabled · fake · anthropic
    unavailable: Literal["disabled", "missing_key"] | None
    model: str | None
    user_daily_tokens: int
    project_monthly_cost_usd: Decimal
    max_output_tokens: int


def now_utc() -> datetime:
    return datetime.now(UTC)


class CopilotService:
    def __init__(
        self,
        repository: CopilotRepository,
        sources: CopilotSources,
        provider: AIProvider | None,
        config: CopilotConfig,
        uow: UnitOfWork,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.repository, self.sources, self.provider = repository, sources, provider
        self.config, self.uow, self.clock = config, uow, clock

    # --- Estado y conversaciones ---------------------------------------------------------------

    def status(self, owner: UUID, project: UUID) -> CopilotStatus:
        self.sources.require_project(owner, project)
        usage = self.usage(owner, project)
        reason: Literal["disabled", "missing_key", "budget_exhausted"] | None = (
            self.config.unavailable
        )
        if reason is None and self.exhausted(usage):
            reason = "budget_exhausted"
        return CopilotStatus(
            available=reason is None and self.provider is not None,
            reason=reason,
            provider=self.config.provider,
            model=self.config.model,
            prompt_version=prompts.PROMPT_VERSION,
            usage=usage,
        )

    def create_conversation(
        self, owner: UUID, project: UUID, title: str, key: UUID
    ) -> Conversation:
        try:
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest("copilot_conversation", {"project": str(project), "title": title})
            replayed = self.repository.replay(owner, project, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return self.repository.conversation(owner, replayed)
            conversation = self.repository.create_conversation(owner, project, title)
            self.repository.remember(owner, project, key, fingerprint, conversation.id)
            self.uow.commit()
            return conversation
        except Exception:
            self.uow.rollback()
            raise

    def conversations(self, owner: UUID, project: UUID) -> list[Conversation]:
        self.sources.require_project(owner, project)
        return self.repository.conversations(owner, project)

    def view(self, owner: UUID, conversation: UUID) -> ConversationView:
        value = self.repository.conversation(owner, conversation)
        self.sources.require_project(owner, value.project_id)
        return ConversationView(conversation=value, messages=self.repository.messages(conversation))

    # --- Turno: petición → propuesta ------------------------------------------------------------

    def send(
        self,
        owner: UUID,
        conversation: UUID,
        version: UUID,
        text: str,
        key: UUID,
        correlation: str,
    ) -> TurnResponse:
        fingerprint = digest(
            "copilot_turn",
            {"conversation": str(conversation), "version": str(version), "text": text},
        )
        current, replayed = self.begin(owner, conversation, key, fingerprint)
        if replayed:
            return replayed
        self.available(owner, current.project_id)
        table = self.sources.table(owner, version)
        if table.ref.project_id != current.project_id:
            raise ApplicationError("VERSION_NOT_FOUND", "Versión no encontrada.", 404)
        metrics = self.sources.metrics(owner, table.ref.artifact_id)
        context = authorized_context(table, metrics)
        self.uow.rollback()  # no se retiene ningún bloqueo mientras responde el proveedor
        request = AIRequest(
            task="copilot_turn",
            prompt_id=prompts.TURN_ID,
            prompt_version=prompts.TURN_VERSION,
            system=prompts.TURN_SYSTEM,
            messages=self.history(conversation) + [self.final(context, text)],
            output_schema=TurnOutput,
            max_output_tokens=self.config.max_output_tokens,
            context={"contexto": context, "peticion": text},
        )
        content, record = self.call(
            owner,
            current.project_id,
            conversation,
            request,
            context,
            lambda result: self.turn_content(owner, result.output, table, metrics),
        )
        return self.finish(
            owner, conversation, key, fingerprint, version, text, content, record, correlation
        )

    def turn_content(
        self,
        owner: UUID,
        output: TurnOutput,
        table: TableContext,
        metrics: list[MetricFact],
    ) -> AssistantContent:
        segments, numbers = plain_text(output.message)
        base: dict[str, Any] = {
            "action": output.action,
            "status": "ok",
            "segments": segments,
            "unverified_numbers": numbers,
            "source_text": output.message,
        }
        if output.action == "propose_query":
            if output.query is None:
                return self.discarded(output.message)
            summary, problems = resolve_query(output.query, table, metrics)
            if not problems:
                problems = self.sources.validate_plan(owner, table.ref, summary["steps"]).problems
            return AssistantContent(
                **base,
                query=QueryCard(table=table.ref, **summary, valid=not problems, problems=problems),
            )
        if output.action == "propose_metric":
            if output.metric is None:
                return self.discarded(output.message)
            draft, measure, time, problems = resolve_metric(output.metric, table)
            return AssistantContent(
                **base,
                metric=MetricCard(
                    table=table.ref,
                    draft=draft,
                    measure_column=measure.name if measure else None,
                    time_column=time.name if time else None,
                    valid=not problems,
                    problems=problems,
                ),
            )
        if output.action == "propose_cleaning_plan":
            steps, problems = resolve_cleaning(output.cleaning_steps)
            if steps and not problems:
                problems = self.sources.validate_plan(owner, table.ref, steps).problems
            return AssistantContent(
                **base,
                cleaning=CleaningCard(
                    table=table.ref, steps=steps, valid=not problems, problems=problems
                ),
            )
        topic = output.clarification.topic if output.clarification else "other"
        if output.clarification and output.clarification.question != output.message:
            question, extra = plain_text(output.clarification.question)
            base["segments"] = segments + [Segment(kind="text", text=" ")] + question
            base["unverified_numbers"] = numbers + extra
        return AssistantContent(
            **base,
            clarification=ClarificationCard(
                topic=topic,
                resolve_in=clarification_target(topic),
            ),
        )

    # --- explain_result ---------------------------------------------------------------------

    def explain(
        self, owner: UUID, conversation: UUID, execution: UUID, key: UUID, correlation: str
    ) -> TurnResponse:
        fingerprint = digest(
            "copilot_explain", {"conversation": str(conversation), "execution": str(execution)}
        )
        current, replayed = self.begin(owner, conversation, key, fingerprint)
        if replayed:
            return replayed
        self.available(owner, current.project_id)
        run = self.sources.execution(owner, execution)
        if run.project_id != current.project_id or run.version_id is None:
            raise ApplicationError("EXECUTION_NOT_FOUND", "Ejecución no encontrada.", 404)
        if run.state != "succeeded":
            raise ApplicationError(
                "RESULT_NOT_READY", "El resultado del análisis no está disponible.", 409
            )
        result = self.sources.result(owner, execution, MAX_RESULT_CELLS)
        table = self.sources.table(owner, run.version_id)
        context = {
            **authorized_context(table, self.sources.metrics(owner, table.ref.artifact_id)),
            "resultado": result_context(result),
        }
        self.uow.rollback()
        text = "Explica el resultado de este análisis."
        request = AIRequest(
            task="explain_result",
            prompt_id=prompts.EXPLAIN_ID,
            prompt_version=prompts.EXPLAIN_VERSION,
            system=prompts.EXPLAIN_SYSTEM,
            messages=self.history(conversation) + [self.final(context, text)],
            output_schema=ExplainOutput,
            max_output_tokens=self.config.max_output_tokens,
            context={"contexto": context, "peticion": text},
        )
        cells = {cell.evidence_id: cell for cell in result.cells}

        def build(result_: AIResult[ExplainOutput]) -> AssistantContent:
            segments, numbers, invalid = verify_explanation(result_.output.text, cells, execution)
            # Cada cifra citada se resuelve como GET /evidence: se recalcula su dirección.
            if not invalid:
                invalid = [
                    s.evidence_id
                    for s in segments
                    if s.kind == "evidence"
                    and s.evidence_id
                    and self.sources.evidence_value(owner, execution, s.evidence_id)
                    != cells[s.evidence_id].value
                ]
            if invalid:
                return AssistantContent(
                    action="explain_result",
                    status="rejected",
                    segments=[
                        Segment(
                            kind="text",
                            text="La explicación citaba cifras que no pertenecen a este "
                            "resultado y se descartó.",
                        )
                    ],
                    error_code="INVALID_EVIDENCE_REFERENCE",
                    execution_id=execution,
                    source_text=result_.output.text,
                )
            return AssistantContent(
                action="explain_result",
                status="ok",
                segments=segments,
                unverified_numbers=numbers,
                execution_id=execution,
                source_text=result_.output.text,
            )

        content, record = self.call(
            owner, current.project_id, conversation, request, context, build
        )
        return self.finish(
            owner,
            conversation,
            key,
            fingerprint,
            run.version_id,
            text,
            content,
            record,
            correlation,
        )

    # --- Acciones explícitas sobre una propuesta ----------------------------------------------

    def run_query(self, owner: UUID, message: UUID, correlation: str) -> ActionResult:
        def act(content: AssistantContent) -> ActionLink:
            card = content.query
            if card is None or not card.valid:
                raise ApplicationError(
                    "PROPOSAL_INVALID", "La propuesta no es una consulta válida.", 409
                )
            plan = self.sources.create_plan(
                owner, card.table, card.steps, uuid5(message, "query-plan"), correlation
            )
            if not plan.valid:
                raise self.invalid(plan.problems)
            execution = self.sources.execute(
                owner, plan.revision_id, uuid5(message, "query-run"), correlation
            )
            return ActionLink(
                kind="query_execution",
                plan_revision_id=plan.revision_id,
                execution_id=execution,
                metric_revision_id=None,
                created_at=self.clock(),
            )

        return self.action(owner, message, "query_execution", correlation, act)

    def create_metric(self, owner: UUID, message: UUID, correlation: str) -> ActionResult:
        def act(content: AssistantContent) -> ActionLink:
            card = content.metric
            if card is None or not card.valid:
                raise ApplicationError(
                    "PROPOSAL_INVALID", "La propuesta no es una métrica válida.", 409
                )
            revision = self.sources.create_metric(
                owner, card.table, card.draft, uuid5(message, "metric"), correlation
            )
            return ActionLink(
                kind="metric",
                plan_revision_id=None,
                execution_id=None,
                metric_revision_id=revision,
                created_at=self.clock(),
            )

        return self.action(owner, message, "metric", correlation, act)

    def cleaning_plan(self, owner: UUID, message: UUID, correlation: str) -> ActionResult:
        """Guarda el plan de limpieza como revisión (nunca lo ejecuta): la vista previa y la
        aprobación del efecto exacto siguen en Limpieza."""

        def act(content: AssistantContent) -> ActionLink:
            card = content.cleaning
            if card is None or not card.valid:
                raise ApplicationError(
                    "PROPOSAL_INVALID", "La propuesta no es un plan de limpieza válido.", 409
                )
            plan = self.sources.create_plan(
                owner, card.table, card.steps, uuid5(message, "cleaning-plan"), correlation
            )
            if not plan.valid:
                raise self.invalid(plan.problems)
            return ActionLink(
                kind="cleaning_plan",
                plan_revision_id=plan.revision_id,
                execution_id=None,
                metric_revision_id=None,
                created_at=self.clock(),
            )

        return self.action(owner, message, "cleaning_plan", correlation, act)

    # --- Internos -------------------------------------------------------------------------

    def begin(
        self, owner: UUID, conversation: UUID, key: UUID, fingerprint: str
    ) -> tuple[Conversation, TurnResponse | None]:
        try:
            current = self.repository.conversation(owner, conversation)
            self.sources.require_project(owner, current.project_id, writable=True)
            replayed = self.repository.replay(owner, conversation, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return current, self.pair(owner, replayed)
            return current, None
        except Exception:
            self.uow.rollback()
            raise

    def available(self, owner: UUID, project: UUID) -> AIProvider:
        if self.provider is None or self.config.unavailable is not None:
            reason = self.config.unavailable or "disabled"
            raise ApplicationError("COPILOT_UNAVAILABLE", UNAVAILABLE_MESSAGES[reason], 503)
        usage = self.usage(owner, project)
        if usage.user_tokens_today >= usage.user_daily_tokens_limit:
            raise ApplicationError(
                "AI_BUDGET_EXCEEDED",
                f"Alcanzaste el límite diario de {usage.user_daily_tokens_limit} tokens del "
                "copiloto. Se renueva a las 00:00 UTC.",
                429,
            )
        if Decimal(usage.project_cost_month_usd) >= Decimal(usage.project_monthly_cost_limit_usd):
            raise ApplicationError(
                "AI_BUDGET_EXCEEDED",
                f"El proyecto alcanzó su límite mensual de costo del copiloto "
                f"(US$ {usage.project_monthly_cost_limit_usd}). Se renueva el día 1 (UTC).",
                429,
            )
        return self.provider

    def usage(self, owner: UUID, project: UUID) -> CopilotUsage:
        moment = self.clock()
        day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        month = day.replace(day=1)
        return CopilotUsage(
            user_daily_tokens_limit=self.config.user_daily_tokens,
            user_tokens_today=self.repository.user_tokens_since(owner, day),
            project_monthly_cost_limit_usd=str(self.config.project_monthly_cost_usd),
            project_cost_month_usd=str(self.repository.project_cost_since(project, month)),
        )

    @staticmethod
    def exhausted(usage: CopilotUsage) -> bool:
        return usage.user_tokens_today >= usage.user_daily_tokens_limit or Decimal(
            usage.project_cost_month_usd
        ) >= Decimal(usage.project_monthly_cost_limit_usd)

    def history(self, conversation: UUID) -> list[AIMessage]:
        """Últimos mensajes: los del usuario tal cual y los del copiloto con sus referencias
        sin sustituir (nunca cifras)."""
        items = []
        for message in self.repository.messages(conversation)[-MAX_HISTORY:]:
            if message.role == "user" and message.text:
                items.append(AIMessage(role="user", content=message.text))
            elif message.assistant and message.assistant.status == "ok":
                text = message.assistant.source_text or "(sin texto)"
                items.append(
                    AIMessage(role="assistant", content=f"[{message.assistant.action}] {text}")
                )
        while items and items[0].role != "user":
            items.pop(0)
        return items

    @staticmethod
    def final(context: dict[str, Any], text: str) -> AIMessage:
        return AIMessage(
            role="user",
            content=(
                "<contexto_autorizado>\n"
                f"{serialize(context)}\n"
                "</contexto_autorizado>\n"
                "<peticion>\n"
                f"{text}\n"
                "</peticion>"
            ),
        )

    def call[T: BaseModel](
        self,
        owner: UUID,
        project: UUID,
        conversation: UUID,
        request: AIRequest[T],
        context: dict[str, Any],
        build: Callable[[AIResult[T]], AssistantContent],
    ) -> tuple[AssistantContent, CallRecord]:
        provider = self.available(owner, project)
        context_sha256 = hashlib.sha256(serialize(context).encode()).hexdigest()
        common: dict[str, Any] = {
            "owner_id": owner,
            "project_id": project,
            "conversation_id": conversation,
            "task": request.task,
            "provider": provider.name,
            "parameters": {
                **provider.parameters(),
                "max_output_tokens": request.max_output_tokens,
            },
            "prompt_id": request.prompt_id,
            "prompt_version": request.prompt_version,
            "context_sha256": context_sha256,
        }
        try:
            result = provider.complete(request)
        except AIProviderError as exc:
            content = AssistantContent(
                action="error",
                status="error",
                segments=[
                    Segment(kind="text", text=f"El copiloto no pudo responder: {exc.message}")
                ],
                error_code=exc.code,
            )
            model = exc.model or provider.model
            return content, CallRecord(
                **common,
                model=model,
                input_tokens=exc.usage.input_tokens,
                output_tokens=exc.usage.output_tokens,
                cache_read_tokens=exc.usage.cache_read_tokens,
                cache_write_tokens=exc.usage.cache_write_tokens,
                cost_usd=estimated_cost(model, exc.usage),
                latency_ms=exc.latency_ms,
                outcome="provider_error",
                error_code=exc.code,
            )
        content = build(result)
        rejected = content.status != "ok" or any(
            card is not None and not card.valid
            for card in (content.query, content.metric, content.cleaning)
        )
        return content, CallRecord(
            **common,
            model=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
            cost_usd=estimated_cost(result.model, result.usage),
            latency_ms=result.latency_ms,
            outcome="rejected" if rejected else "accepted",
            validation=validation_summary(content),
            error_code=content.error_code,
        )

    def finish(
        self,
        owner: UUID,
        conversation: UUID,
        key: UUID,
        fingerprint: str,
        version: UUID,
        text: str,
        content: AssistantContent,
        record: CallRecord,
        correlation: str,
    ) -> TurnResponse:
        try:
            self.repository.lock_conversation(owner, conversation)
            replayed = self.repository.replay(owner, conversation, key, fingerprint)
            call = self.repository.log_call(record)  # la llamada se registra siempre
            if replayed:
                self.uow.commit()
                return self.pair(owner, replayed)
            user = self.repository.append(
                conversation, "user", version, {"text": text}, None, correlation
            )
            assistant = self.repository.append(
                conversation,
                "assistant",
                version,
                content.model_dump(mode="json") | {"source_text": content.source_text},
                call,
                correlation,
            )
            self.repository.remember(owner, conversation, key, fingerprint, assistant.id)
            self.uow.commit()
            return TurnResponse(user=user, assistant=assistant)
        except Exception:
            self.uow.rollback()
            raise

    def pair(self, owner: UUID, assistant_id: UUID) -> TurnResponse:
        assistant = self.repository.message(owner, assistant_id)
        messages = self.repository.messages(assistant.conversation_id)
        user = next(m for m in messages if m.seq == assistant.seq - 1)
        return TurnResponse(user=user, assistant=assistant)

    def action(
        self,
        owner: UUID,
        message: UUID,
        kind: Literal["query_execution", "metric", "cleaning_plan"],
        correlation: str,
        act: Callable[[AssistantContent], ActionLink],
    ) -> ActionResult:
        """Una acción por mensaje y tipo: repetirla devuelve la ya registrada. Las claves de
        idempotencia de planes, ejecuciones y métricas derivan del mensaje."""
        try:
            value = self.repository.message(owner, message)
            conversation = self.repository.conversation(owner, value.conversation_id)
            self.sources.require_project(owner, conversation.project_id, writable=True)
            if value.assistant is None:
                raise ApplicationError("PROPOSAL_INVALID", "El mensaje no es una propuesta.", 409)
            existing = next((link for link in value.links if link.kind == kind), None)
            if existing:
                self.uow.rollback()
                return ActionResult(link=existing)
            self.uow.rollback()
            link = act(value.assistant)
            self.repository.lock_conversation(owner, conversation.id)
            again = next(
                (k for k in self.repository.message(owner, message).links if k.kind == kind),
                None,
            )
            if again:
                self.uow.rollback()
                return ActionResult(link=again)
            self.repository.add_link(message, link)
            self.uow.commit()
            return ActionResult(link=link)
        except Exception:
            self.uow.rollback()
            raise

    @staticmethod
    def invalid(problems: list[ProposalProblem]) -> ApplicationError:
        return ApplicationError(
            "PROPOSAL_INVALID",
            " ".join(p.message for p in problems) or "La propuesta ya no es válida.",
            422,
        )

    @staticmethod
    def discarded(source: str) -> AssistantContent:
        return AssistantContent(
            action="error",
            status="rejected",
            segments=[Segment(kind="text", text=DISCARDED)],
            error_code="INVALID_PROPOSAL_PAYLOAD",
            source_text=source,
        )


def validation_summary(content: AssistantContent) -> dict[str, Any]:
    """Resultado de la validación para el registro: códigos, nunca contenido."""
    cards = [c for c in (content.query, content.metric, content.cleaning) if c is not None]
    return {
        "status": content.status,
        "action": content.action,
        "valid": all(card.valid for card in cards) if cards else content.status == "ok",
        "problems": sorted({p.code for card in cards for p in card.problems}),
        "unverified_numbers": content.unverified_numbers,
        "evidence_references": sum(1 for s in content.segments if s.kind == "evidence"),
    }
