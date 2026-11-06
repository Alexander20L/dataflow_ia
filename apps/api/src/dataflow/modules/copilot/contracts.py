"""Contratos del copiloto (Fase 10, ADR-022).

Tres grupos: (1) la salida estructurada que el modelo puede devolver, deliberadamente más pobre
que los contratos de analytics y planning (sin hashes, IDs como texto, parámetros de limpieza
como JSON en texto) para que el servidor resuelva y valide todo; (2) las vistas de la API;
(3) los puertos que la composición implementa con planning, analytics y executions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ActionKind = Literal[
    "propose_query", "propose_metric", "propose_cleaning_plan", "ask_clarification"
]
FilterOperator = Literal[
    "eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "between", "is_null", "is_not_null"
]
Aggregation = Literal["sum", "count", "count_distinct", "avg", "min", "max"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]
ComparisonKind = Literal["previous_period", "same_period_last_year"]
ClarificationTopic = Literal["metric", "measure", "currency", "business_date", "dimension", "other"]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- (1) Salida estructurada del modelo -----------------------------------------------------


class ProposedFilter(OutputModel):
    column_id: str = Field(description="ID de columna del contexto (nunca el nombre).")
    operator: FilterOperator
    values: list[str] = Field(description="Valores en representación canónica.")


class QueryProposal(OutputModel):
    metric_ids: list[str] = Field(description="revision_id de métricas existentes del contexto.")
    dimension_ids: list[str] = Field(description="IDs de columna para agrupar (0 a 4).")
    filters: list[ProposedFilter]
    time_grain: TimeGrain | None
    time_start: str | None = Field(description="Fecha ISO inclusiva o null.")
    time_end: str | None = Field(description="Fecha ISO inclusiva o null.")
    comparisons: list[ComparisonKind]
    ranking_metric_id: str | None
    ranking_direction: Literal["desc", "asc"] | None
    top_n: int | None
    share_metric_ids: list[str]


class MetricProposal(OutputModel):
    label: str = Field(description="Nombre de negocio propuesto (el usuario lo confirma).")
    description: str | None
    measure_column_id: str
    aggregation: Aggregation
    time_column_id: str | None
    filters: list[ProposedFilter]


class CleaningStepProposal(OutputModel):
    operation: str = Field(description="Operación del catálogo, p. ej. cleaning.trim_whitespace.")
    version: int
    parameters_json: str = Field(description="Parámetros de la operación como objeto JSON.")


class Clarification(OutputModel):
    topic: ClarificationTopic
    question: str


class TurnOutput(OutputModel):
    """Respuesta a una petición: exactamente una acción y su carga."""

    action: ActionKind
    message: str = Field(description="Texto breve para el usuario, sin cifras.")
    query: QueryProposal | None
    metric: MetricProposal | None
    cleaning_steps: list[CleaningStepProposal]
    clarification: Clarification | None


class ExplainOutput(OutputModel):
    """explain_result: texto con referencias {{evidence:<evidence_id>}} en lugar de cifras."""

    text: str


# --- (2) Vistas de la API -------------------------------------------------------------------


class CopilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CopilotUsage(CopilotModel):
    user_daily_tokens_limit: int
    user_tokens_today: int
    project_monthly_cost_limit_usd: str
    project_cost_month_usd: str


class CopilotStatus(CopilotModel):
    available: bool
    reason: Literal["disabled", "missing_key", "budget_exhausted"] | None
    provider: str
    model: str | None
    prompt_version: str
    usage: CopilotUsage | None


class Conversation(CopilotModel):
    id: UUID
    project_id: UUID
    title: str
    created_at: datetime


class CreateConversationRequest(CopilotModel):
    title: str = Field(default="Conversación", min_length=1, max_length=120)


class SendMessageRequest(CopilotModel):
    version_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class ExplainRequest(CopilotModel):
    execution_id: UUID


class Segment(CopilotModel):
    """Trozo de texto que se muestra: texto libre, cifra verificada (con su evidencia) o una
    cifra escrita por el modelo que se retiró."""

    kind: Literal["text", "evidence", "unverified"]
    text: str
    evidence_id: str | None = None
    execution_id: UUID | None = None


class ProposalProblem(CopilotModel):
    code: str
    message: str
    resolve_in: Literal["understanding", "metrics", "proposal", "plan"] = "proposal"


class TableRef(CopilotModel):
    project_id: UUID
    version_id: UUID
    artifact_id: UUID
    artifact_sha256: str
    semantic_ref: dict[str, Any] | None


class NamedRef(CopilotModel):
    id: str
    name: str


class QueryCard(CopilotModel):
    table: TableRef
    steps: list[dict[str, Any]]
    metrics: list[NamedRef]
    dimensions: list[NamedRef]
    time_grain: TimeGrain | None
    time_range: dict[str, str | None] | None
    comparisons: list[ComparisonKind]
    ranking: dict[str, Any] | None
    share_of_total: list[NamedRef]
    valid: bool
    problems: list[ProposalProblem]


class MetricCard(CopilotModel):
    table: TableRef
    draft: dict[str, Any]
    measure_column: str | None
    time_column: str | None
    valid: bool
    problems: list[ProposalProblem]


class CleaningCard(CopilotModel):
    table: TableRef
    steps: list[dict[str, Any]]
    valid: bool
    problems: list[ProposalProblem]


class ClarificationCard(CopilotModel):
    topic: ClarificationTopic
    resolve_in: Literal["understanding", "metrics", "conversation"]


MessageAction = Literal[
    "propose_query",
    "propose_metric",
    "propose_cleaning_plan",
    "ask_clarification",
    "explain_result",
    "error",
]


class AssistantContent(CopilotModel):
    action: MessageAction
    status: Literal["ok", "rejected", "error"]
    segments: list[Segment]
    unverified_numbers: int = 0
    error_code: str | None = None
    query: QueryCard | None = None
    metric: MetricCard | None = None
    cleaning: CleaningCard | None = None
    clarification: ClarificationCard | None = None
    execution_id: UUID | None = None  # explain_result
    # Texto del modelo con referencias, sin sustituir: se reenvía como historial (nunca cifras).
    source_text: str = Field(default="", exclude=True)


class ActionLink(CopilotModel):
    kind: Literal["query_execution", "metric", "cleaning_plan"]
    plan_revision_id: UUID | None
    execution_id: UUID | None
    metric_revision_id: UUID | None
    created_at: datetime


class Message(CopilotModel):
    id: UUID
    conversation_id: UUID
    seq: int
    role: Literal["user", "assistant"]
    version_id: UUID | None
    text: str | None  # mensaje del usuario
    assistant: AssistantContent | None
    links: list[ActionLink]
    created_at: datetime


class ConversationView(CopilotModel):
    conversation: Conversation
    messages: list[Message]


class TurnResponse(CopilotModel):
    user: Message
    assistant: Message


class ActionResult(CopilotModel):
    link: ActionLink


# --- (3) Puertos ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnFact:
    id: UUID
    name: str
    technical_type: str
    null_count: int | None
    distinct_count: int | None
    role: str | None
    confirmed: bool
    unit: str | None
    currency: str | None
    description: str | None


@dataclass(frozen=True)
class TableContext:
    ref: TableRef
    version_number: int
    row_count: int | None
    columns: list[ColumnFact]
    semantic_revision: int | None
    dataset_description: str | None
    row_grain: str | None


@dataclass(frozen=True)
class MetricFact:
    revision_id: UUID
    content_sha256: str
    label: str
    aggregation: str
    measure_column_id: UUID
    time_column_id: UUID | None
    filters: list[dict[str, Any]]
    applicable: bool


@dataclass(frozen=True)
class Validation:
    valid: bool
    problems: list[ProposalProblem]


@dataclass(frozen=True)
class PlanRef:
    revision_id: UUID
    valid: bool
    problems: list[ProposalProblem]


@dataclass(frozen=True)
class ExecutionFact:
    id: UUID
    project_id: UUID
    version_id: UUID | None
    state: str


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
class ResultFacts:
    execution_id: UUID
    operation: str
    metrics: list[dict[str, Any]]
    cells: list[ResultCell]
    total_cells: int
    rows: int


class CopilotSources(Protocol):
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def table(self, owner: UUID, version: UUID) -> TableContext: ...
    def metrics(self, owner: UUID, artifact: UUID) -> list[MetricFact]: ...
    def validate_plan(
        self, owner: UUID, table: TableRef, steps: list[dict[str, Any]]
    ) -> Validation: ...
    def create_plan(
        self,
        owner: UUID,
        table: TableRef,
        steps: list[dict[str, Any]],
        key: UUID,
        correlation: str,
    ) -> PlanRef: ...
    def execute(self, owner: UUID, plan_revision: UUID, key: UUID, correlation: str) -> UUID: ...
    def create_metric(
        self, owner: UUID, table: TableRef, draft: dict[str, Any], key: UUID, correlation: str
    ) -> UUID: ...
    def execution(self, owner: UUID, execution: UUID) -> ExecutionFact: ...
    def result(self, owner: UUID, execution: UUID, limit: int) -> ResultFacts: ...
    def evidence_value(self, owner: UUID, execution: UUID, evidence_id: str) -> str | None:
        """Recalcula la dirección de la cifra (como GET /evidence) y devuelve su valor."""
        ...


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


class CopilotRepository(Protocol):
    def create_conversation(self, owner: UUID, project: UUID, title: str) -> Conversation: ...
    def conversations(self, owner: UUID, project: UUID) -> list[Conversation]: ...
    def conversation(self, owner: UUID, conversation: UUID) -> Conversation: ...
    def lock_conversation(self, owner: UUID, conversation: UUID) -> Conversation: ...
    def messages(self, conversation: UUID) -> list[Message]: ...
    def message(self, owner: UUID, message: UUID) -> Message: ...
    def append(
        self,
        conversation: UUID,
        role: Literal["user", "assistant"],
        version: UUID | None,
        content: dict[str, Any],
        call: UUID | None,
        correlation: str,
    ) -> Message: ...
    def replay(self, owner: UUID, scope: UUID, key: UUID, fingerprint: str) -> UUID | None: ...
    def remember(
        self, owner: UUID, scope: UUID, key: UUID, fingerprint: str, result: UUID
    ) -> None: ...
    def add_link(self, message: UUID, link: ActionLink) -> None: ...
    def log_call(self, record: CallRecord) -> UUID: ...
    def user_tokens_since(self, owner: UUID, since: datetime) -> int: ...
    def project_cost_since(self, project: UUID, since: datetime) -> Decimal: ...
