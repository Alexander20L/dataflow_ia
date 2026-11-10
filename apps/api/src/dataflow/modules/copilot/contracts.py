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


class PropuestaIA(OutputModel):
    """Propuesta de investigación de la IA (Fase 16, ADR-033): sólo nombra un tipo del catálogo
    y elementos que ya existen; Python la valida y el motor la calcula. Nunca contiene cifras."""

    tipo: str = Field(max_length=60, description="Uno de los tipos del catálogo.")
    dimension: str | None = Field(default=None, max_length=200)
    mes: str | None = Field(default=None, max_length=20, description="AAAA-MM")
    anio: int | None = None
    grupo: str | None = Field(default=None, max_length=200)
    motivo: str = Field(max_length=300, description="Qué pregunta responde, sin cifras.")


class PropuestasInvestigacion(OutputModel):
    propuestas: list[PropuestaIA] = Field(max_length=10)


class ColumnaIA(OutputModel):
    """Significado de una columna según la IA (Fase 19): hipótesis, sin cifras."""

    columna: str = Field(max_length=200, description="Nombre exacto de una columna recibida.")
    significado: str = Field(max_length=200)
    entidad: str | None = Field(default=None, max_length=80)


class EntidadIA(OutputModel):
    nombre: str = Field(max_length=80)
    columnas: list[str] = Field(max_length=30)


class OrdenIA(OutputModel):
    """Orden de las categorías de una dimensión ordinal (todas las categorías recibidas)."""

    columna: str = Field(max_length=200)
    orden: list[str] = Field(max_length=50)


class RelacionIA(OutputModel):
    columnas: list[str] = Field(min_length=2, max_length=2)
    tipo: str = Field(max_length=30, description="asociacion, dependencia o jerarquia")
    hipotesis: str = Field(max_length=300, description="Qué relación de negocio se espera.")


class ComprensionIA(OutputModel):
    """Comprensión del negocio a partir de nombres y perfil agregado (Fase 19, ADR-036)."""

    dominio: str = Field(max_length=400, description="De qué trata el dataset, sin cifras.")
    entidades: list[EntidadIA] = Field(max_length=10)
    columnas: list[ColumnaIA] = Field(max_length=128)
    ordenes: list[OrdenIA] = Field(default_factory=list, max_length=20)
    relaciones: list[RelacionIA] = Field(max_length=15)
    preguntas: list[str] = Field(max_length=8)


class ConsultaIA(OutputModel):
    """Consulta del lenguaje cerrado `explore-v1` (Fase 20): sólo nombra columnas y opciones."""

    tipo: str = Field(max_length=40, description="Uno de los tipos del catálogo.")
    medida: str | None = Field(default=None, max_length=200)
    medida_b: str | None = Field(default=None, max_length=200)
    dimensiones: list[str] = Field(default_factory=list, max_length=2)
    agregacion: str | None = Field(default=None, max_length=20)
    filtro_columna: str | None = Field(default=None, max_length=200)
    filtro_valor: str | None = Field(default=None, max_length=200)
    limite: int | None = None
    motivo: str = Field(max_length=300, description="Qué pregunta de negocio responde.")


class ConsultasIA(OutputModel):
    consultas: list[ConsultaIA] = Field(max_length=12)


class JuicioIA(OutputModel):
    clave: str = Field(max_length=600)
    relevante: bool
    motivo: str = Field(max_length=300, description="Por qué, sin cifras propias.")


class JuiciosIA(OutputModel):
    juicios: list[JuicioIA] = Field(max_length=40)


class ElementoIA(OutputModel):
    """Un gráfico del dashboard (Fase 21): señala un elemento publicado; nunca lleva cifras."""

    elemento: str = Field(max_length=700, description="Id exacto del elemento recibido.")
    grafico: str = Field(max_length=20, description="Uno de los gráficos del catálogo.")
    cifra: str | None = Field(
        default=None, max_length=80, description="Sólo en indicadores: id de una de sus cifras."
    )
    titulo: str | None = Field(default=None, max_length=200, description="Sin cifras.")


class SeccionIA(OutputModel):
    titulo: str = Field(max_length=200)
    descripcion: str | None = Field(default=None, max_length=300)
    elementos: list[ElementoIA] = Field(max_length=12)


class DisenoIA(OutputModel):
    titulo: str = Field(max_length=200)
    secciones: list[SeccionIA] = Field(max_length=6)


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
