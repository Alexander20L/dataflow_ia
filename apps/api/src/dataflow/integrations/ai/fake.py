"""Proveedor falso determinista para pytest, CI y E2E: no necesita clave ni red.

No contiene reglas de negocio: recibe una función `responder` (la composición le da la
simulación del copiloto) o una lista de salidas guionizadas para probar respuestas hostiles.
El uso de tokens se deriva del tamaño del texto para que los límites se puedan probar.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from dataflow.integrations.ai.port import (
    AIProviderError,
    AIRequest,
    AIResult,
    AIUsage,
)

Responder = Callable[[AIRequest[Any]], dict[str, Any] | BaseModel]


class FakeProvider:
    def __init__(
        self,
        responder: Responder | None = None,
        script: list[dict[str, Any] | AIProviderError] | None = None,
    ) -> None:
        self.responder = responder
        self.script = list(script or [])
        self.requests: list[AIRequest[Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake"

    def parameters(self) -> dict[str, Any]:
        return {"deterministic": True}

    def complete[T: BaseModel](self, request: AIRequest[T]) -> AIResult[T]:
        self.requests.append(request)
        usage = AIUsage(
            input_tokens=sum(len(m.content) for m in request.messages) // 4
            + len(request.system) // 4,
            output_tokens=50,
        )
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, AIProviderError):
                raise item
            raw: dict[str, Any] | BaseModel = item
        elif self.responder is not None:
            raw = self.responder(request)
        else:
            raise AIProviderError("AI_UNAVAILABLE", "El proveedor falso no tiene respuesta.")
        try:
            output = request.output_schema.model_validate(
                raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
            )
        except ValidationError as exc:
            raise AIProviderError(
                "AI_INVALID_OUTPUT", "La respuesta no cumple el esquema.", usage
            ) from exc
        return AIResult(output=output, usage=usage, model=self.model, latency_ms=1)
