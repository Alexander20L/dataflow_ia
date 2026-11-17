"""Adaptador de IA (ADR-006, ADR-022): puerto, proveedor falso y costo estimado.

El proveedor real se importa sólo desde la composición (`bootstrap`), para que cargar este
paquete no cargue el SDK.
"""

from dataflow.integrations.ai.fake import FakeProvider
from dataflow.integrations.ai.port import (
    AIErrorCode,
    AIMessage,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResult,
    AIUsage,
)
from dataflow.integrations.ai.pricing import estimated_cost

__all__ = [
    "AIErrorCode",
    "AIMessage",
    "AIProvider",
    "AIProviderError",
    "AIRequest",
    "AIResult",
    "AIUsage",
    "FakeProvider",
    "estimated_cost",
]
