"""Composición del proveedor de IA desde la configuración (ADR-022).

`DATAFLOW_AI_PROVIDER`: `disabled` (por defecto), `fake` (pytest, CI y E2E) o `anthropic`.
Sin clave, el copiloto informa `missing_key` y el resto del producto funciona igual.
"""

from functools import lru_cache
from typing import Any

from dataflow.integrations.ai import AIProvider, AIRequest, FakeProvider
from dataflow.modules.copilot import simulation
from dataflow.modules.copilot.application import CopilotConfig
from dataflow.platform.config import Settings, get_settings


def simulated(request: AIRequest[Any]) -> dict[str, Any]:
    return simulation.respond(
        request.task, request.context["contexto"], str(request.context["peticion"])
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
    if settings.ai_provider == "disabled":
        unavailable = "disabled"
    elif settings.ai_provider == "fake":
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
        provider=settings.ai_provider,
        unavailable=unavailable,
        model=model,
        user_daily_tokens=settings.ai_user_daily_tokens,
        project_monthly_cost_usd=settings.ai_project_monthly_cost_usd,
        max_output_tokens=settings.ai_max_output_tokens,
    )
