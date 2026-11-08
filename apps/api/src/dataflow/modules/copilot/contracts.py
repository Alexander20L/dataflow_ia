"""Contratos de la explicación automática (C2) y del registro de llamadas a la IA.

Desde la Fase 13 (ADR-026) el copiloto ya no conversa ni propone acciones: sólo queda la salida
estructurada que el modelo devuelve al explicar el dashboard publicado, su forma ya verificada
(cada cifra con su evidencia) y el registro de consumo.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- (1) Salida estructurada del modelo -----------------------------------------------------


Severity = Literal["alta", "media", "baja"]


class Alerta(OutputModel):
    titulo: str = Field(max_length=120)
    detalle: str = Field(
        max_length=600, description="Cifras sólo como {{evidence:<evidencia>}}, nunca escritas."
    )
    severidad: Severity


class AuditoriaTextual(OutputModel):
    """Auditoría textual de un dashboard publicado (Fase 11F, `copilot-audit@v1`)."""

    resumen_ejecutivo: str = Field(max_length=1500)
    alertas_criticas: list[Alerta] = Field(max_length=3)
    recomendaciones: list[str] = Field(min_length=2, max_length=2)


class CopilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CopilotUsage(CopilotModel):
    user_daily_tokens_limit: int
    user_tokens_today: int
    project_monthly_cost_limit_usd: str
    project_cost_month_usd: str


class Segment(CopilotModel):
    """Trozo de texto que se muestra: texto libre, cifra verificada (con su evidencia) o una
    cifra escrita por el modelo que se retiró."""

    kind: Literal["text", "evidence", "unverified"]
    text: str
    evidence_id: str | None = None
    execution_id: UUID | None = None


class AuditAlert(CopilotModel):
    titulo: list[Segment]
    detalle: list[Segment]
    severidad: Severity


class AuditContent(CopilotModel):
    """Auditoría ya verificada: cada cifra es un segmento con su evidencia y su ejecución."""

    resumen_ejecutivo: list[Segment]
    alertas_criticas: list[AuditAlert]
    recomendaciones: list[list[Segment]]
    unverified_numbers: int  # números escritos por el modelo que se retiraron


@dataclass(frozen=True)
class ResultCell:
    evidence_id: str
    cell: str  # value, change_pct, share_of_total, rank…
    metric_key: str
    metric_label: str
    aggregation: str
    currency: str | None
    unit: str | None
    value: str | None
    group: dict[str, str | None]  # nombre de la dimensión → etiqueta (dato del dataset)
    period: str | None
    comparison: str | None = None


@dataclass(frozen=True)
class CallRecord:
    """Registro de una llamada al proveedor: sólo metadatos, nunca contenido tabular."""

    owner_id: UUID
    project_id: UUID
    conversation_id: UUID | None
    task: str
    provider: str
    model: str
    parameters: dict[str, Any]
    prompt_id: str
    prompt_version: str
    context_sha256: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal | None
    latency_ms: int
    outcome: Literal["accepted", "rejected", "provider_error"]
    validation: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
