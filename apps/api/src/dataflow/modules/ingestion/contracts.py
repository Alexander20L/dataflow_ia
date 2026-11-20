from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

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
    y se descarta: no se guarda, no entra en el plan ni en la huella de idempotencia. Fase 31:
    `schema_name` limita la copia a un esquema (`sqlserver-selection-v2`)."""

    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    schema_name: str | None = Field(default=None, min_length=1, max_length=128)
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


class PostgresConnection(BaseModel):
    """Fase 31: datos de conexión de un solo uso a PostgreSQL. Como en SQL Server, la contraseña
    se usa para copiar las tablas de un esquema y se descarta."""

    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63)
    schema_name: str = Field(default="public", min_length=1, max_length=63)
    user: str = Field(min_length=1, max_length=63)
    password: SecretStr = Field(min_length=1, max_length=256)
    # Fase 32 (ADR-050): certificado de la autoridad del proveedor (PEM) para verificar la
    # conexión en el modo público. Como la contraseña, se usa en esa conexión y se descarta.
    ca_certificate: SecretStr | None = Field(default=None, max_length=16384)

    @field_validator("ca_certificate")
    @classmethod
    def pem(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        if "-----BEGIN CERTIFICATE-----" not in value.get_secret_value():
            raise ValueError(
                "El certificado debe estar en formato PEM (-----BEGIN CERTIFICATE-----)."
            )
        return value


class RelatedFile(BaseModel):
    """Fase 31: un archivo de un conjunto relacionado (CSV o .xlsx), en base64."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class RelatedFilesRequest(BaseModel):
    """Fase 31: de 2 a 5 archivos que se analizan por separado y, si comparten claves, unidos
    (`relations-v1`)."""

    model_config = ConfigDict(extra="forbid")
    files: list[RelatedFile] = Field(min_length=2, max_length=5)


class RelatedTable(BaseModel):
    """Fase 31: una tabla del modelo de datos con sus columnas, claves y papel: de hechos
    (apunta a otras y nadie apunta a ella), entidad principal (a ella apuntan las de hechos),
    dimensión (describe a otra) o por separado (sin clave común)."""

    label: str
    rows: int
    columns: int
    headers: list[str] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    role: Literal["fact", "entity", "dimension", "separate"]
    reason: str


class TableRelation(BaseModel):
    """Fase 31: relación entre dos tablas (`table.column` → `references_table.references_column`),
    su cardinalidad y si se usó en alguna vista, con su motivo."""

    table: str
    column: str
    references_table: str
    references_column: str
    origin: Literal["declared", "detected"]
    cardinality: Literal["N:1", "1:1"] = "N:1"
    status: Literal["joined", "not_joined"]
    reason: str
    added_columns: list[str] = Field(default_factory=list)


class RelatedView(BaseModel):
    """Fase 31: una vista del modelo que se analiza como versión propia: la de una tabla de
    hechos con lo que apunta (`fact`) o la vista general por entidad con métricas de cada tabla
    de hechos (`entity`)."""

    name: str
    kind: Literal["fact", "entity"]
    base: str
    tables: list[str]
    rows: int
    columns: int
    headers: list[str] = Field(default_factory=list)
    description: str


class SourceOrigin(BaseModel):
    """De dónde sale una versión que no es un archivo tabular (Fase 18B): una tabla copiada de
    SQL Server o una tabla de un PDF. Decisión del sistema; no hay nada que elegir. Fase 31: una
    tabla copiada de PostgreSQL, o una versión de un conjunto relacionado (`related`): una de sus
    tablas o una vista (`joined`), con el modelo de datos que decidió `relations-v1`."""

    kind: Literal["sqlserver", "pdf", "postgresql", "related"]
    rule: Literal[
        "sqlserver-selection-v1",
        "sqlserver-selection-v2",
        "sqlserver-selection-v3",
        "pdf-selection-v1",
        "postgresql-selection-v1",
        "postgresql-selection-v2",
        "relations-v1",
    ]
    table: str
    server: str | None = None
    database: str | None = None
    captured_at: str | None = None
    pages: list[int] = Field(default_factory=list)
    excluded_columns: list[ExcludedColumn] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    analyzed_together: list[str] = Field(default_factory=list)
    omitted: list[OmittedSource] = Field(default_factory=list)
    # Fase 31: modelo de datos del conjunto; `joined` y `view_kind` si la versión es una vista.
    joined: bool = False
    view_kind: Literal["fact", "entity"] | None = None
    tables: list[RelatedTable] = Field(default_factory=list)
    relations: list[TableRelation] = Field(default_factory=list)
    views: list[RelatedView] = Field(default_factory=list)
    # Fase 32: cómo se llegó a la base (servidor de la lista o modo público) y cómo se cifró.
    access: Literal["allowlist", "public"] | None = None
    tls: Literal["verified", "encrypted", "none"] | None = None


class DataModel(BaseModel):
    """Fase 31: «foto» del esquema antes de analizar (no guarda nada): tablas con sus columnas y
    claves, relaciones y las vistas que se analizarían; `main` es la vista que se abriría."""

    rule: Literal["relations-v1"] = "relations-v1"
    main: str | None
    tables: list[RelatedTable]
    relations: list[TableRelation]
    views: list[RelatedView]
    omitted: list[OmittedSource] = Field(default_factory=list)


class RelatedSet(BaseModel):
    """Resultado de `relations-v1` (interno entre el subproceso y la API): el modelo y cada vista
    como CSV estándar (`csv`, por nombre de vista). `xlsx`: la hoja o tabla que se leyó de cada
    libro (por etiqueta)."""

    main: str | None
    tables: list[RelatedTable]
    relations: list[TableRelation]
    views: list[RelatedView] = Field(default_factory=list)
    csv: dict[str, str] = Field(default_factory=dict)
    xlsx: dict[str, XlsxSelection] = Field(default_factory=dict)


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
    # Fase 32: lo decide el subproceso, que es quien conecta.
    access: Literal["allowlist", "public"] | None = None
    tls: Literal["verified", "encrypted", "none"] | None = None


class ConnectorPolicy(BaseModel):
    """Fase 32B: la política de destinos tal como viaja de la API al servicio `connector`."""

    model_config = ConfigDict(extra="forbid")
    allowed_hosts: list[str] = Field(default_factory=list, max_length=100)
    public: bool = False
    denied: list[str] = Field(default_factory=list, max_length=500)


class ConnectorSnapshotRequest(BaseModel):
    """Fase 32B (ADR-050): petición interna de la API al servicio `connector` para copiar un
    esquema de PostgreSQL. Lleva la contraseña (y el certificado, si lo hay) sólo para esa
    copia; el conector no guarda nada y repite la regla de destinos antes de conectar."""

    model_config = ConfigDict(extra="forbid")
    connection: PostgresConnection
    policy: ConnectorPolicy
    max_rows: int = Field(ge=1, le=100_000)
    max_columns: int = Field(ge=1, le=128)
    # Fase 33: la copia de una base entera, en segundo plano, puede tardar hasta una hora.
    timeout_seconds: int = Field(ge=5, le=3600)
    max_bytes: int = Field(ge=1, le=2 * 1024 * 1024 * 1024)
    max_cell_bytes: int = Field(ge=1, le=1024 * 1024)


class DatabaseAccess(BaseModel):
    """Fase 32 (ADR-050): a qué bases se puede conectar en este entorno, para que la pantalla
    de carga muestre lo que corresponde. `public`: cualquier servidor accesible desde internet
    (sólo PostgreSQL); `allowlist`: sólo los de la lista; `disabled`: ninguno."""

    postgresql: Literal["disabled", "allowlist", "public"]
    sqlserver: Literal["disabled", "allowlist"]
    egress_ips: list[str] = Field(default_factory=list)


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


class DatabaseCopy(BaseModel):
    """Fase 33 (ADR-051): una copia de base en segundo plano. `photo` («Ver esquema»): al terminar
    trae `model`; `import` («Analizar»): trae la versión principal (`version_id`). Nunca la
    contraseña ni el certificado."""

    id: UUID
    project_id: UUID
    engine: Literal["postgresql", "sqlserver"]
    kind: Literal["photo", "import"]
    state: Literal["queued", "running", "succeeded", "failed"]
    server: str
    database: str
    schema_name: str | None = None
    tables: int | None = None
    omitted: int | None = None
    version_id: UUID | None = None
    model: DataModel | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
