"""Proveedor real: Claude mediante el SDK oficial `anthropic` (ADR-022).

Único archivo que importa el SDK. La clave se pasa explícitamente: el cliente no busca otras
credenciales del entorno. Salida estructurada con `messages.parse` y el esquema Pydantic de la
tarea; el prompt de sistema se cachea (prefijo estable). En los modelos que lo admiten se
activa el respaldo del servidor ante rechazos; el registro guarda el modelo que respondió.
"""

import time
from typing import Any, Literal

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam
from pydantic import BaseModel, ValidationError

from dataflow.integrations.ai.port import (
    AIErrorCode,
    AIMessage,
    AIProviderError,
    AIRequest,
    AIResult,
    AIUsage,
)

FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


Effort = Literal["low", "medium", "high"]


def message_param(message: AIMessage) -> BetaMessageParam:
    if message.role == "user":
        return {"role": "user", "content": message.content}
    return {"role": "assistant", "content": message.content}


class AnthropicProvider:
    def __init__(
        self, api_key: str, model: str, effort: Effort, timeout_seconds: int, max_retries: int = 1
    ) -> None:
        self._model, self.effort, self.timeout = model, effort, timeout_seconds
        self.max_retries = max_retries
        self.client = anthropic.Anthropic(
            api_key=api_key, timeout=float(timeout_seconds), max_retries=max_retries
        )

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def parameters(self) -> dict[str, Any]:
        return {
            "effort": self.effort,
            "timeout_seconds": self.timeout,
            "max_retries": self.max_retries,
            "fallbacks": "default" if self._model in FALLBACK_MODELS else None,
        }

    def complete[T: BaseModel](self, request: AIRequest[T]) -> AIResult[T]:
        started = time.perf_counter()
        config: BetaOutputConfigParam = {"effort": self.effort}
        extra: dict[str, Any] = (
            {"betas": [FALLBACK_BETA], "fallbacks": "default"}
            if self._model in FALLBACK_MODELS
            else {}
        )
        try:
            response = self.client.beta.messages.parse(
                model=self._model,
                max_tokens=request.max_output_tokens,
                system=[
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[message_param(m) for m in request.messages],
                output_format=request.output_schema,
                output_config=config,
                **extra,
            )
        except anthropic.APITimeoutError as exc:
            raise self.failure(
                "AI_TIMEOUT", "El proveedor de IA no respondió a tiempo.", started
            ) from exc
        except anthropic.RateLimitError as exc:
            raise self.failure(
                "AI_RATE_LIMITED",
                "El proveedor de IA limitó las solicitudes; reintenta luego.",
                started,
            ) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise self.failure(
                "AI_UNAVAILABLE", "La clave del proveedor de IA no es válida.", started
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise self.failure(
                "AI_UNAVAILABLE", "No se pudo contactar al proveedor de IA.", started
            ) from exc
        except anthropic.APIStatusError as exc:
            raise self.failure(
                "AI_PROVIDER_ERROR", f"El proveedor de IA devolvió {exc.status_code}.", started
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise self.failure(
                "AI_INVALID_OUTPUT", "La respuesta no cumple el esquema.", started
            ) from exc
        latency = round((time.perf_counter() - started) * 1000)
        raw = response.usage
        usage = AIUsage(
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            cache_read_tokens=raw.cache_read_input_tokens or 0,
            cache_write_tokens=raw.cache_creation_input_tokens or 0,
        )
        served = str(response.model)
        if response.stop_reason == "refusal":
            raise AIProviderError(
                "AI_REFUSED", "El modelo rechazó la solicitud.", usage, latency, served
            )
        if response.stop_reason == "max_tokens":
            raise AIProviderError(
                "AI_INVALID_OUTPUT",
                "La respuesta superó el límite de tokens.",
                usage,
                latency,
                served,
            )
        parsed = response.parsed_output
        if parsed is None:
            raise AIProviderError(
                "AI_INVALID_OUTPUT",
                "La respuesta no trae salida estructurada.",
                usage,
                latency,
                served,
            )
        return AIResult(output=parsed, usage=usage, model=served, latency_ms=latency)

    def failure(self, code: AIErrorCode, message: str, started: float) -> AIProviderError:
        return AIProviderError(
            code, message, latency_ms=round((time.perf_counter() - started) * 1000)
        )
