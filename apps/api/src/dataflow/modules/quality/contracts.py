from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WHITESPACE_CHARS = " \t\r\n"


class QualityIssue(BaseModel):
    id: str
    rule: Literal["Q-001", "Q-002", "Q-003"]
    column: str | None
    severity: Literal["medium", "low"]
    affected_rows: int
    sample_row_numbers: list[int]
    description: str
    proposed_action: str


class AnalyticalFinding(BaseModel):
    """Hallazgo de automatic-quality-v1: qué problema hay y qué análisis afecta.

    `blocking` bloquea sólo los análisis listados, no el resto del dashboard. Una observación
    (`info`) no es un error: nada se corrige automáticamente."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    check: Literal["AQ-001", "AQ-002", "AQ-003", "AQ-004", "AQ-005", "AQ-006", "AQ-007", "AQ-008"]
    title: str
    severity: Literal["info", "warning", "blocking"]
    columns: list[str]
    affected_rows: int = Field(ge=0)
    sample_row_numbers: list[int]
    evidence: list[str]
    affected_analyses: list[str]


class AnalyticalQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rules_version: Literal["automatic-quality-v1"] = "automatic-quality-v1"
    interpretation_rules: Literal["automatic-interpretation-v2"] = "automatic-interpretation-v2"
    findings: list[AnalyticalFinding]
    blocking: int = Field(ge=0)
    warnings: int = Field(ge=0)
    observations: int = Field(ge=0)


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_version: Literal["csv-quality-v1"] = "csv-quality-v1"
    row_count: int
    cell_count: int
    missing_cells: int
    duplicate_rows: int
    whitespace_cells: int
    completeness_percent: float
    issues: list[QualityIssue]
    # quality.evaluate@3 (Fase 14): hallazgos analíticos; @1 lo omite al serializar.
    analytical: AnalyticalQuality | None = None

    def serialized(self, version: int) -> str:
        """quality.evaluate@1 conserva exactamente su serialización anterior."""
        if version == 1:
            return self.model_dump_json(exclude={"analytical"})
        return self.model_dump_json()


QUALITY_RULES: list[Literal["Q-001", "Q-002", "Q-003"]] = ["Q-001", "Q-002", "Q-003"]


class QualityParameters(BaseModel):
    """Parámetros de quality.evaluate@1: conjunto exacto csv-quality-v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_set: Literal["csv-quality-v1"] = "csv-quality-v1"
    rules: list[Literal["Q-001", "Q-002", "Q-003"]] = Field(
        default_factory=lambda: list(QUALITY_RULES)
    )
    score: Literal["cell_completeness_v1"] = "cell_completeness_v1"

    @field_validator("rules")
    @classmethod
    def exact_rule_set(
        cls, value: list[Literal["Q-001", "Q-002", "Q-003"]]
    ) -> list[Literal["Q-001", "Q-002", "Q-003"]]:
        if value != QUALITY_RULES:
            raise ValueError("csv-quality-v1 evalúa exactamente Q-001, Q-002 y Q-003.")
        return value


class AnalyticalQualityParameters(BaseModel):
    """quality.evaluate@3: csv-quality-v1 más hallazgos automatic-quality-v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_set: Literal["csv-quality-v1"] = "csv-quality-v1"
    rules: list[Literal["Q-001", "Q-002", "Q-003"]] = Field(
        default_factory=lambda: list(QUALITY_RULES)
    )
    score: Literal["cell_completeness_v1"] = "cell_completeness_v1"
    analytical_rules: Literal["automatic-quality-v1"] = "automatic-quality-v1"

    @field_validator("rules")
    @classmethod
    def exact_rule_set(
        cls, value: list[Literal["Q-001", "Q-002", "Q-003"]]
    ) -> list[Literal["Q-001", "Q-002", "Q-003"]]:
        if value != QUALITY_RULES:
            raise ValueError("csv-quality-v1 evalúa exactamente Q-001, Q-002 y Q-003.")
        return value
