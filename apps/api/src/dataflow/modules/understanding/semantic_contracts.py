from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dataflow.modules.understanding.contracts import DatasetProfile

DataType = Literal["string", "integer", "decimal", "date", "boolean"]
SemanticRole = Literal["unknown", "identifier", "dimension", "measure", "business_date"]
ReviewState = Literal["pending", "confirmed", "rejected"]
HINTS_VERSION = "semantic-hints-v1"


class SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TableReference(SemanticModel):
    version_id: UUID
    version_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: UUID
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SemanticReference(SemanticModel):
    id: UUID
    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Review(SemanticModel):
    state: ReviewState
    origin: Literal["heuristic", "user", "ai", "migration"]
    actor_id: UUID | None
    reviewed_at: datetime | None


class NullPolicy(SemanticModel):
    mode: Literal["preserve", "empty_is_null", "explicit_tokens"] = "preserve"
    tokens: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tokens")
    @classmethod
    def token_limits(cls, values: list[str]) -> list[str]:
        if any(len(value) > 100 for value in values) or len(set(values)) != len(values):
            raise ValueError("Tokens únicos de hasta 100 caracteres.")
        return values


class ColumnFacts(SemanticModel):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0, le=127)
    technical_type: DataType
    type_parameters: dict[str, Any]
    nullable: bool


class ColumnDraft(SemanticModel):
    column_id: UUID
    description: str | None = Field(default=None, max_length=1000)
    interpretation_type: DataType | None = None
    role: SemanticRole = "unknown"
    unit: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    parse_format: (
        Literal["integer_ascii", "decimal_dot", "iso_date", "boolean_lowercase"] | None
    ) = None
    null_policy: NullPolicy = Field(default_factory=NullPolicy)
    review_state: ReviewState = "pending"

    @field_validator("description", "unit", mode="before")
    @classmethod
    def optional_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class GrainDraft(SemanticModel):
    description: str | None = Field(default=None, max_length=500)
    review_state: ReviewState = "pending"

    @field_validator("description", mode="before")
    @classmethod
    def optional_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class KeyDraft(SemanticModel):
    column_ids: list[UUID] = Field(default_factory=list, max_length=128)
    null_policy: Literal["reject", "group_nulls"] = "reject"
    review_state: ReviewState = "pending"


class SemanticDraft(SemanticModel):
    dataset_description: str | None = Field(default=None, max_length=2000)
    row_grain: GrainDraft = Field(default_factory=GrainDraft)
    columns: list[ColumnDraft] = Field(min_length=1, max_length=128)
    key: KeyDraft = Field(default_factory=KeyDraft)

    @field_validator("dataset_description", mode="before")
    @classmethod
    def optional_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class SemanticColumn(ColumnFacts):
    suggested_type: DataType | None
    description: str | None = None
    interpretation_type: DataType | None = None
    role: SemanticRole
    unit: str | None
    currency: str | None
    parse_format: str | None
    null_policy: NullPolicy
    review: Review


class GrainDefinition(SemanticModel):
    description: str | None
    review: Review


class KeyDefinition(SemanticModel):
    column_ids: list[UUID]
    null_policy: Literal["reject", "group_nulls"]
    review: Review


class SemanticContent(SemanticModel):
    table_ref: TableReference
    dataset_description: str | None = None
    suggestion_rules_version: str = HINTS_VERSION
    row_grain: GrainDefinition
    columns: list[SemanticColumn]
    key: KeyDefinition


class SemanticRevision(SemanticModel):
    schema_version: Literal[1] = 1
    id: UUID
    family_id: UUID
    revision: int
    previous_revision_id: UUID | None
    content: SemanticContent
    content_sha256: str
    created_by: UUID
    created_at: datetime


class ColumnSuggestion(SemanticModel):
    column_id: UUID
    suggested_role: SemanticRole
    suggested_type: DataType | None
    reasons: list[str]
    origin: Literal["heuristic"] = "heuristic"
    state: Literal["pending"] = "pending"
    rule_version: str = HINTS_VERSION


class SemanticWarning(SemanticModel):
    code: str
    message: str
    column_id: UUID | None = None


class KeyAssessment(SemanticModel):
    rule_version: Literal["semantic-key-facts-v1"] = "semantic-key-facts-v1"
    row_count: int
    duplicate_key_rows: int
    null_key_rows: int


class SemanticOrigin(SemanticModel):
    """Revisión vigente de la versión de origen de una derivada (mismos IDs de columna). Es una
    sugerencia: cargarla en el borrador no confirma nada hasta que el usuario guarda."""

    version_id: UUID
    version_number: int
    revision: SemanticReference
    draft: SemanticDraft


class UnderstandingContext(SemanticModel):
    table_ref: TableReference
    columns: list[ColumnFacts]
    schema_sha256: str
    profile: DatasetProfile | None
    head: SemanticRevision | None
    revision_count: int
    editable: SemanticDraft
    suggestions: list[ColumnSuggestion]
    warnings: list[SemanticWarning]
    key_assessment: KeyAssessment | None
    origin: SemanticOrigin | None = None


class RevisionPage(SemanticModel):
    items: list[SemanticReference]
    total: int
    limit: int
    offset: int


class SemanticSaveResult(SemanticModel):
    revision: SemanticRevision
    head_revision: int
    changed: bool


@dataclass(frozen=True)
class Representation:
    project_id: UUID
    owner_id: UUID
    table_ref: TableReference
    columns: list[ColumnFacts]
    profile: DatasetProfile | None


class RepresentationAccess(Protocol):
    def resolve(
        self, owner: UUID, artifact: UUID, with_profile: bool = False
    ) -> Representation: ...
    def require_write(self, owner: UUID, project: UUID) -> None: ...
    def origin_table(self, owner: UUID, artifact: UUID) -> tuple[UUID, int, UUID] | None:
        """(versión, número, tabla) de origen si la tabla pertenece a una derivada."""
        ...

    def key_facts(
        self, owner: UUID, artifact: UUID, columns: list[UUID], null_policy: str
    ) -> KeyAssessment: ...


class SemanticRepository(Protocol):
    def head(self, owner: UUID, artifact: UUID) -> SemanticRevision | None: ...
    def lock_family(self, representation: Representation) -> tuple[UUID, int]: ...
    def replay(self, family: UUID, key: UUID, fingerprint: str) -> SemanticRevision | None: ...
    def append(
        self, family: UUID, expected: int, revision: SemanticRevision, correlation: str
    ) -> None: ...
    def remember(self, family: UUID, key: UUID, fingerprint: str, revision: UUID) -> None: ...
    def get(self, owner: UUID, revision: UUID) -> SemanticRevision: ...
    def page(self, owner: UUID, artifact: UUID, limit: int, offset: int) -> RevisionPage: ...
