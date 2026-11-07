"""Conexiones de SQL Server y extracciones materializadas (Fase 12B).

- La contraseña se cifra con la clave del servidor y nunca se devuelve ni se registra.
- Sólo se extraen los objetos de la lista blanca de la conexión, validados en el servidor.
- Cada extracción se materializa (Parquet de texto) como el original inmutable de una versión
  y recorre el mismo pipeline que un CSV: `ingestion.read_sqlserver@1` → perfil → calidad.
- SQL Server sólo se consulta durante la vista previa y la extracción.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.application import IngestionService, ProjectAccess
from dataflow.modules.ingestion.contracts import (
    ConnectionCreate,
    ConnectionDraft,
    ConnectionResponse,
    Consistency,
    Discovery,
    ExtractionPreview,
    ExtractionProvenance,
    ReadSqlServerParameters,
    SqlColumn,
    SqlObject,
)
from dataflow.modules.ingestion.domain import Version
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork

PREVIEW_ROWS = 20


@dataclass(frozen=True)
class StoredConnection:
    id: UUID
    owner_id: UUID
    project_id: UUID
    name: str
    host: str
    port: int
    database: str
    username: str
    password_ciphertext: str
    encrypt: bool
    trust_server_certificate: bool
    allowed_objects: list[SqlObject]
    can_write: bool
    created_at: datetime

    def view(self) -> ConnectionResponse:
        return ConnectionResponse(
            id=self.id,
            project_id=self.project_id,
            name=self.name,
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            encrypt=self.encrypt,
            trust_server_certificate=self.trust_server_certificate,
            allowed_objects=self.allowed_objects,
            can_write=self.can_write,
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class Materialized:
    parquet: bytes
    columns: list[SqlColumn]
    rows: list[list[str | None]]
    row_count: int
    byte_count: int
    consistency: Consistency
    server_version: str


class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...


class SqlGateway(Protocol):
    """Subproceso aislado con el controlador ODBC; recibe credenciales sólo por archivo."""

    def discover(self, credentials: dict[str, Any], timeout: int) -> Discovery: ...
    def extract(
        self,
        credentials: dict[str, Any],
        target: SqlObject,
        config: ProcessingConfig,
        max_bytes: int,
        truncate: bool,
    ) -> Materialized: ...


class ConnectionRepository(Protocol):
    def add(self, connection: StoredConnection) -> None: ...
    def list(self, owner: UUID, project: UUID) -> list[StoredConnection]: ...
    def get(self, owner: UUID, connection_id: UUID) -> StoredConnection: ...
    def revoke(self, owner: UUID, connection_id: UUID) -> None: ...
    def record_extraction(self, provenance: ExtractionProvenance) -> None: ...
    def extraction(self, owner: UUID, version_id: UUID) -> ExtractionProvenance | None: ...
    def audit(self, actor: UUID, entity: UUID, action: str, correlation: str) -> None: ...


def extraction_fingerprint(connection: UUID, target: SqlObject) -> str:
    return digest(
        "import_request",
        {"sqlserver": {"connection_id": str(connection), **target.model_dump()}},
    )


class ConnectionService:
    def __init__(
        self,
        repository: ConnectionRepository,
        gateway: SqlGateway,
        cipher: Cipher | None,
        projects: ProjectAccess,
        ingestion: IngestionService,
        uow: UnitOfWork,
        config: ProcessingConfig,
        max_bytes: int,
        driver: str,
    ) -> None:
        self.repository, self.gateway, self.cipher = repository, gateway, cipher
        self.projects, self.ingestion, self.uow = projects, ingestion, uow
        self.config, self.max_bytes, self.driver = config, max_bytes, driver

    # --- credenciales -------------------------------------------------------------------
    def _credentials(self, draft: ConnectionDraft | StoredConnection) -> dict[str, Any]:
        if isinstance(draft, ConnectionDraft):
            password = draft.password.get_secret_value()
        else:
            password = self._cipher().decrypt(draft.password_ciphertext)
        return {
            "host": draft.host,
            "port": draft.port,
            "database": draft.database,
            "username": draft.username,
            "password": password,
            "encrypt": draft.encrypt,
            "trust_server_certificate": draft.trust_server_certificate,
            "driver": self.driver,
        }

    def _cipher(self) -> Cipher:
        if self.cipher is None:
            raise ApplicationError(
                "SOURCES_KEY_MISSING",
                "Falta la clave de cifrado de conexiones (DATAFLOW_SOURCES_KEY_FILE).",
                503,
            )
        return self.cipher

    # --- casos de uso -------------------------------------------------------------------
    def discover(self, owner: UUID, project: UUID, draft: ConnectionDraft) -> Discovery:
        """Prueba la conexión y lista sus objetos; no guarda nada."""
        self._writable(owner, project)
        return self.gateway.discover(self._credentials(draft), self.config.timeout_seconds)

    def create(
        self, owner: UUID, project: UUID, body: ConnectionCreate, correlation: str
    ) -> ConnectionResponse:
        self._writable(owner, project)
        cipher = self._cipher()
        discovery = self.gateway.discover(self._credentials(body), self.config.timeout_seconds)
        visible = {(o.schema_name, o.name) for o in discovery.objects}
        allowed = list(dict.fromkeys(body.allowed_objects))
        missing = [o for o in allowed if (o.schema_name, o.name) not in visible]
        if missing:
            raise ApplicationError(
                "SQL_OBJECT_NOT_FOUND",
                f"El objeto {missing[0].schema_name}.{missing[0].name} no existe o no es visible.",
                422,
            )
        connection = StoredConnection(
            id=uuid4(),
            owner_id=owner,
            project_id=project,
            name=body.name,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password_ciphertext=cipher.encrypt(body.password.get_secret_value()),
            encrypt=body.encrypt,
            trust_server_certificate=body.trust_server_certificate,
            allowed_objects=allowed,
            can_write=discovery.can_write,
            created_at=datetime.now(UTC),
        )
        try:
            self.projects.require(owner, project, writable=True)
            self.repository.add(connection)
            self.repository.audit(owner, connection.id, "ingestion.connection_created", correlation)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return connection.view()

    def list(self, owner: UUID, project: UUID) -> list[ConnectionResponse]:
        self.projects.require(owner, project)
        return [connection.view() for connection in self.repository.list(owner, project)]

    def revoke(self, owner: UUID, connection_id: UUID, correlation: str) -> None:
        try:
            connection = self.repository.get(owner, connection_id)
            self.projects.require(owner, connection.project_id, writable=True)
            self.repository.revoke(owner, connection_id)
            self.repository.audit(owner, connection_id, "ingestion.connection_revoked", correlation)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise

    def preview(self, owner: UUID, connection_id: UUID, target: SqlObject) -> ExtractionPreview:
        connection = self._allowed(owner, connection_id, target)
        result = self.gateway.extract(
            self._credentials(connection),
            target,
            self.config.model_copy(update={"max_rows": PREVIEW_ROWS}),
            self.max_bytes,
            True,
        )
        return ExtractionPreview(
            columns=result.columns, rows=result.rows, consistency=result.consistency
        )

    def extract(
        self, owner: UUID, connection_id: UUID, target: SqlObject, key: UUID, correlation: str
    ) -> Version:
        connection = self._allowed(owner, connection_id, target)
        fingerprint = extraction_fingerprint(connection.id, target)
        existing = self.ingestion.find_import(owner, connection.project_id, key, fingerprint)
        if existing:
            return existing
        self.projects.require(owner, connection.project_id, writable=True)
        self.uow.rollback()  # sin bloqueos abiertos mientras se consulta SQL Server
        result = self.gateway.extract(
            self._credentials(connection), target, self.config, self.max_bytes, False
        )
        extracted_at = datetime.now(UTC)
        parameters = ReadSqlServerParameters(
            connection_id=connection.id,
            schema_name=target.schema_name,
            name=target.name,
            columns=[c.name for c in result.columns],
        )

        def provenance(version_id: UUID) -> None:
            self.repository.record_extraction(
                ExtractionProvenance(
                    version_id=version_id,
                    connection_id=connection.id,
                    connection_name=connection.name,
                    host=connection.host,
                    database=connection.database,
                    schema_name=target.schema_name,
                    name=target.name,
                    columns=result.columns,
                    row_count=result.row_count,
                    byte_count=result.byte_count,
                    consistency=result.consistency,
                    server_version=result.server_version,
                    extracted_at=extracted_at,
                )
            )
            self.repository.audit(owner, version_id, "ingestion.sqlserver_extracted", correlation)

        return self.ingestion.submit_extraction(
            owner,
            connection.project_id,
            f"{target.schema_name}.{target.name}.parquet",
            result.parquet,
            parameters,
            key,
            correlation,
            fingerprint,
            provenance,
        )

    def provenance(self, owner: UUID, version_id: UUID) -> ExtractionProvenance:
        found = self.repository.extraction(owner, version_id)
        if found is None:
            raise ApplicationError(
                "EXTRACTION_NOT_FOUND", "Esta versión no procede de SQL Server.", 404
            )
        return found

    def _allowed(self, owner: UUID, connection_id: UUID, target: SqlObject) -> StoredConnection:
        connection = self.repository.get(owner, connection_id)
        self.projects.require(owner, connection.project_id)
        target = SqlObject(schema_name=target.schema_name, name=target.name)
        if target not in connection.allowed_objects:
            raise ApplicationError(
                "SQL_OBJECT_NOT_ALLOWED",
                f"{target.schema_name}.{target.name} no está autorizado en esta conexión.",
                403,
            )
        return connection

    def _writable(self, owner: UUID, project: UUID) -> None:
        try:
            self.projects.require(owner, project, writable=True)
        finally:
            self.uow.rollback()
