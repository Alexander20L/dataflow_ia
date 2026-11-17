"""Contratos de la investigación automática (`investigation.investigate@1`, Fase 16, ADR-033).

Una investigación es un ciclo acotado sobre los hallazgos ya publicados de una carga: primero
reglas, después propuestas de la IA en un esquema cerrado. Python valida cada propuesta contra el
plan y los hallazgos y el motor determinista la calcula; la IA nunca aporta cifras.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.analytics.contracts import (
    AutomaticEvidence,
    FollowUpKind,
    FollowUpQuery,
    FollowUpResult,
)
from dataflow.modules.copilot.contracts import AuditContent

RULES = "investigation-v1"
OPERATION = "investigation.investigate@1"


class InvestigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InvestigationLimits(InvestigationModel):
    """Límites duros del ciclo; se guardan con cada investigación."""

    max_iterations: int = Field(default=3, ge=1, le=10)
    max_ai_calls: int = Field(default=4, ge=0, le=20)
    max_seconds: int = Field(default=60, ge=5, le=600)
    max_cost_usd: str = "0.05"
    max_queries: int = Field(default=12, ge=1, le=50)
    max_proposals_per_call: int = Field(default=4, ge=1, le=10)

    @property
    def cost(self) -> Decimal:
        return Decimal(self.max_cost_usd)


class InvestigationScope(InvestigationModel):
    execution_id: UUID
    version_id: UUID
    analysis_artifact_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_execution_id: UUID
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelCall(InvestigationModel):
    """Metadatos de una llamada al proveedor (nunca el contenido tabular)."""

    purpose: Literal["proposal", "explanation"]
    iteration: int
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    parameters: dict[str, object]
    context_sha256: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: str | None
    latency_ms: int
    outcome: Literal["accepted", "rejected", "provider_error"]
    error_code: str | None = None


class RawProposal(InvestigationModel):
    """Propuesta tal como llega de la IA: todavía sin validar."""

    kind: str = Field(max_length=60)
    dimension: str | None = Field(default=None, max_length=200)
    month: str | None = Field(default=None, max_length=20)
    year: int | None = None
    group: str | None = Field(default=None, max_length=200)
    motive: str = Field(default="", max_length=400)


class Proposal(InvestigationModel):
    """Una consulta propuesta (por regla o por la IA) y la decisión de Python, con motivo."""

    origin: Literal["rule", "ai"]
    iteration: int
    kind: str
    dimension: str | None
    month: str | None = None
    year: int | None = None
    group: str | None = None
    motive: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None
    key: str | None = None  # clave de la consulta aceptada (resultado en `results`)


class Consumption(InvestigationModel):
    ai_calls: int
    cost_usd: str
    elapsed_ms: int


StopReason = Literal[
    "max_iterations",
    "no_new_proposals",
    "ai_unavailable",
    "ai_error",
    "max_ai_calls",
    "max_cost",
    "max_seconds",
    "max_queries",
    "nothing_to_investigate",
]


class Investigation(InvestigationModel):
    schema_version: Literal[1] = 1
    operation: Literal["investigation.investigate@1"] = "investigation.investigate@1"
    rules_version: Literal["investigation-v1"] = "investigation-v1"
    scope: InvestigationScope
    limits: InvestigationLimits
    iterations: int
    proposals: list[Proposal]
    results: list[FollowUpResult]
    calls: list[ModelCall]
    consumption: Consumption
    stopped: StopReason
    ai: Literal["available", "unavailable"]
    ai_reason: str | None = None
    explanation_state: Literal["ready", "unavailable", "failed"]
    explanation_reason: str | None = None
    explanation: AuditContent | None = None
    limitations: list[str]


class InvestigationView(BaseModel):
    """Estado de la investigación de una versión (sólo lectura)."""

    state: Literal["queued", "running", "ready", "failed"]
    reason: str | None = None
    execution_id: UUID
    investigation: Investigation | None = None


# --- Puertos: entrada y salida de la IA en tipos de este módulo -------------------------------


class Finding(InvestigationModel):
    id: str
    title: str
    statement: str


class ProposalContext(InvestigationModel):
    """Lo único que ve la IA para proponer: hallazgos, resultados y el catálogo permitido."""

    iteration: int
    measure: str
    kinds: dict[FollowUpKind, str]
    dimensions: list[str]
    months: list[str]
    years: list[int]
    groups: dict[str, list[str]]
    findings: list[Finding]
    done: list[str]
    max_proposals: int


class ProposalReply(InvestigationModel):
    proposals: list[RawProposal]
    call: ModelCall | None
    error: str | None = None


class ExplainedFigure(InvestigationModel):
    evidence_id: str
    label: str
    value: str | None
    unit: str
    execution_id: UUID


class ExplanationReply(InvestigationModel):
    state: Literal["ready", "unavailable", "failed"]
    reason: str | None = None
    content: AuditContent | None = None
    call: ModelCall | None = None


__all__ = [
    "OPERATION",
    "RULES",
    "AutomaticEvidence",
    "Consumption",
    "ExplainedFigure",
    "ExplanationReply",
    "Finding",
    "FollowUpQuery",
    "Investigation",
    "InvestigationLimits",
    "InvestigationScope",
    "InvestigationView",
    "ModelCall",
    "Proposal",
    "ProposalContext",
    "ProposalReply",
    "RawProposal",
    "StopReason",
]
