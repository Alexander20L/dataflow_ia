import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4, uuid5

from dataflow.modules.analytics.contracts import AutomaticAnalysis, AutomaticEvidence
from dataflow.modules.datasets.public import Datasets, DatasetVersion, ObjectStore
from dataflow.modules.executions.public import (
    Execution,
    Executions,
    PlanRevision,
    ProcessingConfig,
    legacy_state,
)
from dataflow.modules.ingestion.contracts import (
    Diagnostic,
    IngestionSummary,
    PdfChoice,
    PdfSelection,
    PreviewPage,
    ReadPdfParameters,
    ReadXlsxParameters,
    SourceOrigin,
    SourceReading,
    SourceReview,
    SqlServerConnection,
    SqlSnapshot,
    XlsxCandidate,
    XlsxInspection,
    XlsxSelection,
)
from dataflow.modules.ingestion.domain import ImportState, Version
from dataflow.modules.ingestion.plans import (
    analysis_fingerprint,
    build_plan,
    import_fingerprint,
    resolve_encoding,
    resolve_separator,
    xlsx_import_fingerprint,
)
from dataflow.modules.ingestion.structure import compare
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import SemanticReference, SemanticService, TableReference
from dataflow.platform.canonical import digest
from dataflow.platform.csv_export import CsvProfile, table_csv
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


@dataclass(frozen=True)
class AnalysisOutput:
    profile: DatasetProfile | None
    quality: QualityReport
    parquet: bytes

    @property
    def diagnostic(self) -> Diagnostic:
        assert self.profile is not None
        return Diagnostic(profile=self.profile, quality=self.quality)


@dataclass(frozen=True)
class ReadOutput:
    parquet: bytes
    separator: str
    source_sha256: str
    row_count: int
    column_count: int


class Analyzer(Protocol):
    """Motor aislado por paso; cada llamada respeta el plazo restante del plan."""

    def quality_rules(
        self,
        table: bytes,
        columns: list[dict[str, Any]],
        rules: list[dict[str, Any]],
        reference: dict[str, Any],
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes: ...

    def read(
        self,
        content: bytes,
        separator: str,
        config: ProcessingConfig,
        timeout: float,
        encoding: str | None = None,
    ) -> ReadOutput: ...
    def read_xlsx(
        self,
        content: bytes,
        parameters: ReadXlsxParameters,
        config: ProcessingConfig,
        timeout: float,
    ) -> ReadOutput: ...
    def read_pdf(
        self,
        content: bytes,
        parameters: ReadPdfParameters,
        config: ProcessingConfig,
        timeout: float,
    ) -> ReadOutput: ...
    def profile(
        self,
        table: bytes,
        separator: str,
        source_sha256: str,
        config: ProcessingConfig,
        timeout: float,
        include_overview: bool = False,
        include_interpretation: bool = False,
        include_analysis: bool = False,
    ) -> DatasetProfile: ...
    def quality(
        self, table: bytes, config: ProcessingConfig, timeout: float, analytical: bool = False
    ) -> QualityReport: ...


class XlsxInspector(Protocol):
    """Lista hojas/tablas y previsualiza la selección en el subproceso aislado (Fase 12A). Desde
    la Fase 18B también elige las tablas de un PDF y copia las de SQL Server."""

    def select_pdf(self, content: bytes, config: ProcessingConfig) -> PdfSelection: ...
    def snapshot_sqlserver(
        self, connection: SqlServerConnection, config: ProcessingConfig
    ) -> SqlSnapshot: ...

    def inspect_xlsx(
        self,
        content: bytes,
        sheet: str | None,
        table: str | None,
        header_row: int,
        config: ProcessingConfig,
    ) -> XlsxInspection: ...


XLSX_REJECTED = (".xls", ".xlsm", ".xlsb", ".xltm", ".xlt")
UNSAFE_NAME = "/\\\x00\r\n"


class PreviewReader(Protocol):
    def read(
        self,
        content: bytes,
        limit: int,
        offset: int,
        rule: str | None = None,
        column: str | None = None,
    ) -> PreviewPage: ...
    def source_reading(self, content: bytes) -> SourceReading | None: ...


class ProjectAccess(Protocol):
    def require(self, owner_id: UUID, project_id: UUID, writable: bool = False) -> None: ...


def legacy_view(
    version: DatasetVersion, run: Execution, parent_version_id: UUID | None = None
) -> Version:
    return Version(
        version.id,
        version.dataset_id,
        version.project_id,
        version.number,
        version.file_name,
        version.content.sha256,
        version.content.byte_size,
        version.created_at,
        run.id,
        cast(ImportState, legacy_state(run.state)),
        run.row_count,
        run.column_count,
        run.error_code,
        run.error_message,
        run.attempts,
        version.kind,
        parent_version_id,
        run.plan.content.get("source_selection") if run.plan else None,
        run.plan.content.get("source_origin") if run.plan else None,
    )


@dataclass(frozen=True)
class Sibling:
    """Otra tabla de la misma fuente que se registra como versión propia (Fase 18)."""

    key: UUID
    fingerprint: str
    plan: Callable[[DatasetVersion], PlanRevision]
    content: bytes | None = None  # None: comparte el original de la versión principal
    name: str | None = None


def table_file_name(label: str) -> str:
    """Nombre de archivo de una tabla copiada (esquema.tabla.csv) sin caracteres inseguros."""
    safe = "".join("_" if c in UNSAFE_NAME or ord(c) < 32 else c for c in label)
    return f"{safe[:250]}.csv"


class IngestionService:
    """Coordina una carga; datasets y executions son dueños de sus registros."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        projects: ProjectAccess,
        preview: PreviewReader,
        uow: UnitOfWork,
        config: ProcessingConfig,
        quota: int,
        maximum_upload: int = 5 * 1024 * 1024,
        inspector: XlsxInspector | None = None,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.projects, self.preview_reader, self.uow = projects, preview, uow
        self.config, self.quota, self.maximum_upload = config, quota, maximum_upload
        self.inspector = inspector

    def submit(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        separator: str,
        key: UUID,
        correlation: str,
    ) -> Version:
        try:
            if (
                not name.lower().endswith(".csv")
                or any(c in name for c in UNSAFE_NAME)
                or len(name) > 255
            ):
                raise ApplicationError(
                    "CSV_REQUIRED", "Selecciona un nombre de archivo CSV válido.", 422
                )
            self._check_content(content, "El CSV supera el límite de tamaño.")
            if separator not in {"auto", ",", ";", "tab"}:
                raise ApplicationError("CSV_SEPARATOR", "Separador no admitido.", 422)
        except Exception:
            self.uow.rollback()
            raise
        return self._register(
            owner,
            project,
            name,
            content,
            key,
            correlation,
            "csv",
            import_fingerprint(name, hashlib.sha256(content).hexdigest(), separator),
            lambda version: build_plan(
                owner,
                version,
                self.config,
                separator,
                resolve_separator(content, separator, resolve_encoding(content)),
                encoding=resolve_encoding(content),
            ),
        )

    def submit_xlsx(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        parameters: ReadXlsxParameters | None,
        key: UUID,
        correlation: str,
    ) -> Version:
        """Un libro .xlsx. Sin hoja ni tabla (Fase 13B), el sistema elige con la regla
        `xlsx-selection-v2` (Fase 18) y la decisión queda en el plan: la tabla principal es la
        versión que se devuelve y las demás tablas con datos se registran como versiones propias
        de la misma carga. Con hoja o tabla explícitas (Fase 12A) se respeta y no hay más.
        Un libro que no se puede abrir se rechaza aquí; un problema de la hoja elegida se
        registra y falla en el worker conservando el original."""
        selection: XlsxSelection | None = None
        siblings: list[Sibling] = []
        sha256 = hashlib.sha256(content).hexdigest()
        if parameters is None:
            inspection = self.inspect_xlsx(owner, project, name, content, None, None, 1)
            selection = inspection.selection
            assert selection is not None
            parameters = ReadXlsxParameters(
                sheet=selection.sheet, table=selection.table, header_row=selection.header_row
            )
            tables = [
                XlsxCandidate(sheet=selection.sheet, table=selection.table),
                *(XlsxCandidate(sheet=c.sheet, table=c.table) for c in inspection.additional),
            ]
            for choice in inspection.additional:
                own = ReadXlsxParameters(
                    sheet=choice.sheet, table=choice.table, header_row=choice.header_row
                )
                decision = selection.model_copy(
                    update={
                        "sheet": choice.sheet,
                        "table": choice.table,
                        "header_row": choice.header_row,
                        "analyzed_together": [
                            t for t in tables if (t.sheet, t.table) != (choice.sheet, choice.table)
                        ],
                    }
                )
                siblings.append(
                    Sibling(
                        uuid5(key, f"xlsx-table:{choice.sheet}:{choice.table or ''}"),
                        xlsx_import_fingerprint(name, sha256, own),
                        self._xlsx_plan(owner, own, decision),
                    )
                )
        try:
            self._check_xlsx(name, content)
        except Exception:
            self.uow.rollback()
            raise
        chosen = parameters
        return self._register(
            owner,
            project,
            name,
            content,
            key,
            correlation,
            "xlsx",
            xlsx_import_fingerprint(name, sha256, chosen),
            lambda version: build_plan(
                owner, version, self.config, xlsx=chosen, source_selection=selection
            ),
            siblings,
        )

    def submit_pdf(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        key: UUID,
        correlation: str,
    ) -> Version:
        """Fase 18B: un PDF con texto. La regla `pdf-selection-v1` elige la tabla principal (la
        versión que se devuelve) y hasta cuatro más, cada una como versión propia que comparte el
        original. Un PDF sin tablas, escaneado o protegido se rechaza aquí con su motivo."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        lowered = name.lower()
        if not lowered.endswith(".pdf") or any(c in name for c in UNSAFE_NAME) or len(name) > 255:
            raise ApplicationError("PDF_REQUIRED", "Selecciona un archivo PDF válido.", 422)
        self._check_content(content, "El PDF supera el límite de tamaño.")
        if not content.startswith(b"%PDF-"):
            raise ApplicationError("PDF_MALFORMED", "El archivo no es un PDF.", 422)
        if self.inspector is None:
            raise ApplicationError("PDF_UNAVAILABLE", "La lectura de PDF no está activa.", 503)
        chosen = self.inspector.select_pdf(content, self.config)
        tables = [chosen.main, *chosen.additional]
        sha256 = hashlib.sha256(content).hexdigest()
        omitted = [o.model_dump() for o in chosen.omitted]

        def origin(table: PdfChoice) -> SourceOrigin:
            return SourceOrigin(
                kind="pdf",
                rule="pdf-selection-v1",
                table=table.label,
                pages=sorted({page for page, _ in table.segments}),
                analyzed_together=[t.label for t in tables if t is not table],
                omitted=omitted,
            )

        def plan(table: PdfChoice) -> Callable[[DatasetVersion], PlanRevision]:
            parameters = ReadPdfParameters(segments=table.segments)
            decision = origin(table)
            return lambda version: build_plan(
                owner, version, self.config, pdf=parameters, source_origin=decision
            )

        def fingerprint(table: PdfChoice) -> str:
            return digest(
                "import_request",
                {"name": name, "sha256": sha256, "pdf": [list(s) for s in table.segments]},
            )

        return self._register(
            owner,
            project,
            name,
            content,
            key,
            correlation,
            "pdf",
            fingerprint(chosen.main),
            plan(chosen.main),
            [
                Sibling(uuid5(key, f"pdf-table:{t.segments}"), fingerprint(t), plan(t))
                for t in chosen.additional
            ],
        )

    def submit_sqlserver(
        self,
        owner: UUID,
        project: UUID,
        connection: SqlServerConnection,
        allowed_hosts: Sequence[str],
        key: UUID,
        correlation: str,
    ) -> Version:
        """Fase 18B: copia de un solo uso de las tablas de una base de SQL Server. Sólo hosts de
        la lista permitida (evita usar el servidor para llegar a equipos internos). Cada tabla
        elegida por `sqlserver-selection-v1` se guarda como CSV estándar inmutable (su original)
        y se analiza como versión propia; la contraseña no se guarda."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        allowed = {host.strip().lower() for host in allowed_hosts if host.strip()}
        if not allowed:
            raise ApplicationError(
                "SQLSERVER_DISABLED",
                "La conexión a SQL Server no está activada en este entorno.",
                503,
            )
        if connection.server.lower() not in allowed:
            raise ApplicationError(
                "SQLSERVER_HOST_NOT_ALLOWED",
                "Ese servidor no está en la lista de servidores permitidos.",
                422,
            )
        if self.inspector is None:
            raise ApplicationError("SQLSERVER_UNAVAILABLE", "SQL Server no está activo.", 503)
        snapshot = self.inspector.snapshot_sqlserver(connection, self.config)
        captured = datetime.now(UTC).replace(microsecond=0).isoformat()
        labels = [t.label for t in snapshot.tables]
        parts = []
        for table in snapshot.tables:
            data = table.csv.encode("utf-8")
            if len(data) > self.maximum_upload:
                raise ApplicationError(
                    "SQLSERVER_TABLE_TOO_LARGE",
                    f"La tabla {table.label} supera el tamaño máximo de un original.",
                    413,
                )
            decision = SourceOrigin(
                kind="sqlserver",
                rule="sqlserver-selection-v1",
                table=table.label,
                server=f"{connection.server}:{connection.port}",
                database=connection.database,
                captured_at=captured,
                excluded_columns=table.excluded_columns,
                analyzed_together=[label for label in labels if label != table.label],
                omitted=snapshot.omitted,
            )
            file_name = table_file_name(table.label)
            fingerprint = digest(
                "import_request",
                {
                    "name": file_name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "sqlserver": f"{connection.server}:{connection.port}/{connection.database}",
                },
            )
            parts.append((table, data, file_name, fingerprint, self._csv_plan(owner, decision)))
        main, *rest = parts
        return self._register(
            owner,
            project,
            main[2],
            main[1],
            key,
            correlation,
            "csv",
            main[3],
            main[4],
            [
                Sibling(uuid5(key, f"sqlserver-table:{t.label}"), fp, plan, data, file_name)
                for t, data, file_name, fp, plan in rest
            ],
        )

    def _csv_plan(
        self, owner: UUID, decision: SourceOrigin
    ) -> Callable[[DatasetVersion], PlanRevision]:
        """Tabla copiada como CSV estándar (UTF-8, coma): se lee con read_csv del catálogo."""

        def plan(version: DatasetVersion) -> PlanRevision:
            return build_plan(owner, version, self.config, ",", ",", source_origin=decision)

        return plan

    def _xlsx_plan(
        self, owner: UUID, parameters: ReadXlsxParameters, decision: XlsxSelection
    ) -> Callable[[DatasetVersion], PlanRevision]:
        def plan(version: DatasetVersion) -> PlanRevision:
            return build_plan(
                owner, version, self.config, xlsx=parameters, source_selection=decision
            )

        return plan

    def inspect_xlsx(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        sheet: str | None,
        table: str | None,
        header_row: int,
    ) -> XlsxInspection:
        """Vista previa antes de activar: no guarda nada."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        self._check_xlsx(name, content)
        if self.inspector is None:
            raise ApplicationError("XLSX_UNAVAILABLE", "La lectura de Excel no está activa.", 503)
        return self.inspector.inspect_xlsx(content, sheet, table, header_row, self.config)

    def _check_content(self, content: bytes, too_large: str) -> None:
        if not content:
            raise ApplicationError("EMPTY_FILE", "El archivo está vacío.", 422)
        if len(content) > self.maximum_upload:
            raise ApplicationError("FILE_TOO_LARGE", too_large, 413)

    def _check_xlsx(self, name: str, content: bytes) -> None:
        lowered = name.lower()
        if any(c in name for c in UNSAFE_NAME) or len(name) > 255:
            raise ApplicationError("XLSX_REQUIRED", "Nombre de archivo no válido.", 422)
        if lowered.endswith(XLSX_REJECTED):
            raise ApplicationError(
                "UNSUPPORTED_FORMAT",
                "Sólo se admiten libros .xlsx; guarda el archivo como «Libro de Excel (.xlsx)».",
                422,
            )
        if not lowered.endswith(".xlsx"):
            raise ApplicationError("XLSX_REQUIRED", "Selecciona un libro de Excel .xlsx.", 422)
        self._check_content(content, "El libro supera el límite de tamaño.")

    def _register(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        key: UUID,
        correlation: str,
        extension: str,
        fingerprint: str,
        plan: Callable[[DatasetVersion], PlanRevision],
        siblings: Sequence[Sibling] = (),
    ) -> Version:
        """Registra la versión y su carga. `siblings` (Fase 18): otras tablas de la misma fuente,
        cada una como versión propia encolada en la misma transacción; comparten el original
        (libros y PDF, un solo objeto) o traen el suyo (tablas copiadas de SQL Server)."""
        try:
            self.projects.require(owner, project)
            self.datasets.lock_owner(owner)
            existing = self.executions.find_request(owner, project, "csv_import", key, fingerprint)
            if existing:
                result = legacy_view(self.datasets.get(owner, existing.version_id), existing)
                self.uow.rollback()
                return result
            self.projects.require(owner, project, writable=True)
            self.executions.ensure_capacity(owner, project, "csv_import")
            extra = sum(len(s.content) for s in siblings if s.content is not None)
            if self.datasets.used_bytes(owner) + len(content) + extra > self.quota:
                raise ApplicationError(
                    "STORAGE_QUOTA", "Se alcanzó la cuota de archivos originales de la cuenta.", 413
                )
            version_id = uuid4()
            digest_hex = hashlib.sha256(content).hexdigest()
            source = self.objects.put(
                f"originals/{owner}/{version_id}/{digest_hex}.{extension}", content
            )
            # Las tablas secundarias reciben antes su número: la principal queda como la versión
            # más reciente (la que se abre), y su carga se encola primero.
            registered: list[tuple[Sibling, DatasetVersion]] = []
            for item in siblings:
                sibling_id = uuid4()
                own = source
                if item.content is not None:
                    own = self.objects.put(
                        f"originals/{owner}/{sibling_id}/"
                        f"{hashlib.sha256(item.content).hexdigest()}.{extension}",
                        item.content,
                    )
                registered.append(
                    (
                        item,
                        self.datasets.register(owner, project, sibling_id, item.name or name, own),
                    )
                )
            version = self.datasets.register(owner, project, version_id, name, source)
            run = self.executions.enqueue(
                owner,
                project,
                version_id,
                "csv_import",
                key,
                fingerprint,
                plan(version),
                correlation,
            )
            self.datasets.bind_import(version_id, run.id)
            for item, sibling in registered:
                sibling_id = sibling.id
                sibling_run = self.executions.enqueue(
                    owner,
                    project,
                    sibling_id,
                    "csv_import",
                    item.key,
                    item.fingerprint,
                    item.plan(sibling),
                    correlation,
                )
                self.datasets.bind_import(sibling_id, sibling_run.id)
            self.uow.commit()
            return legacy_view(version, run)
        except Exception:
            self.uow.rollback()
            raise

    def versions(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[Version], int]:
        self.projects.require(owner, project)
        versions, total = self.datasets.versions(owner, project, limit, offset)
        return [self._view(owner, version) for version in versions], total

    def version(self, owner: UUID, version_id: UUID) -> Version:
        """Una versión por ID, aunque no esté en la página que muestra el selector."""
        return self._view(owner, self.datasets.get(owner, version_id))

    def _view(self, owner: UUID, version: DatasetVersion) -> Version:
        return legacy_view(
            version,
            self.executions.get(owner, self.datasets.binding(owner, version.id).execution_id),
            lineage.parent_version_id
            if version.kind == "derived" and (lineage := self.datasets.lineage(owner, version.id))
            else None,
        )

    def summary(self, owner: UUID) -> IngestionSummary:
        states = self.executions.counts(owner)
        return IngestionSummary(
            datasets=self.datasets.count(owner),
            versions=sum(states.values()),
            processed=states.get("succeeded", 0),
            pending=states.get("queued", 0) + states.get("running", 0),
            failed=states.get("failed", 0),
        )

    def diagnostic(self, owner: UUID, version_id: UUID) -> Diagnostic:
        version = self.datasets.get(owner, version_id)
        binding = self.datasets.binding(owner, version_id)
        run = self.executions.get(owner, binding.execution_id)
        self._ready(run)
        if binding.diagnostic_artifact_id:
            result = Diagnostic.model_validate_json(
                self.objects.read(
                    self.executions.artifact(owner, binding.diagnostic_artifact_id).content
                )
            )
        else:
            assert binding.profile_artifact_id and binding.quality_artifact_id
            result = Diagnostic(
                profile=DatasetProfile.model_validate_json(
                    self.objects.read(
                        self.executions.artifact(owner, binding.profile_artifact_id).content
                    )
                ),
                quality=QualityReport.model_validate_json(
                    self.objects.read(
                        self.executions.artifact(owner, binding.quality_artifact_id).content
                    )
                ),
            )
        if result.profile.source_sha256 != version.content.sha256:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El diagnóstico no coincide con el original.", 409
            )
        return result

    def automatic_analysis(self, owner: UUID, version_id: UUID) -> AutomaticAnalysis:
        """Plan analítico y hallazgos guardados al importar (Fase 15). Sólo lectura: nunca
        recalcula; las versiones anteriores a analysis-v12 no lo tienen."""
        binding = self.datasets.binding(owner, version_id)
        run = self.executions.get(owner, binding.execution_id)
        self._ready(run)
        artifact = next(
            (a for a in self.executions.artifacts(owner, run.id) if a.kind == "automatic_analysis"),
            None,
        )
        if artifact is None:
            raise ApplicationError(
                "AUTOMATIC_ANALYSIS_NOT_AVAILABLE",
                "Esta versión se procesó antes del análisis automático y no lo tiene.",
                404,
            )
        result = AutomaticAnalysis.model_validate_json(self.objects.read(artifact.content))
        if result.scope.version_id != version_id or result.scope.execution_id != run.id:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El análisis no corresponde a esta versión.", 409
            )
        return result

    def automatic_evidence(
        self, owner: UUID, version_id: UUID, evidence_id: str
    ) -> AutomaticEvidence:
        for item in self.automatic_analysis(owner, version_id).evidence:
            if item.evidence_id == evidence_id:
                return item
        raise ApplicationError("EVIDENCE_NOT_FOUND", "Esa cifra no existe en el análisis.", 404)

    def preview(
        self, owner: UUID, version_id: UUID, limit: int, offset: int, issue_id: str | None = None
    ) -> PreviewPage:
        binding = self.datasets.binding(owner, version_id)
        self._ready(self.executions.get(owner, binding.execution_id))
        rule = column = None
        if issue_id:
            issue = next(
                (
                    item
                    for item in self.diagnostic(owner, version_id).quality.issues
                    if item.id == issue_id
                ),
                None,
            )
            if not issue:
                raise ApplicationError("ISSUE_NOT_FOUND", "Incidencia no encontrada.", 404)
            rule, column = issue.rule, issue.column
        assert binding.table_artifact_id
        return self.preview_reader.read(
            self.objects.read(self.executions.artifact(owner, binding.table_artifact_id).content),
            limit,
            offset,
            rule,
            column,
        )

    def original(self, owner: UUID, version_id: UUID) -> tuple[str, bytes]:
        version = self.datasets.get(owner, version_id)
        if version.kind == "derived":
            raise ApplicationError(
                "DERIVED_HAS_NO_ORIGINAL",
                "Esta versión es derivada; descarga el original de la versión de origen.",
                409,
            )
        return version.file_name, self.objects.read(version.content)

    def export_csv(self, owner: UUID, version_id: UUID, profile: CsvProfile) -> tuple[str, bytes]:
        """Tabla publicada de cualquier versión (también derivada) en un perfil CSV fijo."""
        version = self.datasets.get(owner, version_id)
        tables = [
            t for t in self.executions.representations(owner, version_id) if t.kind == "table"
        ]
        if not tables or not tables[0].columns:
            raise ApplicationError(
                "TABLE_NOT_READY", "La versión todavía no tiene una tabla publicada.", 409
            )
        table = tables[0]
        stem = version.file_name.rsplit(".", 1)[0] or "datos"
        suffix = "" if profile == "standard" else "-excel"
        return (
            f"{stem}-v{version.number}{suffix}.csv",
            table_csv(self.objects.read(table.content), table.columns or [], profile),
        )

    def cancel(self, owner: UUID, execution_id: UUID) -> Version:
        run = self.executions.get(owner, execution_id)
        binding = self.datasets.binding(owner, run.version_id)
        if run.kind != "csv_import" or binding.execution_id != execution_id:
            raise ApplicationError(
                "NOT_BASELINE_IMPORT", "Utiliza cancel-analysis para este análisis.", 409
            )
        return legacy_view(
            self.datasets.get(owner, run.version_id), self.executions.cancel(owner, execution_id)
        )

    def review(self, owner: UUID, version_id: UUID) -> SourceReview:
        """Lectura del archivo y cambios respecto de la versión anterior comparable (Fase 18).
        Sólo lee lo publicado: la decisión de lectura guardada con la tabla y los perfiles."""
        version = self.datasets.get(owner, version_id)
        binding = self.datasets.binding(owner, version_id)
        run = self.executions.get(owner, binding.execution_id)
        self._ready(run)
        reading = (
            self.preview_reader.source_reading(
                self.objects.read(
                    self.executions.artifact(owner, binding.table_artifact_id).content
                )
            )
            if version.kind == "imported" and binding.table_artifact_id
            else None
        )
        structure = None
        current = self._profile(owner, binding.profile_artifact_id)
        previous = self.previous(owner, version, run) if current else None
        if current and previous:
            before, number, profile = previous
            structure = compare(profile, current, str(before), number)
        origin = run.plan.content.get("source_origin") if run.plan else None
        return SourceReview(
            reading=reading,
            structure=structure,
            origin=SourceOrigin.model_validate(origin) if origin else None,
        )

    def previous(
        self, owner: UUID, version: DatasetVersion, run: Execution
    ) -> tuple[UUID, int, DatasetProfile] | None:
        """Versión importada anterior más reciente del mismo archivo (y de la misma hoja o
        tabla si es un libro) que terminó con perfil."""
        if version.kind != "imported":
            return None
        source = source_key(run)
        offset = 0
        while True:
            page, total = self.datasets.versions(owner, version.project_id, 100, offset)
            for candidate in page:
                if (
                    candidate.number >= version.number
                    or candidate.kind != "imported"
                    or candidate.file_name != version.file_name
                ):
                    continue
                binding = self.datasets.binding(owner, candidate.id)
                other = self.executions.get(owner, binding.execution_id)
                if other.state != "succeeded" or source_key(other) != source:
                    continue
                profile = self._profile(owner, binding.profile_artifact_id)
                if profile is not None:
                    return candidate.id, candidate.number, profile
            offset += len(page)
            if not page or offset >= total:
                return None

    def _profile(self, owner: UUID, artifact: UUID | None) -> DatasetProfile | None:
        if artifact is None:
            return None
        return DatasetProfile.model_validate_json(
            self.objects.read(self.executions.artifact(owner, artifact).content)
        )

    @staticmethod
    def _ready(run: Execution) -> None:
        if run.state != "succeeded":
            raise ApplicationError(
                "RESULT_NOT_READY", "El procesamiento todavía no ha terminado correctamente.", 409
            )


def source_key(run: Execution) -> tuple[str, str | None] | None:
    """Hoja y tabla leídas (libros); None en CSV."""
    steps = run.plan.content.get("steps", []) if run.plan else []
    read = next((s for s in steps if s.get("id") == "read"), None)
    if read is None or read.get("operation") != "ingestion.read_xlsx":
        return None
    parameters = read.get("parameters", {})
    return str(parameters.get("sheet")), parameters.get("table")


class AnalysisService:
    """Fachada de casos de uso de análisis tabular fijo; no es planificación libre."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        projects: ProjectAccess,
        uow: UnitOfWork,
        config: ProcessingConfig,
        semantics: SemanticService | None = None,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.projects, self.uow, self.config = projects, uow, config
        self.semantics = semantics

    def submit(
        self,
        owner: UUID,
        version_id: UUID,
        artifact_id: UUID,
        artifact_sha256: str,
        kind: Literal["profile_quality", "quality_only"],
        key: UUID,
        correlation: str,
        semantic_ref: SemanticReference | None = None,
    ) -> Execution:
        try:
            version = self.datasets.get(owner, version_id)
            self.datasets.lock_owner(owner)
            fingerprint = analysis_fingerprint(
                version_id, artifact_id, artifact_sha256, kind, semantic_ref
            )
            existing = self.executions.find_request(
                owner, version.project_id, "table_analysis", key, fingerprint
            )
            if existing:
                self.uow.rollback()
                return existing
            self.projects.require(owner, version.project_id, writable=True)
            table = self.executions.artifact(owner, artifact_id)
            if (
                table.version_id != version_id
                or table.kind != "table"
                or table.content.sha256 != artifact_sha256
            ):
                raise ApplicationError(
                    "INPUT_MISMATCH",
                    "La representación o su hash no corresponde a la versión.",
                    409,
                )
            if semantic_ref:
                if not self.semantics:
                    raise ApplicationError(
                        "SEMANTICS_UNAVAILABLE", "La revisión semántica no está disponible.", 503
                    )
                self.semantics.resolve_for_table(
                    owner,
                    semantic_ref,
                    TableReference(
                        version_id=version.id,
                        version_content_sha256=version.content.sha256,
                        artifact_id=table.id,
                        artifact_sha256=table.content.sha256,
                    ),
                )
            plan = build_plan(
                owner,
                version,
                self.config,
                table=table,
                analysis_kind=kind,
                semantic_ref=semantic_ref,
            )
            run = self.executions.enqueue(
                owner,
                version.project_id,
                version_id,
                "table_analysis",
                key,
                fingerprint,
                plan,
                correlation,
                table.id,
                table.content.sha256,
            )
            self.uow.commit()
            return run
        except Exception:
            self.uow.rollback()
            raise

    def quality(self, owner: UUID, execution_id: UUID) -> QualityReport:
        for artifact in self.executions.artifacts(owner, execution_id):
            if artifact.kind == "quality":
                return QualityReport.model_validate_json(self.objects.read(artifact.content))
            if artifact.kind == "legacy_diagnostic":
                return Diagnostic.model_validate_json(self.objects.read(artifact.content)).quality
        raise ApplicationError(
            "RESULT_NOT_READY", "El resultado de calidad no está disponible.", 409
        )

    def profile(self, owner: UUID, execution_id: UUID) -> DatasetProfile:
        for artifact in self.executions.artifacts(owner, execution_id):
            if artifact.kind == "profile":
                return DatasetProfile.model_validate_json(self.objects.read(artifact.content))
            if artifact.kind == "legacy_diagnostic":
                return Diagnostic.model_validate_json(self.objects.read(artifact.content)).profile
        raise ApplicationError(
            "PROFILE_NOT_AVAILABLE", "Este análisis no ha publicado un perfil.", 404
        )
