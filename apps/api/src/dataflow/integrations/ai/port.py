"""Puerto AIProvider (ADR-006, ADR-022).

Los casos de uso sólo conocen este contrato: salida estructurada validada con Pydantic,
identificador y versión de prompt, límite de tokens y un error estable por causa. Ningún módulo
importa el SDK del proveedor; sólo `anthropic_provider.py` lo hace.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

AIErrorCode = Literal[
    "AI_TIMEOUT",
    "AI_UNAVAILABLE",
    "AI_RATE_LIMITED",
    "AI_REFUSED",
    "AI_INVALID_OUTPUT",
    "AI_PROVIDER_ERROR",
]


@dataclass(frozen=True)
class AIMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AIRequest[OutputT: BaseModel]:
    """Una llamada. `context` es el contexto autorizado que ya va serializado en `messages`:
    el proveedor real lo ignora y el falso lo usa para responder de forma determinista."""

    task: str
    prompt_id: str
    prompt_version: str
    system: str
    messages: list[AIMessage]
    output_schema: type[OutputT]
    max_output_tokens: int
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class AIResult[OutputT: BaseModel]:
    output: OutputT
    usage: AIUsage
    model: str  # el modelo que respondió (puede ser el de respaldo)
    latency_ms: int


class AIProviderError(Exception):
    """Fallo del proveedor con código estable. Conserva el uso si la llamada llegó a facturarse."""

    def __init__(
        self,
        code: AIErrorCode,
        message: str,
        usage: AIUsage | None = None,
        latency_ms: int = 0,
        model: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message = code, message
        self.usage, self.latency_ms, self.model = usage or AIUsage(), latency_ms, model


class AIProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def parameters(self) -> dict[str, Any]:
        """Parámetros normalizados de la llamada (para el registro): nunca la clave."""
        ...

    def complete[T: BaseModel](self, request: AIRequest[T]) -> AIResult[T]: ...
