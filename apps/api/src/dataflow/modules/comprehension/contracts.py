"""Contratos de la comprensión del negocio (Fase 19, ADR-036).

La comprensión junta tres fuentes y nunca las mezcla:
- **reglas** (deterministas): escala de medida de cada columna y matriz de asociaciones calculada
  sobre todas las filas;
- **IA** (hipótesis): de qué trata el dataset, entidades, significado de cada columna y
  relaciones candidatas; sólo recibe nombres y un perfil agregado, nunca filas;
- **datos**: cada relación (de la IA, de las reglas o declarada en la base) lleva la medida que
  la respalda o no.
La valoración del usuario («Relevante» / «No relevante») es opcional y no bloquea nada.

Fase 23 (`business-comprehension-v2`, ADR-040): las correcciones del Diccionario de la pestaña
Dataset cambian el rol y la escala de sus columnas, y las columnas con datos personales se tratan
como texto y nunca se envían a la IA.

Fase 24 (`business-comprehension-v3`, ADR-041): grano del dataset, columnas calculadas a partir de
otras (fórmulas ponderadas, productos y umbrales), misma entidad 1:1, periodo, medidas y
dimensiones con su justificación, tres familias de relaciones (estructural, estadística y temporal)
con estado (pendiente, validada, rechazada o ambigua) y significados con confianza que el usuario
puede editar. Validar o rechazar una relación rehace la exploración, el dashboard y el informe.
"""

from datetime import datetime
from typing import Literal, NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Scale = Literal["nominal", "ordinal", "interval", "ratio", "identifier", "text", "empty"]
Measure = Literal["pearson", "spearman", "cramers_v", "eta", "dependency"]
Strength = Literal["negligible", "weak", "moderate", "strong"]
Verdict = Literal["relevant", "not_relevant"]
# Fase 24: cómo se lee una relación. «relevant» = validada y «not_relevant» = rechazada por el
# usuario; sin valoración, «ambigua» si los datos no la respaldan del todo y «pendiente» si sí.
RelationState = Literal["pending", "validated", "rejected", "ambiguous"]
RelationFamily = Literal["structural", "statistical", "temporal"]
Confidence = Literal["high", "medium", "low"]


class ComprehensionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnScale(ComprehensionModel):
    """Escala de medida de una columna por reglas (`measurement-scale-v1`)."""

    column: str
    scale: Scale
    order: list[str] = Field(default_factory=list)  # categorías ordenadas (ordinal)
    reason: str
    order_source: Literal["rules", "ai", "user"] | None = None


class Association(ComprehensionModel):
    """Medida de asociación entre dos columnas, calculada sobre las filas con ambos valores."""

    columns: tuple[str, str]
    measure: Measure
    value: str  # canónico, 4 decimales (redondeo declarado en `method`)
    strength: Strength
    rows: int
    method: str


class ColumnMeaning(ComprehensionModel):
    """Hipótesis de la IA sobre una columna (no se usa para calcular). Fase 24: con su confianza
    (una columna con nombre de código nunca pasa de «baja») o escrita por el usuario. Fase 24B:
    con la justificación de la IA (`reason`, prompt v3) y `unknown` si el usuario la marcó como
    desconocida."""

    column: str
    meaning: str
    entity: str | None = None
    confidence: Confidence | None = None
    source: Literal["ai", "user"] = "ai"
    confirmed: bool = False
    reason: str | None = None
    unknown: bool = False


class UserMeaning(NamedTuple):
    """Último significado del usuario de una columna (Fase 24 y 24B)."""

    text: str | None
    confirmed: bool
    unknown: bool = False


class Entity(ComprehensionModel):
    name: str
    columns: list[str]


class Relationship(ComprehensionModel):
    """Relación candidata con la evidencia que la respalda o no.

    `key` es estable entre versiones del mismo archivo (columnas ordenadas y tipo): con ella se
    guarda la valoración del usuario. Fase 24: `derived` (una columna calculada y una de sus
    fuentes), `same_entity` (dos columnas que nombran lo mismo, 1:1) y `period` (columnas que
    forman un periodo), con su familia y su estado."""

    key: str
    columns: tuple[str, str]
    kind: Literal["association", "dependency", "declared", "derived", "same_entity", "period"]
    origin: Literal["ai", "data", "declared"]
    hypothesis: str | None = None
    status: Literal["confirmed", "not_supported", "not_testable"]
    evidence: Association | None = None
    detail: str
    verdict: Verdict | None = None  # valoración del usuario (en esta versión o una anterior)
    family: RelationFamily = "statistical"
    state: RelationState = "pending"


class Grain(ComprehensionModel):
    """Qué representa una fila (Fase 24), por reglas: la clave única y la entidad que nombra."""

    sentence: str
    key: list[str]
    entity: str | None
    unique: bool
    reason: str


class Formula(ComprehensionModel):
    """Columna calculada a partir de otras, comprobada fila a fila sobre todas las filas."""

    column: str
    kind: Literal["weighted_sum", "product", "threshold"]
    sources: list[str]
    weights: list[str] = Field(default_factory=list)  # weighted_sum: un peso por fuente
    threshold: str | None = None  # threshold: valor desde el que se da `category`
    category: str | None = None
    expression: str
    rows: int
    matching_rows: int
    tolerance: str
    method: str


class MeasureInfo(ComprehensionModel):
    column: str
    additivity: Literal["additive", "semi_additive", "non_additive", "unknown"]
    aggregation: Literal["sum", "mean", "weighted_mean"]
    unit: str | None = None
    monetary: bool = False
    derived: bool = False
    reason: str


class DimensionInfo(ComprehensionModel):
    column: str
    distinct: int
    groupable: bool
    reason: str


class DatedAttribute(ComprehensionModel):
    """Fase 28 (`date-role-v1`): una fecha que describe a cada registro (p. ej. la fecha de
    ingreso de un empleado). No es una línea de tiempo: no hay evolución mensual, sólo registros
    por año."""

    column: str
    first: str | None
    last: str | None
    per_year: list[tuple[str, int]]
    reason: str


class AnalysisTarget(ComprehensionModel):
    """Fase 29 (`business-comprehension-v5`, ADR-047): lo que el análisis intenta explicar. Una
    columna de dos valores (se analiza su tasa: `value` es la categoría contada; sin ella, la
    menos frecuente) o una medida (se analiza su promedio). La proponen las reglas o la IA y el
    usuario la puede confirmar o cambiar; nunca bloquea."""

    column: str
    kind: Literal["rate", "measure"]
    value: str | None = None
    origin: Literal["rules", "ai", "user"]
    reason: str


class DerivedVariable(ComprehensionModel):
    """Fase 29: variable que el motor deriva de otra para agrupar: antigüedad en tramos a partir
    de una fecha que describe al registro, o cuartiles de una medida. `name` es el nombre con el
    que se consulta («antigüedad de X», «cuartil de X»)."""

    name: str
    kind: Literal["tenure", "quartile"]
    base: str
    origin: Literal["rules", "ai"]
    reason: str


class TargetChoice(ComprehensionModel):
    """Fase 29: el objetivo elegido por el usuario (metadato de la fuente, heredado). Sin
    columna, vuelve al propuesto por las reglas o la IA."""

    column: str | None
    value: str | None = None


class Period(ComprehensionModel):
    kind: Literal["date", "year_month"]
    columns: list[str]
    first: str | None
    last: str | None
    periods: int
    missing: int
    note: str


class ComprehensionScope(ComprehensionModel):
    execution_id: UUID
    version_id: UUID
    profile_sha256: str
    table_sha256: str


class Comprehension(ComprehensionModel):
    """Resultado del trabajo `comprehension` (operación `comprehension.understand@1`)."""

    rules_version: Literal[
        "business-comprehension-v1",
        "business-comprehension-v2",
        "business-comprehension-v3",
        "business-comprehension-v4",
        "business-comprehension-v5",
    ] = "business-comprehension-v5"
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
    # Fase 23: columnas cuya clasificación viene de una corrección del Diccionario y columnas con
    # datos personales (tratadas como texto y fuera del contexto de la IA).
    corrected_columns: list[str] = Field(default_factory=list)
    personal_columns: list[str] = Field(default_factory=list)
    # Fase 24 (`business-comprehension-v3`).
    grain: Grain | None = None
    formulas: list[Formula] = Field(default_factory=list)
    measures: list[MeasureInfo] = Field(default_factory=list)
    dimensions: list[DimensionInfo] = Field(default_factory=list)
    period: Period | None = None
    # Fase 28 (`business-comprehension-v4`): fechas que describen al registro, no eventos.
    dated_attributes: list[DatedAttribute] = Field(default_factory=list)
    # Fase 29 (`business-comprehension-v5`): objetivo del análisis, candidatos y variables
    # derivadas que el motor calcula.
    target: AnalysisTarget | None = None
    target_candidates: list[str] = Field(default_factory=list)
    derived: list[DerivedVariable] = Field(default_factory=list)


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
    # Fase 29 (prompt v4): objetivo propuesto (columna y motivo) y variables derivadas
    # propuestas (tipo y columna base); Python las valida.
    target: tuple[str, str] | None = None
    derived: list[tuple[str, str]] = Field(default_factory=list)


class AIReply(ComprehensionModel):
    comprehension: AIComprehension | None
    call: dict[str, object] | None
    error: str | None


# --- Valoración del usuario ---------------------------------------------------------------------


class FeedbackRequest(ComprehensionModel):
    relationship_key: str = Field(min_length=1, max_length=400)
    verdict: Verdict


class MeaningRequest(ComprehensionModel):
    """Fase 24: significado escrito o confirmado por el usuario (metadato de la fuente y la
    columna, heredado por las versiones siguientes). Sin texto, sin confirmar y sin marcar =
    vuelve al de la IA. Fase 24B: `unknown` marca la columna como desconocida (sin texto). No
    cambia ningún cálculo; el informe usa el significado vigente."""

    column: str = Field(min_length=1, max_length=200)
    meaning: str | None = Field(default=None, max_length=300)
    confirmed: bool = False
    unknown: bool = False


class TargetRequest(ComprehensionModel):
    """Fase 29: el usuario confirma o cambia el objetivo del análisis. `column` vacío vuelve al
    propuesto; `value` es la categoría contada de una columna de dos valores."""

    column: str | None = Field(default=None, max_length=200)
    value: str | None = Field(default=None, max_length=200)


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
    # Fase 24: la exploración, el dashboard y el informe se rehacen tras una valoración.
    recalculating: bool = False
