"""Contratos de la exploración guiada (Fase 20, ADR-037).

La exploración usa un lenguaje de consultas cerrado (`explore-v1`). Las consultas las proponen las
reglas (a partir de las relaciones confirmadas de la comprensión) y la IA (a partir de la estructura
y de las preguntas de negocio). Python valida cada propuesta y el motor la calcula sobre **todas**
las filas. A la IA sólo le llegan hasta 100 filas de cada resultado para juzgar su relevancia; las
cifras publicadas son las del motor, cada una con su `evidence_id`.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

QueryKind = Literal["aggregate", "crosstab", "ratio", "top", "correlation_by_group"]
Aggregation = Literal["sum", "mean", "median", "count"]

RULES = "explore-v1"
OPERATION = "exploration.explore@1"
MAX_GROUPS = 500  # filas de resultado que se guardan
AI_ROWS = 100  # filas de cada resultado que ve la IA


class ExplorationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExploreQuery(ExplorationModel):
    """Una consulta del lenguaje cerrado. Columnas por nombre exacto de la tabla publicada."""

    kind: QueryKind
    measure: str | None = None
    measure_b: str | None = None  # ratio: numerador/denominador; correlación: segunda medida
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    aggregation: Aggregation | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    limit: int | None = Field(default=None, ge=1, le=20)  # top

    @property
    def key(self) -> str:
        parts = [
            self.kind,
            self.aggregation or "",
            self.measure or "",
            self.measure_b or "",
            ",".join(self.dimensions),
            f"{self.filter_column}={self.filter_value}" if self.filter_column else "",
            str(self.limit or ""),
        ]
        return "|".join(parts)


class ExploreFigure(ExplorationModel):
    label: str
    value: str | None  # canónico (Decimal en texto); None si no se puede calcular
    evidence_id: str


class ExploreRow(ExplorationModel):
    groups: list[str]
    rows: int
    figures: list[ExploreFigure]


class ExploreResult(ExplorationModel):
    key: str
    query: ExploreQuery
    title: str
    method: str
    columns: list[str]  # cabeceras: grupos y cifras
    rows: list[ExploreRow]
    total_groups: int
    truncated: bool
    covered_rows: int
    relevant: bool | None = None  # juicio (IA o reglas)
    judged_by: Literal["ai", "rules"] | None = None
    reason: str | None = None


class ExploreProposal(ExplorationModel):
    origin: Literal["rule", "ai"]
    query: dict[str, object]
    motive: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None
    key: str | None = None


class ExplorationLimits(ExplorationModel):
    max_queries: int = Field(default=20, ge=1, le=40)
    max_ai_proposals: int = Field(default=12, ge=0, le=20)
    max_ai_calls: int = Field(default=2, ge=0, le=4)
    ai_rows: int = Field(default=AI_ROWS, ge=1, le=AI_ROWS)


class ExplorationScope(ExplorationModel):
    execution_id: UUID
    version_id: UUID
    comprehension_sha256: str
    table_sha256: str


class Exploration(ExplorationModel):
    rules_version: Literal["explore-v1"] = "explore-v1"
    operation: Literal["exploration.explore@1"] = "exploration.explore@1"
    scope: ExplorationScope
    limits: ExplorationLimits
    ai_state: Literal["ready", "unavailable", "failed"]
    ai_reason: str | None = None
    proposals: list[ExploreProposal]
    results: list[ExploreResult]
    excluded: list[str] = Field(default_factory=list)  # relaciones marcadas «No relevante»
    calls: list[dict[str, object]] = Field(default_factory=list)
    limitations: list[str]


class ExplorationView(ExplorationModel):
    state: Literal["queued", "running", "ready", "failed"]
    execution_id: UUID
    reason: str | None = None
    exploration: Exploration | None = None


# --- IA ------------------------------------------------------------------------------------------


class RawQuery(ExplorationModel):
    """Propuesta de la IA traducida del esquema de salida; todavía sin validar."""

    kind: str
    measure: str | None = None
    measure_b: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    aggregation: str | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    limit: int | None = None
    motive: str = ""


class Judgment(ExplorationModel):
    key: str
    relevant: bool
    reason: str
