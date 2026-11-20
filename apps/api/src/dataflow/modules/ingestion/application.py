import base64
import binascii
import hashlib
import json
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
    DatabaseCopy,
    DataModel,
    Diagnostic,
    IngestionSummary,
    OmittedSource,
    PdfChoice,
    PdfSelection,
    PostgresConnection,
    PreviewPage,
    ReadPdfParameters,
    ReadXlsxParameters,
    RecordsPage,
    RelatedFilesRequest,
    RelatedSet,
    RelatedView,
    SnapshotTable,
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
from dataflow.platform import destinations
from dataflow.platform.canonical import digest
from dataflow.platform.csv_export import CsvProfile, table_csv
from dataflow.platform.destinations import DestinationPolicy
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
    def snapshot_postgresql(
        self,
        connection: PostgresConnection,
        config: ProcessingConfig,
        policy: DestinationPolicy | None = None,
        timeout: int | None = None,
    ) -> SqlSnapshot: ...
    def relate(
        self, payload: bytes, config: ProcessingConfig, timeout: int | None = None
    ) -> RelatedSet: ...
    def snapshot_sqlserver(
        self, connection: SqlServerConnection, config: ProcessingConfig, timeout: int | None = None
    ) -> SqlSnapshot: ...

    def inspect_xlsx(
        self,
        content: bytes,
        sheet: str | None,
        table: str | None,
        header_row: int,
        config: ProcessingConfig,
    ) -> XlsxInspection: ...


@dataclass(frozen=True)
class AttemptLimits:
    """Fase 32 (ADR-050): intentos de conexión a bases de datos. Por usuario en 15 min, fallidos
    por usuario y día, y hacia un mismo destino en 15 min (todas las cuentas: protege a terceros
    de que DataFlow sirva para probar contraseñas contra su servidor)."""

    per_user: int = 10
    failures_per_day: int = 30
    per_target: int = 20


class ConnectionAttempts(Protocol):
    def admit(self, user: UUID, client: str, target: str, limits: AttemptLimits) -> UUID | None:
        """Registra el intento y devuelve su id, o None si supera algún límite."""
        ...

    def succeeded(self, attempt: UUID) -> None: ...


DatabaseEngine = Literal["postgresql", "sqlserver"]
CopyKind = Literal["photo", "import"]


class DatabaseCopies(Protocol):
    """Fase 33 (ADR-051): estado de las copias de bases en segundo plano (sin credenciales)."""

    def create(
        self,
        owner: UUID,
        project: UUID,
        engine: DatabaseEngine,
        kind: CopyKind,
        server: str,
        database: str,
        schema: str | None,
    ) -> DatabaseCopy: ...
    def get(self, owner: UUID, copy: UUID) -> DatabaseCopy | None: ...
    def running(self, copy: UUID) -> None: ...
    def succeeded(
        self,
        copy: UUID,
        version: UUID | None,
        model: DataModel | None,
        tables: int,
        omitted: int,
    ) -> None: ...
    def failed(self, copy: UUID, code: str, message: str) -> None: ...


@dataclass(frozen=True)
class CopyTicket:
    """Fase 33: lo que la comprobación previa decidió en la petición y la copia necesita después,
    en segundo plano (el intento y si el servidor es de la lista)."""

    copy: UUID
    attempt: UUID | None
    listed: bool
    access: "ConnectionAccess"


class SnapshotConnector(Protocol):
    """Fase 32B (ADR-050): copia de una base fuera del proceso de la API, en el servicio
    `connector` (red de salida aislada, sin credenciales de DataFlow). Sólo para destinos que no
    están en la lista: los de la lista son de confianza y se copian como antes."""

    def snapshot_postgresql(
        self,
        connection: PostgresConnection,
        config: ProcessingConfig,
        policy: DestinationPolicy,
        timeout: int | None = None,
    ) -> SqlSnapshot: ...


@dataclass(frozen=True)
class ConnectionAccess:
    """Fase 32: a qué servidores se puede conectar (`database-destination-v1`) y desde qué IP
    llega la petición (para el límite de intentos)."""

    policy: DestinationPolicy
    client: str = ""


DESTINATION_REFUSALS = {
    "HOST_UNKNOWN": (
        "DATABASE_HOST_UNKNOWN",
        "No se encontró ese servidor. Revisa el nombre.",
        422,
    ),
    "HOST_PRIVATE": (
        "DATABASE_HOST_PRIVATE",
        "Esa dirección pertenece a una red privada. DataFlow sólo se conecta a servidores "
        "accesibles desde internet.",
        422,
    ),
}

XLSX_REJECTED = (".xls", ".xlsm", ".xlsb", ".xltm", ".xlt")
UNSAFE_NAME = "/\\\x00\r\n"
# Fase 31: los archivos de un conjunto relacionado pueden sumar el doble del límite de uno.
RELATED_TOTAL = 2


class PreviewReader(Protocol):
    def read(
        self,
        content: bytes,
        limit: int,
        offset: int,
        rule: str | None = None,
        column: str | None = None,
        sort: str | None = None,
        descending: bool = False,
        search: str | None = None,
        column_ids: list[str] | None = None,
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
    extension: str | None = None  # Fase 31: la de su propio original (si no, la de la carga)


def view_file_name(view: str) -> str:
    """Fase 31: nombre de archivo de una vista del modelo («estudiantes (vista general).csv»)."""
    safe = "".join("_" if c in UNSAFE_NAME or ord(c) < 32 else c for c in view)
    return f"{safe[:250]}.csv"


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
        attempts: ConnectionAttempts | None = None,
        attempt_limits: AttemptLimits | None = None,
        connector: SnapshotConnector | None = None,
        copies: DatabaseCopies | None = None,
        copy_timeout: int = 1800,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.projects, self.preview_reader, self.uow = projects, preview, uow
        self.config, self.quota, self.maximum_upload = config, quota, maximum_upload
        self.inspector = inspector
        self.attempts, self.attempt_limits = attempts, attempt_limits or AttemptLimits()
        self.connector = connector
        # Fase 33: copias en segundo plano y su plazo (el de la copia, la lectura y las relaciones).
        self.copies, self.copy_timeout = copies, copy_timeout

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

    def start_database_copy(
        self,
        owner: UUID,
        project: UUID,
        engine: DatabaseEngine,
        kind: CopyKind,
        connection: PostgresConnection | SqlServerConnection,
        access: ConnectionAccess,
    ) -> tuple[DatabaseCopy, CopyTicket]:
        """Fase 33 (ADR-051): en la petición, la comprobación previa del destino y el intento
        (Fase 32) y el registro de la copia, que se hace después en segundo plano. Responde al
        momento; la contraseña no se guarda (sólo vive en memoria hasta que termine la copia)."""
        if self.copies is None:
            raise ApplicationError(
                "DATABASE_COPY_UNAVAILABLE", "Las copias de bases no están activas.", 503
            )
        if engine == "sqlserver":
            # SQL Server sigue sólo con la lista (Fase 32): sin verificar certificados ni impedir
            # redirecciones no se abre al modo público.
            access = ConnectionAccess(
                DestinationPolicy(access.policy.allowed_hosts, False, access.policy.denied),
                access.client,
            )
            prefix, label = "SQLSERVER", "SQL Server"
        else:
            prefix, label = "POSTGRESQL", "PostgreSQL"
        attempt, listed = self._gate(
            owner, project, connection.server, connection.port, access, prefix, label
        )
        try:
            copy = self.copies.create(
                owner,
                project,
                engine,
                kind,
                f"{connection.server}:{connection.port}",
                connection.database,
                connection.schema_name,
            )
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return copy, CopyTicket(copy.id, attempt, listed, access)

    def database_copy(self, owner: UUID, copy: UUID) -> DatabaseCopy:
        if self.copies is None:
            raise ApplicationError("NOT_FOUND", "Copia no encontrada.", 404)
        try:
            found = self.copies.get(owner, copy)
            self.uow.commit()  # `get` puede marcar como interrumpida una copia sin latido
        except Exception:
            self.uow.rollback()
            raise
        if found is None:
            raise ApplicationError("NOT_FOUND", "Copia no encontrada.", 404)
        return found

    def run_database_copy(
        self,
        owner: UUID,
        project: UUID,
        engine: DatabaseEngine,
        kind: CopyKind,
        connection: PostgresConnection | SqlServerConnection,
        ticket: CopyTicket,
        key: UUID,
        correlation: str,
    ) -> None:
        """Fase 33: la copia en segundo plano. Nunca lanza: el resultado (la versión principal,
        el modelo o el error) queda en el registro de la copia."""
        assert self.copies is not None
        try:
            self.copies.running(ticket.copy)
            self.uow.commit()
            snapshot = self._database_snapshot(engine, connection, ticket)
            self._succeeded(ticket.attempt)
            if kind == "photo":
                model = self._snapshot_model(snapshot, self.copy_timeout)
                self.copies.succeeded(
                    ticket.copy, None, model, len(snapshot.tables), len(model.omitted)
                )
            else:
                schema = connection.schema_name
                version, copied, omitted = self._submit_snapshot(
                    owner,
                    project,
                    snapshot,
                    engine,
                    f"{connection.server}:{connection.port}",
                    connection.database + (f"/{schema}" if schema else ""),
                    key,
                    correlation,
                )
                self.copies.succeeded(ticket.copy, version.id, None, copied, omitted)
            self.uow.commit()
        except Exception as exc:
            self.uow.rollback()
            code, message = (
                (exc.code, exc.message)
                if isinstance(exc, ApplicationError)
                else ("DATABASE_COPY_FAILED", "No se pudo completar la copia de la base.")
            )
            self.copies.failed(ticket.copy, code, message)
            self.uow.commit()

    def _database_snapshot(
        self,
        engine: DatabaseEngine,
        connection: PostgresConnection | SqlServerConnection,
        ticket: CopyTicket,
    ) -> SqlSnapshot:
        """La copia en sí, con el plazo largo de las copias en segundo plano. Fase 32B: un
        destino fuera de la lista se copia en el servicio `connector` si existe."""
        if isinstance(connection, SqlServerConnection):
            if self.inspector is None:
                raise ApplicationError("SQLSERVER_UNAVAILABLE", "SQL Server no está activo.", 503)
            return self.inspector.snapshot_sqlserver(
                connection, self.config, timeout=self.copy_timeout
            )
        if not ticket.listed and self.connector is not None:
            return self.connector.snapshot_postgresql(
                connection, self.config, ticket.access.policy, timeout=self.copy_timeout
            )
        if self.inspector is None:
            raise ApplicationError("POSTGRESQL_UNAVAILABLE", "PostgreSQL no está activo.", 503)
        return self.inspector.snapshot_postgresql(
            connection, self.config, ticket.access.policy, timeout=self.copy_timeout
        )

    def _gate(
        self,
        owner: UUID,
        project: UUID,
        server: str,
        port: int,
        access: ConnectionAccess,
        prefix: str,
        engine: str,
    ) -> tuple[UUID | None, bool]:
        """Fase 32 (`database-destination-v1`, ADR-050): comprobación previa en la API, para
        responder sin lanzar el subproceso (que la repite justo antes de conectar), y límite
        de intentos. Un servidor de la lista no se resuelve aquí. Devuelve el intento y si el
        servidor es de la lista."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        policy = access.policy
        if not policy.enabled:
            raise ApplicationError(
                f"{prefix}_DISABLED",
                f"La conexión a {engine} no está activada en este entorno.",
                503,
            )
        target = server.strip().lower()
        if not policy.listed(server):
            if not policy.public:
                raise ApplicationError(
                    f"{prefix}_HOST_NOT_ALLOWED",
                    "Ese servidor no está en la lista de servidores permitidos.",
                    422,
                )
            decision = destinations.decide(server, destinations.resolve(server, port), policy)
            if isinstance(decision, destinations.Denied):
                code, message, status = DESTINATION_REFUSALS[decision.reason]
                raise ApplicationError(code, message, status)
            target = decision.address
        return self._admit(owner, access.client, target), policy.listed(server)

    def _admit(self, owner: UUID, client: str, target: str) -> UUID | None:
        if self.attempts is None:
            return None
        try:
            attempt = self.attempts.admit(owner, client, target, self.attempt_limits)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        if attempt is None:
            raise ApplicationError(
                "DATABASE_RATE_LIMITED",
                "Demasiados intentos de conexión. Espera unos minutos.",
                429,
            )
        return attempt

    def _succeeded(self, attempt: UUID | None) -> None:
        if attempt is None or self.attempts is None:
            return
        try:
            self.attempts.succeeded(attempt)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise

    def _relate(
        self,
        tables: list[tuple[str, str, bytes]],
        declared: list[dict[str, str]],
        data: bool,
        timeout: int | None = None,
    ) -> RelatedSet:
        """`relations-v1` en el subproceso de ingesta. `data`: con las vistas en CSV (para
        registrarlas) o sólo el modelo (la «foto» del esquema)."""
        assert self.inspector is not None
        payload = {
            "tables": [
                {
                    "label": label,
                    "format": kind,
                    "content_base64": base64.b64encode(content).decode(),
                }
                for label, kind, content in tables
            ],
            "declared": declared,
            "with_data": data,
        }
        return self.inspector.relate(json.dumps(payload).encode(), self.config, timeout)

    def _snapshot_relations(
        self, snapshot: SqlSnapshot, data: bool, timeout: int | None = None
    ) -> RelatedSet:
        return self._relate(
            [(t.label, "standard", t.csv.encode("utf-8")) for t in snapshot.tables],
            [
                {
                    "table": t.label,
                    "column": fk.column,
                    "references_table": fk.references.rsplit(".", 1)[0],
                    "references_column": fk.references.rsplit(".", 1)[-1],
                }
                for t in snapshot.tables
                for fk in t.foreign_keys
            ],
            data,
            timeout,
        )

    def _snapshot_model(self, snapshot: SqlSnapshot, timeout: int | None = None) -> DataModel:
        related = self._snapshot_relations(snapshot, data=False, timeout=timeout)
        return DataModel(
            main=related.main,
            tables=related.tables,
            relations=related.relations,
            views=related.views,
            omitted=snapshot.omitted,
        )

    def _fit_tables(self, owner: UUID, snapshot: SqlSnapshot) -> tuple[SqlSnapshot, int]:
        """Fase 33: las tablas (ya de menor a mayor) que caben como originales y en la cuota de
        la cuenta; las demás se omiten con su motivo. Devuelve también el espacio que queda."""
        try:
            room = self.quota - self.datasets.used_bytes(owner)
        finally:
            self.uow.rollback()
        megabytes = self.maximum_upload // (1024 * 1024)
        kept: list[SnapshotTable] = []
        omitted = list(snapshot.omitted)
        for table in snapshot.tables:
            size = len(table.csv.encode("utf-8"))
            if size > self.maximum_upload:
                reason = f"Supera el tamaño máximo de un original ({megabytes} MB)."
                omitted.append(OmittedSource(table=table.label, reason=reason))
            elif size > room:
                reason = "No cabe en la cuota de archivos originales de la cuenta."
                omitted.append(OmittedSource(table=table.label, reason=reason))
            else:
                kept.append(table)
                room -= size
        if not kept:
            raise ApplicationError(
                "STORAGE_QUOTA",
                "Ninguna tabla de la base cabe en la cuota de archivos originales de la cuenta.",
                413,
            )
        return snapshot.model_copy(update={"tables": kept, "omitted": omitted}), room

    def _fit_views(
        self, related: RelatedSet, room: int, omitted: list[OmittedSource]
    ) -> RelatedSet:
        """Fase 33: las vistas que no caben (tamaño de un original o cuota) se omiten con su
        motivo en vez de impedir la carga; si cae la principal, se abre la tabla mayor."""
        kept: list[RelatedView] = []
        for view in related.views:
            size = len(related.csv.get(view.name, "").encode("utf-8"))
            if size > self.maximum_upload or size > room:
                reason = (
                    "La vista supera el tamaño máximo de un original."
                    if size > self.maximum_upload
                    else "La vista no cabe en la cuota de archivos originales de la cuenta."
                )
                omitted.append(OmittedSource(table=view.name, reason=reason))
            else:
                kept.append(view)
                room -= size
        names = {v.name for v in kept}
        return related.model_copy(
            update={
                "views": kept,
                "csv": {k: v for k, v in related.csv.items() if k in names},
                "main": related.main if related.main in names else None,
            }
        )

    def _submit_snapshot(
        self,
        owner: UUID,
        project: UUID,
        snapshot: SqlSnapshot,
        kind: Literal["sqlserver", "postgresql"],
        server: str,
        database: str,
        key: UUID,
        correlation: str,
    ) -> tuple[Version, int, int]:
        """Cada tabla (y cada vista del modelo) como versión. Fase 33: lo que no cabe se omite
        con su motivo. Devuelve la versión principal, las tablas copiadas y las omitidas."""
        captured = datetime.now(UTC).replace(microsecond=0).isoformat()
        snapshot, room = self._fit_tables(owner, snapshot)
        labels = [t.label for t in snapshot.tables]
        omitted = list(snapshot.omitted)
        related = (
            self._fit_views(
                self._snapshot_relations(snapshot, data=True, timeout=self.copy_timeout),
                room,
                omitted,
            )
            if len(snapshot.tables) > 1
            else None
        )
        rule: Literal["sqlserver-selection-v3", "postgresql-selection-v2"] = (
            "sqlserver-selection-v3" if kind == "sqlserver" else "postgresql-selection-v2"
        )
        members: list[Sibling] = []
        for table in snapshot.tables:
            data = table.csv.encode("utf-8")
            decision = SourceOrigin(
                kind=kind,
                rule=rule,
                table=table.label,
                server=server,
                database=database,
                captured_at=captured,
                excluded_columns=table.excluded_columns,
                foreign_keys=table.foreign_keys,
                analyzed_together=[label for label in labels if label != table.label],
                omitted=omitted,
                tables=related.tables if related else [],
                relations=related.relations if related else [],
                views=related.views if related else [],
                access=snapshot.access,
                tls=snapshot.tls,
            )
            file_name = table_file_name(table.label)
            fingerprint = digest(
                "import_request",
                {
                    "name": file_name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    kind: f"{server}/{database}",
                },
            )
            members.append(
                Sibling(
                    uuid5(key, f"{kind}-table:{table.label}"),
                    fingerprint,
                    self._csv_plan(owner, decision),
                    data,
                    file_name,
                )
            )
        # Sin vista principal, se abre la tabla con más registros (como en la Fase 31).
        members.sort(key=lambda m: -len(m.content or b""))
        origin = {
            "server": server,
            "database": database,
            "captured_at": captured,
            "omitted": omitted,
            "access": snapshot.access,
            "tls": snapshot.tls,
        }
        version = self._register_set(owner, project, related, members, origin, key, correlation)
        return version, len(snapshot.tables), len(omitted)

    def _related_files(self, request: RelatedFilesRequest) -> list[tuple[str, str, bytes]]:
        """Archivos de un conjunto relacionado ya comprobados (nombre, formato y tamaño)."""
        files: list[tuple[str, str, bytes]] = []
        seen: set[str] = set()
        for item in request.files:
            name, lowered = item.name, item.name.lower()
            kind = next((k for k in ("csv", "xlsx") if lowered.endswith(f".{k}")), "")
            if not kind or any(c in name for c in UNSAFE_NAME):
                raise ApplicationError(
                    "RELATED_FORMAT", f"«{name}»: sólo se admiten archivos CSV o .xlsx.", 422
                )
            if lowered in seen:
                raise ApplicationError(
                    "RELATED_DUPLICATE_NAMES", "Hay dos archivos con el mismo nombre.", 422
                )
            seen.add(lowered)
            try:
                content = base64.b64decode(item.content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ApplicationError(
                    "RELATED_FILE_INVALID", f"«{name}» no llegó completo; vuelve a elegirlo.", 422
                ) from exc
            self._check_content(content, f"«{name}» supera el límite de tamaño.")
            files.append((name, kind, content))
        total = sum(len(content) for _, _, content in files)
        if total > self.maximum_upload * RELATED_TOTAL:
            raise ApplicationError(
                "RELATED_TOO_LARGE",
                "Los archivos juntos superan "
                f"{RELATED_TOTAL * self.maximum_upload // (1024 * 1024)} MB.",
                413,
            )
        if self.inspector is None:
            raise ApplicationError(
                "RELATED_UNAVAILABLE", "La lectura de archivos no está activa.", 503
            )
        return files

    def inspect_related(
        self, owner: UUID, project: UUID, request: RelatedFilesRequest
    ) -> DataModel:
        """Fase 31: «foto» del modelo de datos de los archivos sin guardar nada."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        related = self._relate(self._related_files(request), [], data=False)
        return DataModel(
            main=related.main,
            tables=related.tables,
            relations=related.relations,
            views=related.views,
        )

    def submit_related(
        self,
        owner: UUID,
        project: UUID,
        request: RelatedFilesRequest,
        key: UUID,
        correlation: str,
    ) -> Version:
        """Fase 31: de 2 a 5 archivos (CSV o .xlsx) en una sola carga. Cada archivo se analiza
        como versión propia con su original; con el modelo de datos de `relations-v1`, cada vista
        (la de cada tabla de hechos y la vista general por entidad) es otra versión y se devuelve
        la principal, con la decisión en `source_origin`."""
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
        files = self._related_files(request)
        related = self._relate(files, [], data=True)
        names = [name for name, _, _ in files]
        rows = {t.label: t.rows for t in related.tables}
        members: list[Sibling] = []
        for name, kind, content in sorted(files, key=lambda f: (-rows.get(f[0], 0), f[0])):
            origin = SourceOrigin(
                kind="related",
                rule="relations-v1",
                table=name,
                analyzed_together=[other for other in names if other != name],
                tables=related.tables,
                relations=related.relations,
                views=related.views,
            )
            sha256 = hashlib.sha256(content).hexdigest()
            if kind == "csv":
                encoding = resolve_encoding(content)
                separator = resolve_separator(content, "auto", encoding)
                plan = self._related_csv_plan(owner, separator, encoding, origin)
                fingerprint = import_fingerprint(name, sha256, "auto")
            else:
                selection = related.xlsx[name]
                parameters = ReadXlsxParameters(
                    sheet=selection.sheet, table=selection.table, header_row=selection.header_row
                )
                plan = self._related_xlsx_plan(owner, parameters, selection, origin)
                fingerprint = xlsx_import_fingerprint(name, sha256, parameters)
            members.append(
                Sibling(uuid5(key, f"related-table:{name}"), fingerprint, plan, content, name, kind)
            )
        return self._register_set(owner, project, related, members, {}, key, correlation)

    def _register_set(
        self,
        owner: UUID,
        project: UUID,
        related: RelatedSet | None,
        members: list[Sibling],
        origin: dict[str, Any],
        key: UUID,
        correlation: str,
    ) -> Version:
        """Las tablas y cada vista del modelo como versiones propias. La vista principal es la
        versión que se devuelve (la que se abre); sin vistas, la tabla con más registros."""
        views: list[Sibling] = []
        main_view: Sibling | None = None
        for view in related.views if related else []:
            assert related is not None
            data = related.csv[view.name].encode("utf-8")
            if len(data) > self.maximum_upload:
                raise ApplicationError(
                    "RELATED_JOINED_TOO_LARGE",
                    f"La vista «{view.name}» supera el tamaño máximo de un original; sube menos "
                    "columnas o menos registros.",
                    413,
                )
            name = view_file_name(view.name)
            decision = SourceOrigin(
                kind="related",
                rule="relations-v1",
                table=view.name,
                joined=True,
                view_kind=view.kind,
                analyzed_together=[m.name for m in members if m.name],
                tables=related.tables,
                relations=related.relations,
                views=related.views,
                **origin,
            )
            fingerprint = digest(
                "import_request",
                {
                    "name": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "related": sorted(m.fingerprint for m in members),
                },
            )
            item = Sibling(
                uuid5(key, f"related-view:{view.name}"),
                fingerprint,
                self._csv_plan(owner, decision),
                data,
                name,
                "csv",
            )
            if view.name == related.main:
                main_view = item
            else:
                views.append(item)
        main = main_view or members[0]
        rest = [m for m in [*members, *views] if m is not main]
        assert main.content is not None and main.name is not None
        return self._register(
            owner,
            project,
            main.name,
            main.content,
            key,
            correlation,
            main.extension or "csv",
            main.fingerprint,
            main.plan,
            rest,
        )

    def _related_csv_plan(
        self,
        owner: UUID,
        separator: str,
        encoding: Literal["utf-8-sig", "cp1252"],
        decision: SourceOrigin,
    ) -> Callable[[DatasetVersion], PlanRevision]:
        def plan(version: DatasetVersion) -> PlanRevision:
            return build_plan(
                owner,
                version,
                self.config,
                "auto",
                separator,
                encoding=encoding,
                source_origin=decision,
            )

        return plan

    def _related_xlsx_plan(
        self,
        owner: UUID,
        parameters: ReadXlsxParameters,
        selection: XlsxSelection,
        decision: SourceOrigin,
    ) -> Callable[[DatasetVersion], PlanRevision]:
        def plan(version: DatasetVersion) -> PlanRevision:
            return build_plan(
                owner,
                version,
                self.config,
                xlsx=parameters,
                source_selection=selection,
                source_origin=decision,
            )

        return plan

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
                        f"{hashlib.sha256(item.content).hexdigest()}"
                        f".{item.extension or extension}",
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
                # Fase 33: las versiones de una misma carga (todas las tablas de una base) entran
                # juntas; la cola ya admitió la carga arriba.
                sibling_run = self.executions.enqueue(
                    owner,
                    project,
                    sibling_id,
                    "csv_import",
                    item.key,
                    item.fingerprint,
                    item.plan(sibling),
                    correlation,
                    admitted=True,
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
        self,
        owner: UUID,
        version_id: UUID,
        limit: int,
        offset: int,
        issue_id: str | None = None,
        sort: UUID | None = None,
        descending: bool = False,
        search: str | None = None,
    ) -> RecordsPage:
        """Página de la tabla publicada. Fase 22: orden por el identificador de una columna
        (nunca por un nombre que llegue en la petición) y búsqueda literal."""
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
        table = self.executions.artifact(owner, binding.table_artifact_id)
        described = table.columns or []
        ids = [str(item["id"]) for item in described]
        sort_name = None
        if sort is not None:
            sort_name = next(
                (str(item["name"]) for item in described if str(item["id"]) == str(sort)), None
            )
            if sort_name is None:
                raise ApplicationError("UNKNOWN_COLUMN", "La columna no existe en la tabla.", 422)
        page = self.preview_reader.read(
            self.objects.read(table.content),
            limit,
            offset,
            rule,
            column,
            sort_name,
            descending,
            search or None,
            ids,
        )
        return RecordsPage(
            **{**page.__dict__, "column_ids": ids, "sort": str(sort) if sort else None}
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
