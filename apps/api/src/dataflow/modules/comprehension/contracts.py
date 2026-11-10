"""Contratos de la comprensión del negocio (Fase 19, ADR-036).

La comprensión junta tres fuentes y nunca las mezcla:
- **reglas** (deterministas): escala de medida de cada columna y matriz de asociaciones calculada
  sobre todas las filas;
- **IA** (hipótesis): de qué trata el dataset, entidades, significado de cada columna y
  relaciones candidatas; sólo recibe nombres y un perfil agregado, nunca filas;
- **datos**: cada relación (de la IA, de las reglas o declarada en la base) lleva la medida que
  la respalda o no.
La valoración del usuario («Relevante» / «No relevante») es opcional y no bloquea nada.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Scale = Literal["nominal", "ordinal", "interval", "ratio", "identifier", "text", "empty"]
Measure = Literal["pearson", "spearman", "cramers_v", "eta", "dependency"]
Strength = Literal["negligible", "weak", "moderate", "strong"]
Verdict = Literal["relevant", "not_relevant"]


class ComprehensionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnScale(ComprehensionModel):
    """Escala de medida de una columna por reglas (`measurement-scale-v1`)."""

    column: str
    scale: Scale
    order: list[str] = Field(default_factory=list)  # categorías ordenadas (ordinal)
    reason: str
    order_source: Literal["rules", "ai"] | None = None


class Association(ComprehensionModel):
    """Medida de asociación entre dos columnas, calculada sobre las filas con ambos valores."""

    columns: tuple[str, str]
    measure: Measure
    value: str  # canónico, 4 decimales (redondeo declarado en `method`)
    strength: Strength
    rows: int
    method: str


class ColumnMeaning(ComprehensionModel):
    """Hipótesis de la IA sobre una columna (no se usa para calcular)."""

    column: str
    meaning: str
    entity: str | None = None


class Entity(ComprehensionModel):
    name: str
    columns: list[str]


class Relationship(ComprehensionModel):
    """Relación candidata con la evidencia que la respalda o no.

    `key` es estable entre versiones del mismo archivo (columnas ordenadas y tipo): con ella se
    guarda la valoración del usuario."""

    key: str
    columns: tuple[str, str]
    kind: Literal["association", "dependency", "declared"]
    origin: Literal["ai", "data", "declared"]
    hypothesis: str | None = None
    status: Literal["confirmed", "not_supported", "not_testable"]
    evidence: Association | None = None
    detail: str
    verdict: Verdict | None = None  # valoración del usuario en una versión anterior


class ComprehensionScope(ComprehensionModel):
    execution_id: UUID
    version_id: UUID
    profile_sha256: str
    table_sha256: str


class Comprehension(ComprehensionModel):
    """Resultado del trabajo `comprehension` (operación `comprehension.understand@1`)."""

    rules_version: Literal["business-comprehension-v1"] = "business-comprehension-v1"
    scope: ComprehensionScope
    ai_state: Literal["ready", "unavailable", "failed"]
    ai_reason: str | None = None
    domain: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    meanings: list[ColumnMeaning] = Field(default_factory=list)
    scales: list[ColumnScale]
    associations: list[Association]
    matrix_columns: list[str]
    relationships: list[Relationship]
    questions: list[str] = Field(default_factory=list)
    discarded: list[str] = Field(default_factory=list)  # textos de la IA retirados y por qué
    limitations: list[str]
    calls: list[dict[str, object]] = Field(default_factory=list)


# --- IA: contexto y respuesta ------------------------------------------------------------------


class AIColumn(ComprehensionModel):
    """Lo único que la IA ve de una columna: nombre y perfil agregado."""

    name: str
    type: str
    role: str
    scale: str
    distinct: int
    nulls: int
    rows: int
    frequent: list[str] = Field(default_factory=list)  # valores más frecuentes (dimensiones)
    minimum: str | None = None
    maximum: str | None = None


class AIComprehension(ComprehensionModel):
    """Respuesta de la IA ya traducida del esquema de salida; todavía sin validar."""

    domain: str
    entities: list[Entity]
    meanings: list[ColumnMeaning]
    orders: dict[str, list[str]]
    relationships: list[tuple[str, str, str, str]]  # (columna, columna, tipo, hipótesis)
    questions: list[str]


class AIReply(ComprehensionModel):
    comprehension: AIComprehension | None
    call: dict[str, object] | None
    error: str | None


# --- Valoración del usuario ---------------------------------------------------------------------


class FeedbackRequest(ComprehensionModel):
    relationship_key: str = Field(min_length=1, max_length=400)
    verdict: Verdict


class FeedbackItem(ComprehensionModel):
    relationship_key: str
    verdict: Verdict
    created_at: datetime


class ComprehensionView(ComprehensionModel):
    state: Literal["queued", "running", "ready", "failed"]
    execution_id: UUID
    reason: str | None = None
    comprehension: Comprehension | None = None
    feedback: list[FeedbackItem] = Field(default_factory=list)  # valoraciones de esta versión
