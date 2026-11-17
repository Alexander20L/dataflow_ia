from typing import Literal

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


class RecordsPage(PreviewPage):
    """Fase 22: página de registros con los identificadores de columna (mismo orden que
    `columns`) y el orden y la búsqueda aplicados; `total` cuenta las filas que cumplen el
    filtro y la búsqueda. `PreviewPage` no cambia."""

    column_ids: list[str] = Field(default_factory=list)
    sort: str | None = None
    descending: bool = False
    search: str | None = None


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


class ReadCsvV2Parameters(BaseModel):
    """Parámetros de ingestion.read_csv@2 (Fase 18): codificación resuelta al subir (UTF-8 o
    Windows-1252) y valores regionales leídos con `regional-values-v1`."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    requested_separator: Literal["auto", ",", ";", "	"] | None = None
    separator: Literal[",", ";", "	"]
    encoding: Literal["utf-8-sig", "cp1252"]
    values: Literal["regional-values-v1"] = "regional-values-v1"
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


class ReadXlsxV2Parameters(ReadXlsxParameters):
    """ingestion.read_xlsx@2 (Fase 18): como @1 y, además, los textos con números o fechas
    regionales se leen con `regional-values-v1` (los números nativos de Excel no cambian)."""

    values: Literal["regional-values-v1"] = "regional-values-v1"


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
    importada, fila de cabecera y lo que quedó fuera. Desde la Fase 18 (`xlsx-selection-v2`)
    las demás tablas con datos del libro se analizan como versiones propias de la misma carga
    (`analyzed_together`); `omitted` sólo lista lo que no se analiza."""

    rule: Literal["xlsx-selection-v1", "xlsx-selection-v2"]
    sheet: str
    table: str | None
    header_row: int
    omitted: list[XlsxCandidate]
    analyzed_together: list[XlsxCandidate] = Field(default_factory=list)


class XlsxChoice(BaseModel):
    """Una tabla del libro que `xlsx-selection-v2` analiza (con su fila de cabecera)."""

    sheet: str
    table: str | None
    header_row: int


class ConvertedColumn(BaseModel):
    """Columna leída con un formato regional (Fase 18, `regional-values-v1`)."""

    column: str
    kind: Literal["number", "date"]
    format: Literal[
        "decimal_comma",
        "decimal_point_grouped",
        "day_month_year",
        "month_day_year",
        "year_month_day",
    ]
    values: int
    by_file_convention: bool
    explanation: str


class KeptColumn(BaseModel):
    """Columna que parecía regional pero se dejó como texto por ambigua."""

    column: str
    kind: Literal["number", "date"]
    reason: str


class SourceReading(BaseModel):
    """Cómo se leyó el original: codificación, separador y valores regionales. Se guarda en
    los metadatos de la tabla leída (no es un artefacto aparte)."""

    rule: Literal["regional-values-v1"] = "regional-values-v1"
    format: Literal["csv", "xlsx", "pdf"]
    encoding: Literal["utf-8-sig", "cp1252"] | None = None
    separator: str | None = None
    convention: Literal["decimal_comma", "decimal_point_grouped"] | None = None
    converted: list[ConvertedColumn] = Field(default_factory=list)
    kept_as_text: list[KeptColumn] = Field(default_factory=list)


class SheetFacts(BaseModel):
    name: str
    hidden: bool
    tables: list[str]
    selected: bool


class SourceFacts(BaseModel):
    """Datos del original que la pestaña Dataset muestra (Fase 22, `source-facts-v1`). Los
    calcula el subproceso de ingesta, el único que abre el original con sus lectores; nunca
    cambia lo que se leyó ni el archivo."""

    rule: Literal["source-facts-v1"] = "source-facts-v1"
    format: Literal["csv", "xlsx", "pdf", "other"]
    size_bytes: int
    # CSV: codificación y separador con que se leyó, líneas en blanco omitidas y registros.
    encoding: str | None = None
    separator: str | None = None
    blank_lines: int | None = None
    # Excel: hojas del libro, rango leído, filas y columnas vacías dentro del rango, celdas
    # con fórmula (se lee su resultado guardado) y celdas con formato de fecha.
    sheets: list[SheetFacts] = Field(default_factory=list)
    sheet: str | None = None
    table: str | None = None
    used_range: str | None = None
    header_row: int | None = None
    empty_rows: int | None = None
    empty_columns: list[str] = Field(default_factory=list)
    formula_cells: int | None = None
    date_cells: int | None = None
    inexact_numbers: int | None = None
    problems: list[str] = Field(default_factory=list)


class ReadPdfParameters(BaseModel):
    """ingestion.read_pdf@1 (Fase 18B): una tabla lógica del PDF (segmentos página/índice con la
    misma cabecera) y valores regionales con convención de archivo."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    segments: list[tuple[int, int]] = Field(min_length=1)
    reader: Literal["pdfplumber-lines-1"] = "pdfplumber-lines-1"
    values: Literal["regional-values-v1"] = "regional-values-v1"
    empty_cells: Literal["null"] = "null"


class SqlServerConnection(BaseModel):
    """Datos de conexión de un solo uso (Fase 18B). La contraseña se usa para copiar las tablas
    y se descarta: no se guarda, no entra en el plan ni en la huella de idempotencia."""

    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    user: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=256)


class ExcludedColumn(BaseModel):
    column: str
    type: str
    reason: str


class ForeignKey(BaseModel):
    """Clave foránea declarada en la base (Fase 19): columna → esquema.tabla.columna."""

    column: str
    references: str


class OmittedSource(BaseModel):
    table: str
    reason: str


class SourceOrigin(BaseModel):
    """De dónde sale una versión que no es un archivo tabular (Fase 18B): una tabla copiada de
    SQL Server o una tabla de un PDF. Decisión del sistema; no hay nada que elegir."""

    kind: Literal["sqlserver", "pdf"]
    rule: Literal["sqlserver-selection-v1", "pdf-selection-v1"]
    table: str
    server: str | None = None
    database: str | None = None
    captured_at: str | None = None
    pages: list[int] = Field(default_factory=list)
    excluded_columns: list[ExcludedColumn] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    analyzed_together: list[str] = Field(default_factory=list)
    omitted: list[OmittedSource] = Field(default_factory=list)


class SnapshotTable(BaseModel):
    """Tabla copiada (interno entre el subproceso y la API)."""

    label: str
    headers: list[str]
    csv: str
    excluded_columns: list[ExcludedColumn] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class SqlSnapshot(BaseModel):
    tables: list[SnapshotTable]
    omitted: list[OmittedSource]


class PdfChoice(BaseModel):
    label: str
    segments: list[tuple[int, int]]


class PdfSelection(BaseModel):
    main: PdfChoice
    additional: list[PdfChoice]
    omitted: list[OmittedSource]


class ColumnChange(BaseModel):
    column: str
    change: Literal["added", "removed", "type_changed", "role_changed"]
    before: str | None = None
    after: str | None = None
    description: str = ""


class StructureComparison(BaseModel):
    """Cambios de columnas respecto de la versión anterior del mismo archivo (Fase 18).
    Sólo se informa: no se renombra ni se mapea nada."""

    rule: Literal["structure-comparison-v1"] = "structure-comparison-v1"
    previous_version_id: str
    previous_version_number: int
    changes: list[ColumnChange]
    unchanged: int


class SourceReview(BaseModel):
    """Lectura del archivo y cambios de estructura de una versión (GET /versions/{id}/reading).
    `reading` es None en versiones leídas antes de la Fase 18; `structure`, si no hay una
    versión anterior comparable."""

    reading: SourceReading | None
    structure: StructureComparison | None
    # Fase 18B: tabla copiada de SQL Server o tabla de un PDF.
    origin: SourceOrigin | None = None


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
    # Fase 18: otras tablas que se analizan como versiones propias de la misma carga.
    additional: list[XlsxChoice] = Field(default_factory=list)
