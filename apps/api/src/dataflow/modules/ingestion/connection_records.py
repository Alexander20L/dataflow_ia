"""Persistencia de conexiones de SQL Server y de la procedencia de cada extracción (Fase 12B).

La contraseña sólo existe cifrada (`password_ciphertext`); ninguna vista la incluye.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.ingestion.connections import StoredConnection
from dataflow.modules.ingestion.contracts import ExtractionProvenance, SqlColumn, SqlObject
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class ConnectionRecord(Base):
    __tablename__ = "ingestion_connections"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(String(128))
    username: Mapped[str] = mapped_column(String(128))
    password_ciphertext: Mapped[str] = mapped_column(Text)
    encrypt: Mapped[bool] = mapped_column(Boolean)
    trust_server_certificate: Mapped[bool] = mapped_column(Boolean)
    allowed_objects: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    can_write: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractionRecord(Base):
    __tablename__ = "ingestion_extractions"
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_version_records.id"), primary_key=True
    )
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_connections.id"), index=True)
    schema_name: Mapped[str] = mapped_column(String(128))
    object_name: Mapped[str] = mapped_column(String(128))
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(Integer)
    byte_count: Mapped[int] = mapped_column(Integer)
    consistency: Mapped[str] = mapped_column(String(32))
    server_version: Mapped[str] = mapped_column(String(128))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def stored(record: ConnectionRecord) -> StoredConnection:
    return StoredConnection(
        id=record.id,
        owner_id=record.owner_id,
        project_id=record.project_id,
        name=record.name,
        host=record.host,
        port=record.port,
        database=record.database,
        username=record.username,
        password_ciphertext=record.password_ciphertext,
        encrypt=record.encrypt,
        trust_server_certificate=record.trust_server_certificate,
        allowed_objects=[SqlObject.model_validate(o) for o in record.allowed_objects],
        can_write=record.can_write,
        created_at=record.created_at,
    )


class SQLConnectionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, connection: StoredConnection) -> None:
        self.db.add(
            ConnectionRecord(
                id=connection.id,
                owner_id=connection.owner_id,
                project_id=connection.project_id,
                name=connection.name,
                host=connection.host,
                port=connection.port,
                database=connection.database,
                username=connection.username,
                password_ciphertext=connection.password_ciphertext,
                encrypt=connection.encrypt,
                trust_server_certificate=connection.trust_server_certificate,
                allowed_objects=[o.model_dump() for o in connection.allowed_objects],
                can_write=connection.can_write,
                created_at=connection.created_at,
            )
        )

    def list(self, owner: UUID, project: UUID) -> list[StoredConnection]:
        records = self.db.scalars(
            select(ConnectionRecord)
            .where(
                ConnectionRecord.owner_id == owner,
                ConnectionRecord.project_id == project,
                ConnectionRecord.revoked_at.is_(None),
            )
            .order_by(ConnectionRecord.created_at)
        )
        return [stored(record) for record in records]

    def get(self, owner: UUID, connection_id: UUID) -> StoredConnection:
        record = self.db.get(ConnectionRecord, connection_id)
        if record is None or record.owner_id != owner or record.revoked_at is not None:
            raise ApplicationError("CONNECTION_NOT_FOUND", "Conexión no encontrada.", 404)
        return stored(record)

    def revoke(self, owner: UUID, connection_id: UUID) -> None:
        record = self.db.get(ConnectionRecord, connection_id)
        if record is None or record.owner_id != owner or record.revoked_at is not None:
            raise ApplicationError("CONNECTION_NOT_FOUND", "Conexión no encontrada.", 404)
        record.revoked_at = datetime.now(UTC)
        # La contraseña cifrada se elimina al revocar; la procedencia de extracciones se conserva.
        record.password_ciphertext = ""

    def record_extraction(self, provenance: ExtractionProvenance) -> None:
        self.db.add(
            ExtractionRecord(
                version_id=provenance.version_id,
                connection_id=provenance.connection_id,
                schema_name=provenance.schema_name,
                object_name=provenance.name,
                columns=[c.model_dump() for c in provenance.columns],
                row_count=provenance.row_count,
                byte_count=provenance.byte_count,
                consistency=provenance.consistency,
                server_version=provenance.server_version,
                extracted_at=provenance.extracted_at,
            )
        )

    def extraction(self, owner: UUID, version_id: UUID) -> ExtractionProvenance | None:
        row = self.db.execute(
            select(ExtractionRecord, ConnectionRecord)
            .join(ConnectionRecord, ConnectionRecord.id == ExtractionRecord.connection_id)
            .where(ExtractionRecord.version_id == version_id, ConnectionRecord.owner_id == owner)
        ).first()
        if row is None:
            return None
        extraction, connection = row
        return ExtractionProvenance(
            version_id=extraction.version_id,
            connection_id=connection.id,
            connection_name=connection.name,
            host=connection.host,
            database=connection.database,
            schema_name=extraction.schema_name,
            name=extraction.object_name,
            columns=[SqlColumn.model_validate(c) for c in extraction.columns],
            row_count=extraction.row_count,
            byte_count=extraction.byte_count,
            consistency=extraction.consistency,
            server_version=extraction.server_version,
            extracted_at=extraction.extracted_at,
        )

    def audit(self, actor: UUID, entity: UUID, action: str, correlation: str) -> None:
        record_event(self.db, actor, entity, action, correlation)
