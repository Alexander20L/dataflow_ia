from typing import Literal

from pydantic import BaseModel, ConfigDict

from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: DatasetProfile
    quality: QualityReport


class PreviewRow(BaseModel):
    row_number: int
    values: dict[str, str | None]


class PreviewPage(BaseModel):
    columns: list[str]
    rows: list[PreviewRow]
    total: int
    limit: int
    offset: int


class IngestionSummary(BaseModel):
    datasets: int
    versions: int
    processed: int
    pending: int
    failed: int


class ReadCsvParameters(BaseModel):
    """Parámetros de ingestion.read_csv@1, tal como los fija el plan de importación."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    requested_separator: Literal["auto", ",", ";", "\t"] | None = None
    separator: Literal[",", ";", "\t"]
    encoding: Literal["utf-8-sig"] = "utf-8-sig"
    strict: Literal[True] = True
    empty_cells: Literal["null"] = "null"
    blank_lines: Literal["skip"] = "skip"
