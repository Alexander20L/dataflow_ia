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
