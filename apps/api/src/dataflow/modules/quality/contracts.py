from typing import Literal

from pydantic import BaseModel, ConfigDict

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
