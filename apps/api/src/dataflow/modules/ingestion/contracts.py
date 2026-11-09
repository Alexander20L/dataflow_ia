from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ReadXlsxParameters(BaseModel):
    """Parámetros de ingestion.read_xlsx@1 (Fase 12A): una hoja o tabla con nombre."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    sheet: str = Field(min_length=1, max_length=31)
    table: str | None = Field(default=None, min_length=1, max_length=255)
    header_row: int = Field(default=1, ge=1, le=1_048_576)
    reader: Literal["xlsx-reader-1"] = "xlsx-reader-1"
    formulas: Literal["stored_result"] = "stored_result"
    empty_cells: Literal["null"] = "null"


class XlsxSheet(BaseModel):
    name: str
    hidden: bool
    tables: list[str]


class XlsxWarning(BaseModel):
    code: str
    cell: str
    message: str


class XlsxProblem(BaseModel):
    code: str
    message: str


class XlsxCandidate(BaseModel):
    sheet: str
    table: str | None


class XlsxSelection(BaseModel):
    """Decisión automática del sistema (Fase 13B, regla `xlsx-selection-v1`): hoja o tabla
    importada, fila de cabecera y lo que quedó fuera."""

    rule: Literal["xlsx-selection-v1"]
    sheet: str
    table: str | None
    header_row: int
    omitted: list[XlsxCandidate]


class XlsxInspection(BaseModel):
    """Hojas y tablas del libro y vista previa de la selección, antes de importar."""

    sheets: list[XlsxSheet]
    sheet: str
    table: str | None
    header_row: int
    columns: list[str]
    rows: list[list[str | None]]
    row_count: int
    warnings: list[XlsxWarning]
    warning_count: int
    problem: XlsxProblem | None = None
    selection: XlsxSelection | None = None
