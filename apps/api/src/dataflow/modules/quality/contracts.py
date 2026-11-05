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
