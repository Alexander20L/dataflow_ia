from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

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


# --- Fase 12B: SQL Server ---------------------------------------------------------------------


class SqlObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_name: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)


class SqlObjectInfo(SqlObject):
    kind: Literal["table", "view"]


class SqlColumn(BaseModel):
    name: str
    sql_type: str


class ConnectionDraft(BaseModel):
    """Datos para probar una conexión. La contraseña sólo entra: nunca se devuelve."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=256)
    encrypt: bool = True
    trust_server_certificate: bool = False


class ConnectionCreate(ConnectionDraft):
    allowed_objects: list[SqlObject] = Field(min_length=1, max_length=200)


class Discovery(BaseModel):
    objects: list[SqlObjectInfo]
    can_write: bool
    server_version: str


class ConnectionResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    host: str
    port: int
    database: str
    username: str
    encrypt: bool
    trust_server_certificate: bool
    allowed_objects: list[SqlObject]
    can_write: bool
    created_at: datetime


class ExtractionRequest(SqlObject):
    pass


Consistency = Literal["snapshot", "read_committed_snapshot", "none"]


class ExtractionPreview(BaseModel):
    columns: list[SqlColumn]
    rows: list[list[str | None]]
    consistency: Consistency


class ExtractionProvenance(BaseModel):
    """Procedencia de una versión extraída de SQL Server (sin credenciales)."""

    version_id: UUID
    connection_id: UUID
    connection_name: str
    host: str
    database: str
    schema_name: str
    name: str
    columns: list[SqlColumn]
    row_count: int
    byte_count: int
    consistency: Consistency
    server_version: str
    extracted_at: datetime


class ReadSqlServerParameters(BaseModel):
    """Parámetros de ingestion.read_sqlserver@1: la extracción materializada es el original."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    connection_id: UUID
    schema_name: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    columns: list[str] = Field(min_length=1, max_length=128)
    reader: Literal["sqlserver-reader-1"] = "sqlserver-reader-1"
    materialized: Literal["parquet-text"] = "parquet-text"
