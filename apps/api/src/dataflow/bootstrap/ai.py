"""Composición del proveedor de IA desde la configuración (ADR-022).

`DATAFLOW_AI_PROVIDER`: `auto` (por defecto: Anthropic si hay clave, si no desactivada),
`disabled`, `fake` (pytest, CI y E2E) o `anthropic`. Con `anthropic` y sin clave se informa
`missing_key`; el resto del producto funciona igual.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from dataflow.integrations.ai import AIProvider, AIRequest, FakeProvider
from dataflow.modules.copilot import simulation
from dataflow.modules.copilot.application import CopilotConfig, CopilotService
from dataflow.modules.executions.public import Deferred, Lease, ProcessingConfig
from dataflow.platform.config import Settings, get_settings
from dataflow.platform.errors import ApplicationError


def simulated(request: AIRequest[Any]) -> dict[str, Any]:
    return simulation.respond(
        request.task, request.context["contexto"], str(request.context["peticion"])
    )


def budget_deferral(error: ApplicationError) -> Deferred:
    """Fase 33 (ADR-051): con el presupuesto de IA agotado, el trabajo espera a que se renueve
    y sigue con IA (no se hace sólo con reglas)."""
    renews = (error.details or {}).get("renews_at")
    try:
        until = datetime.fromisoformat(str(renews))
    except ValueError:
        until = datetime.now(UTC) + timedelta(hours=1)
    when = until.astimezone(UTC).strftime("%d/%m/%Y %H:%M")
    return Deferred(
        until,
        "AI_BUDGET_WAITING",
        f"En espera: el presupuesto de IA se renueva el {when} (UTC).",
    )


def ai_unavailability(copilot: CopilotService, lease: Lease) -> str | None:
    """Por qué un trabajo seguiría sin IA (sin clave, desactivada…), o None si hay IA. Con el
    presupuesto agotado no sigue sin IA: se aplaza (`Deferred`)."""
    try:
        copilot.available(lease.owner_id, lease.execution.project_id)
    except ApplicationError as error:
        if error.code == "AI_BUDGET_EXCEEDED":
            raise budget_deferral(error) from error
        if error.code == "COPILOT_UNAVAILABLE":
            return copilot.config.unavailable or "disabled"
        return error.code
    return None


def ai_job_config(config: ProcessingConfig) -> ProcessingConfig:
    """Plazo de un trabajo con IA (Fase 29.1): el de la configuración de IA, nunca menos que el
    de procesamiento. Queda guardado en el plan como cualquier otro límite."""
    return config.model_copy(
        update={
            "timeout_seconds": max(config.timeout_seconds, get_settings().ai_job_timeout_seconds)
        }
    )


@lru_cache
def anthropic_provider(
    key: str, model: str, effort: str, timeout: int, max_retries: int = 1
) -> AIProvider:
    # Import diferido: el SDK sólo se carga si la IA real está activada.
    from dataflow.integrations.ai.anthropic_provider import AnthropicProvider

    return AnthropicProvider(key, model, effort, timeout, max_retries)  # type: ignore[arg-type]


def configured(
    settings: Settings | None = None, *, max_retries: int = 1
) -> tuple[AIProvider | None, CopilotConfig]:
    settings = settings or get_settings()
    provider: AIProvider | None = None
    unavailable: Any = None
    model: str | None = None
    effective = settings.effective_ai_provider()
    if effective == "disabled":
        unavailable = "disabled"
    elif effective == "fake":
        provider, model = FakeProvider(responder=simulated), "fake"
    else:
        key = settings.ai_key()
        model = settings.ai_model
        if key is None:
            unavailable = "missing_key"
        else:
            provider = anthropic_provider(
                key, settings.ai_model, settings.ai_effort, settings.ai_timeout_seconds, max_retries
            )
    return provider, CopilotConfig(
        provider=effective,
        unavailable=unavailable,
        model=model,
        user_daily_tokens=settings.ai_user_daily_tokens,
        project_monthly_cost_usd=settings.ai_project_monthly_cost_usd,
        max_output_tokens=settings.ai_max_output_tokens,
    )
