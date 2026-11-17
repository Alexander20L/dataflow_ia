"""csv-quality-v2: reglas de calidad configuradas por el usuario (Fase 6B).

Las reglas se guardan como revisiones inmutables de un conjunto por tabla base del proyecto y
referencian columnas por ID (sirven para esa tabla y sus versiones derivadas, que conservan
los IDs). Los diagnósticos separan el origen: `technical` (Q-001 a Q-003, completitud) y
`user` (reglas de negocio), para que la completitud técnica no se mezcle con ellas.
"""

from datetime import datetime
from typing import Annotated, Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dataflow.platform.conversion import FORMATS, CastType
from dataflow.platform.data_types import DataType

RULE_SET: Final = "csv-quality-v2"
MAX_RULES = 50
Severity = Literal["low", "medium", "high"]
RuleKind = Literal["required", "unique_key", "range", "allowed_values", "convertible"]
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class RulesModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticKeyRef(RulesModel):
    """Revisión semántica de la que se tomó la clave (procedencia, no dependencia)."""

    id: UUID
    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BaseRule(RulesModel):
    id: RuleId
    severity: Severity = "medium"
    description: str | None = Field(default=None, max_length=300)


class RequiredRule(BaseRule):
    """Obligatoriedad: la columna no admite nulos."""

    kind: Literal["required"] = "required"
    column_id: UUID


class UniqueKeyRule(BaseRule):
    """Unicidad de clave: los registros que repiten una clave ya vista (en el orden de la tabla)
    son infracciones. Una clave con algún nulo es infracción: una clave no puede ser nula."""

    kind: Literal["unique_key"] = "unique_key"
    column_ids: list[UUID] = Field(min_length=1, max_length=16)
    source: Literal["user", "semantic_key"] = "user"
    semantic_ref: SemanticKeyRef | None = None

    @model_validator(mode="after")
    def provenance(self) -> "UniqueKeyRule":
        if len(set(self.column_ids)) != len(self.column_ids):
            raise ValueError("Cada columna sólo puede aparecer una vez en la clave.")
        if (self.source == "semantic_key") != (self.semantic_ref is not None):
            raise ValueError("Una clave tomada de la semántica debe citar su revisión.")
        return self


class RangeRule(BaseRule):
    """Rango inclusivo para columnas tipadas: entero/decimal (cadena decimal) o fecha ISO."""

    kind: Literal["range"] = "range"
    column_id: UUID
    minimum: str | None = Field(default=None, max_length=60)
    maximum: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def bounded(self) -> "RangeRule":
        if self.minimum is None and self.maximum is None:
            raise ValueError("Indica un mínimo, un máximo o ambos.")
        return self


class AllowedValuesRule(BaseRule):
    """Valores de un catálogo: comparación exacta con la cadena canónica de la celda."""

    kind: Literal["allowed_values"] = "allowed_values"
    column_id: UUID
    values: list[str] = Field(min_length=1, max_length=200)

    @field_validator("values")
    @classmethod
    def distinct(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not 1 <= len(v) <= 200 for v in values):
            raise ValueError("Valores únicos de 1 a 200 caracteres.")
        return values


class ConvertibleRule(BaseRule):
    """Formato convertible: el texto cumple la gramática de cleaning.cast@1 (sin convertirlo)."""

    kind: Literal["convertible"] = "convertible"
    column_id: UUID
    type: CastType
    scale: int | None = Field(default=None, ge=0, le=12)

    @model_validator(mode="after")
    def decimal_scale(self) -> "ConvertibleRule":
        if (self.type == "decimal") != (self.scale is not None):
            raise ValueError("La escala (0 a 12) es obligatoria para decimal y sólo para decimal.")
        return self

    @property
    def format(self) -> str:
        return FORMATS[self.type]


Rule = Annotated[
    RequiredRule | UniqueKeyRule | RangeRule | AllowedValuesRule | ConvertibleRule,
    Field(discriminator="kind"),
]


class BaseTable(RulesModel):
    version_id: UUID
    artifact_id: UUID
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RulesetDraft(RulesModel):
    name: str = Field(min_length=1, max_length=120)
    rules: list[Rule] = Field(default_factory=list, max_length=MAX_RULES)

    @field_validator("rules")
    @classmethod
    def unique_ids(cls, rules: list[Rule]) -> list[Rule]:
        ids = [rule.id for rule in rules]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada regla necesita un identificador único.")
        return rules


class RulesetContent(RulesetDraft):
    """Contenido sometido a hash (dominio `quality_ruleset`)."""

    schema_version: Literal[1] = 1
    rule_set: Literal["csv-quality-v2"] = RULE_SET
    base_table: BaseTable


class RulesetRevision(RulesModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    project_id: UUID
    revision: int = Field(ge=1)
    previous_revision_id: UUID | None
    content: RulesetContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class RulesetReference(RulesModel):
    id: UUID
    revision: int
    content_sha256: str


class RulesetProblem(RulesModel):
    rule_id: str
    code: Literal["UNKNOWN_COLUMN", "COLUMN_TYPE_MISMATCH", "INVALID_BOUND"]
    message: str


class RulesetSummary(RulesModel):
    """Conjunto de reglas del proyecto y si es aplicable a la tabla consultada."""

    family_id: UUID
    head: RulesetRevision
    revision_count: int
    anchored_here: bool
    applicable: bool
    problems: list[RulesetProblem]


class RulesetContext(RulesModel):
    artifact_id: UUID
    own: RulesetSummary | None
    others: list[RulesetSummary]


class SaveRulesetRequest(RulesModel):
    table_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0)
    draft: RulesetDraft


class SaveRulesetResponse(RulesModel):
    revision: RulesetRevision
    changed: bool


class RulesetRevisionPage(RulesModel):
    items: list[RulesetReference]
    total: int


class QualityRulesParameters(RulesModel):
    """Parámetros de quality.evaluate@2: revisión exacta de un conjunto de reglas."""

    rule_set: Literal["csv-quality-v2"] = RULE_SET
    ruleset_revision_id: UUID
    ruleset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


Origin = Literal["technical", "user"]


class RuleIssue(RulesModel):
    id: str
    origin: Origin
    rule: str  # Q-001..Q-003 (técnicas) o el tipo de regla de usuario
    rule_id: str | None  # identificador de la regla del usuario
    column_ids: list[str]
    columns: list[str]
    severity: Severity
    affected_rows: int = Field(ge=1)
    sample_row_numbers: list[int] = Field(max_length=5)
    description: str


class TechnicalSummary(RulesModel):
    """Completitud técnica (csv-quality-v1): no incluye reglas de negocio."""

    completeness_percent: float
    missing_cells: int
    duplicate_rows: int
    whitespace_cells: int


class UserSummary(RulesModel):
    rules_evaluated: int
    rules_failed: int


class QualityRulesReport(RulesModel):
    schema_version: Literal[1] = 1
    rule_version: Literal["csv-quality-v2"] = RULE_SET
    ruleset: RulesetReference
    row_count: int
    cell_count: int
    technical: TechnicalSummary
    user: UserSummary
    issues: list[RuleIssue]


class RulesetFacts(RulesModel):
    """Lo que la validación de planes necesita de una revisión: hash y tipos exigidos."""

    content_sha256: str
    column_types: dict[UUID, list[DataType]]


class RulesetRepository(Protocol):
    def family_for_table(self, owner: UUID, artifact: UUID) -> UUID | None: ...
    def lock_family(self, owner: UUID, project: UUID, base: BaseTable) -> tuple[UUID, int]: ...
    def replay(self, family: UUID, key: UUID, fingerprint: str) -> RulesetRevision | None: ...
    def append(
        self, family: UUID, expected: int, revision: RulesetRevision, correlation: str
    ) -> None: ...
    def remember(self, family: UUID, key: UUID, fingerprint: str, revision: UUID) -> None: ...
    def head(self, family: UUID) -> tuple[RulesetRevision, int] | None: ...
    def families(self, owner: UUID, project: UUID) -> list[UUID]: ...
    def revision(self, owner: UUID, revision: UUID) -> RulesetRevision: ...
    def history(self, owner: UUID, family: UUID) -> list[RulesetReference]: ...
