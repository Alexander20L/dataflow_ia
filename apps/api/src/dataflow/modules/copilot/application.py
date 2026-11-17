"""Acceso a la IA para la explicación automática (C2): disponibilidad y presupuesto.

Desde la Fase 13 (ADR-026) el copiloto ya no conversa ni propone acciones: la IA sólo explica el
dashboard publicado, en un trabajo del worker. Este servicio decide si puede llamarse al proveedor
(configuración y límites de consumo registrado) sin conocer al proveedor concreto.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from dataflow.integrations.ai import AIProvider
from dataflow.modules.copilot.contracts import CopilotUsage
from dataflow.platform.errors import ApplicationError

UNAVAILABLE_MESSAGES = {
    "disabled": "La IA está desactivada en este servidor.",
    "missing_key": "La IA no tiene una clave configurada.",
}


class UsageRepository(Protocol):
    def user_tokens_since(self, owner: UUID, since: datetime) -> int: ...
    def project_cost_since(self, project: UUID, since: datetime) -> Decimal: ...


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
        repository: UsageRepository,
        provider: AIProvider | None,
        config: CopilotConfig,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.repository, self.provider = repository, provider
        self.config, self.clock = config, clock

    def available(self, owner: UUID, project: UUID) -> AIProvider:
        if self.provider is None or self.config.unavailable is not None:
            reason = self.config.unavailable or "disabled"
            raise ApplicationError("COPILOT_UNAVAILABLE", UNAVAILABLE_MESSAGES[reason], 503)
        usage = self.usage(owner, project)
        if usage.user_tokens_today >= usage.user_daily_tokens_limit:
            raise ApplicationError(
                "AI_BUDGET_EXCEEDED",
                f"Alcanzaste el límite diario de {usage.user_daily_tokens_limit} tokens de IA. "
                "Se renueva a las 00:00 UTC.",
                429,
            )
        if Decimal(usage.project_cost_month_usd) >= Decimal(usage.project_monthly_cost_limit_usd):
            raise ApplicationError(
                "AI_BUDGET_EXCEEDED",
                f"El proyecto alcanzó su límite mensual de costo de IA "
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
