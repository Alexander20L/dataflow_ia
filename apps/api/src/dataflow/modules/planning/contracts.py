from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.data_types import DataType

CATALOG_VERSION = "analysis-v7"
MAX_STEPS = 16
# Marca en el esquema de parámetros: el campo contiene IDs de columna de la tabla fijada.
COLUMN_REF = "x-dataflow-column-ref"

InputKind = Literal["source", "table"]
OutputKind = Literal["table", "profile", "quality", "quality_rules", "analysis_result"]
SemanticRole = Literal["unknown", "identifier", "dimension", "measure", "business_date"]
ProblemCode = Literal[
    "EMPTY_PLAN",
    "TOO_MANY_STEPS",
    "DUPLICATE_STEP_ID",
    "INVALID_STEP_REFERENCE",
    "UNSUPPORTED_OPERATION",
    "INPUT_KIND_MISMATCH",
    "INVALID_PARAMETERS",
    "UNKNOWN_COLUMN",
    "SEMANTIC_REQUIREMENT_MISSING",
    "COLUMN_TYPE_MISMATCH",
    "IDENTIFIER_CONVERSION_UNCONFIRMED",
    "QUALITY_RULESET_MISMATCH",
    "METRIC_REFERENCE_MISMATCH",
    "UNIT_MISMATCH",
    "TIME_COLUMN_MISMATCH",
    "SHARE_NOT_ADDITIVE",
    "METRIC_UNSUPPORTED",
]
ResolveIn = Literal["plan_steps", "plan_input", "understanding"]
PlanStatus = Literal["incomplete", "valid"]


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticRevisionRequirement(PlanningModel):
    kind: Literal["semantic_revision"] = "semantic_revision"


class ConfirmedColumnRole(PlanningModel):
    kind: Literal["confirmed_column_role"] = "confirmed_column_role"
    parameter: str
    role: SemanticRole


Requirement = Annotated[
    SemanticRevisionRequirement | ConfirmedColumnRole, Field(discriminator="kind")
]


# Esquema tipado de una tabla durante la validación: ID de columna → tipo del catálogo.
Schema = Mapping[UUID, DataType]
# Tipos admitidos por cada parámetro de columna, según los parámetros ya validados.
ColumnTypes = Callable[[Any], Mapping[str, frozenset[DataType]]]
# Esquema de salida de una operación tabla → tabla (funciones puras, sin datos).
OutputSchema = Callable[[Any, Schema], dict[UUID, DataType]]


@dataclass(frozen=True)
class IdentifierConversionGuard:
    """Salvaguarda: una columna confirmada como «identifier» en la revisión fijada no se
    convierte a un tipo numérico sin la confirmación explícita del parámetro indicado."""

    column_parameter: str
    type_parameter: str
    confirmation_parameter: str
    numeric_types: frozenset[DataType]


@dataclass(frozen=True)
class RulesetRequirement:
    """Revisión de un conjunto de reglas: hash y tipos que exige a cada columna."""

    content_sha256: str
    column_types: dict[UUID, frozenset[DataType]]


@dataclass(frozen=True)
class MetricRequirement:
    """Revisión de una métrica: columnas, tipos, si exige el rol semántico «measure» y si su
    agregación se puede sumar entre grupos (participación sobre el total)."""

    content_sha256: str
    measure_column_id: UUID
    measure_types: frozenset[DataType]
    requires_measure_role: bool
    time_column_id: UUID | None
    filter_column_ids: tuple[UUID, ...]
    additive: bool = False
    # 11E · analytics.query@3: segunda medida (`sum_product`, también confirmada como
    # «measure»), columna temporal exigida aunque no se agrupe por tiempo (último corte) y
    # versión mínima de la consulta que la calcula.
    second_measure_column_id: UUID | None = None
    requires_time_role: bool = False
    min_query_version: int = 1


@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    version: int
    title: str
    input_kind: InputKind
    output_kind: OutputKind
    parameters: type[BaseModel]
    requirements: tuple[SemanticRevisionRequirement | ConfirmedColumnRole, ...] = ()
    transforms_data: bool = False
    column_types: ColumnTypes | None = None
    output_schema: OutputSchema | None = None
    identifier_guard: IdentifierConversionGuard | None = None
    # (parámetro con el ID de revisión, parámetro con su hash) de un conjunto de reglas.
    ruleset_reference: tuple[str, str] | None = None
    # Parámetro con la lista de referencias exactas a métricas ({revision_id, content_sha256}).
    metric_reference: str | None = None
    # Parámetro con IDs de revisión (de entre las métricas) que deben poder sumarse
    # (participación sobre el total).
    additive_metrics: str | None = None

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


class OperationCatalog(Protocol):
    @property
    def catalog_version(self) -> str: ...
    def descriptors(self) -> list[OperationDescriptor]: ...
    def descriptor(self, name: str, version: int) -> OperationDescriptor | None: ...


class InputRef(PlanningModel):
    kind: Literal["input"] = "input"
    alias: Literal["source"] = "source"


class StepRef(PlanningModel):
    kind: Literal["step"] = "step"
    step_id: str


class PlanStep(PlanningModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    version: int = Field(ge=1, le=1000)
    input: Annotated[InputRef | StepRef, Field(discriminator="kind")]
    parameters: dict[str, Any] = Field(default_factory=dict)


class TableInput(PlanningModel):
    kind: Literal["table"] = "table"
    alias: Literal["source"] = "source"
    version_id: UUID
    version_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: UUID
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanDraft(PlanningModel):
    """Contenido editable; el servidor completa input y configuración."""

    semantic_ref: SemanticReference | None = None
    # Límite de carga útil; el máximo de negocio (16) se informa como problema.
    steps: list[PlanStep] = Field(default_factory=list, max_length=64)


class Problem(PlanningModel):
    code: ProblemCode
    message: str
    resolve_in: ResolveIn
    step_id: str | None = None
    parameter: str | None = None


@dataclass(frozen=True)
class PlanningFacts:
    """Hechos de la entrada fijada que la validación necesita, ya resueltos."""

    input_kind: InputKind
    column_ids: frozenset[UUID]
    semantic_pinned: bool = False
    confirmed_roles: dict[UUID, SemanticRole] = field(default_factory=dict)
    # Vacío: tipos desconocidos (p. ej. planes de sistema); no se comprueban tipos.
    column_types: dict[UUID, DataType] = field(default_factory=dict)
    # Revisiones de reglas referenciadas por los pasos que existen y son del propietario.
    quality_rulesets: dict[UUID, RulesetRequirement] = field(default_factory=dict)
    # Métricas referenciadas que existen y son del propietario.
    metrics: dict[UUID, MetricRequirement] = field(default_factory=dict)
    # Unidad o moneda de las columnas confirmadas en la revisión fijada («currency:EUR»).
    column_units: dict[UUID, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class PinnedTable:
    """Representación publicada y verificada que un plan fija como input."""

    project_id: UUID
    input: TableInput
    column_ids: frozenset[UUID]
    column_types: dict[UUID, DataType] = field(default_factory=dict)


class PlanValidation(PlanningModel):
    catalog_version: str
    status: PlanStatus
    valid: bool
    problems: list[Problem]
    validated_at: datetime


class PlanView(PlanningModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    revision: int
    head_revision: int
    project_id: UUID
    input: TableInput
    semantic_ref: SemanticReference | None
    steps: list[PlanStep]
    content: dict[str, Any]
    content_sha256: str
    created_by: UUID
    created_at: datetime
    validation: PlanValidation


class PlanPage(PlanningModel):
    items: list[PlanView]
    total: int
    limit: int
    offset: int


class ApplicableOperation(PlanningModel):
    operation: str
    version: int
    key: str
    title: str
    applicable: bool
    reason: str | None = None
    missing_requirements: list[Requirement] = Field(default_factory=list)


class PlanningAccess(Protocol):
    def table(self, owner: UUID, artifact: UUID) -> PinnedTable: ...
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def confirmed_roles(
        self, owner: UUID, reference: SemanticReference, table: TableInput
    ) -> dict[UUID, SemanticRole]: ...
    def semantic_reference(self, owner: UUID, revision: UUID) -> SemanticReference: ...
    def quality_ruleset(self, owner: UUID, revision: UUID) -> RulesetRequirement | None: ...
    def analytics_metric(self, owner: UUID, revision: UUID) -> MetricRequirement | None: ...
    def column_units(
        self, owner: UUID, reference: SemanticReference, table: TableInput
    ) -> dict[UUID, str | None]: ...
    def lock_owner(self, owner: UUID) -> None: ...


class PlanningRepository(Protocol):
    def validation(self, plan: UUID, catalog_version: str) -> PlanValidation | None: ...
    def save_validation(self, plan: UUID, validation: PlanValidation) -> None: ...
    def request(self, project: UUID, key: UUID) -> tuple[str, UUID] | None: ...
    def remember(
        self, project: UUID, key: UUID, owner: UUID, fingerprint: str, plan: UUID
    ) -> None: ...
