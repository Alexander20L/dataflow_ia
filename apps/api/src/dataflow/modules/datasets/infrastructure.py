import hashlib
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.datasets.contracts import (
    DatasetVersion,
    ImportBinding,
    StoredObject,
    VersionLineage,
)
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class DatasetRecord(Base):
    __tablename__ = "datasets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)


class VersionRecord(Base):
    __tablename__ = "dataset_version_records"
    __table_args__ = (
        UniqueConstraint("dataset_id", "number", name="uq_dataset_version_record_number"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id"), index=True)
    number: Mapped[int]
    kind: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(255))
    content_object_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_objects.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ObjectRecord(Base):
    __tablename__ = "dataset_objects"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    media_type: Mapped[str] = mapped_column(String(100))


class VersionLineageRecord(Base):
    """Vínculo 1:1 de una versión derivada con su versión de origen y la ejecución que la
    produjo. Tabla aparte para que el código y los datos 0.5/0.6 no dependan de columnas nuevas."""

    __tablename__ = "dataset_version_lineage"
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_version_records.id"), primary_key=True
    )
    parent_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_version_records.id"), index=True
    )
    producer_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_runs.id"), unique=True
    )


class ImportBindingRecord(Base):
    __tablename__ = "dataset_import_bindings"
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_version_records.id"), primary_key=True
    )
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"), unique=True)
    table_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_artifacts.id"))
    diagnostic_artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("execution_artifacts.id")
    )
    profile_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_artifacts.id"))
    quality_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_artifacts.id"))


class DatasetDefaultRecord(Base):
    __tablename__ = "dataset_defaults"
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id"), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"))
    table_artifact_id: Mapped[UUID] = mapped_column(ForeignKey("execution_artifacts.id"))
    revision: Mapped[int]


class SQLDatasetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def view(self, version: VersionRecord, dataset: DatasetRecord) -> DatasetVersion:
        return DatasetVersion(
            version.id,
            dataset.id,
            dataset.project_id,
            dataset.owner_id,
            version.number,
            cast(Literal["imported", "derived"], version.kind),
            version.file_name,
            self.object(dataset.owner_id, version.content_object_id),
            version.created_at,
        )

    def register_object(self, owner_id: UUID, reference: StoredObject, media_type: str) -> None:
        current = self.db.get(ObjectRecord, reference.object_id)
        if current:
            if (
                current.owner_id,
                current.object_key,
                current.sha256,
                current.byte_size,
                current.media_type,
            ) != (owner_id, reference.key, reference.sha256, reference.byte_size, media_type):
                raise ApplicationError(
                    "OBJECT_METADATA_CONFLICT", "La referencia inmutable no coincide.", 409
                )
            return
        self.db.add(
            ObjectRecord(
                id=reference.object_id,
                owner_id=owner_id,
                object_key=reference.key,
                sha256=reference.sha256,
                byte_size=reference.byte_size,
                media_type=media_type,
            )
        )
        self.db.flush()

    def object(self, owner_id: UUID, object_id: UUID) -> StoredObject:
        record = self.db.get(ObjectRecord, object_id)
        if not record or record.owner_id != owner_id:
            raise ApplicationError("OBJECT_NOT_FOUND", "Objeto no encontrado.", 404)
        return StoredObject(record.object_key, record.sha256, record.byte_size)

    def lock_owner(self, owner_id: UUID) -> None:
        key = hashlib.sha256(b"ingestion-quota" + owner_id.bytes).digest()
        self.db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(key[:8], signed=True))))

    def used_bytes(self, owner_id: UUID) -> int:
        return int(
            self.db.scalar(
                select(func.sum(ObjectRecord.byte_size))
                .select_from(VersionRecord)
                .join(DatasetRecord)
                .join(ObjectRecord, ObjectRecord.id == VersionRecord.content_object_id)
                .where(DatasetRecord.owner_id == owner_id, VersionRecord.kind == "imported")
            )
            or 0
        )

    def count(self, owner_id: UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(DatasetRecord)
                .where(DatasetRecord.owner_id == owner_id)
            )
            or 0
        )

    def register(
        self, owner_id: UUID, project_id: UUID, version_id: UUID, name: str, source: StoredObject
    ) -> DatasetVersion:
        dataset = self.db.scalar(
            select(DatasetRecord)
            .where(DatasetRecord.project_id == project_id, DatasetRecord.owner_id == owner_id)
            .with_for_update()
        )
        if not dataset:
            dataset = DatasetRecord(id=uuid4(), project_id=project_id, owner_id=owner_id)
            self.db.add(dataset)
            self.db.flush()
        number = (
            int(
                self.db.scalar(
                    select(func.max(VersionRecord.number)).where(
                        VersionRecord.dataset_id == dataset.id
                    )
                )
                or 0
            )
            + 1
        )
        self.register_object(owner_id, source, "text/csv")
        record = VersionRecord(
            id=version_id,
            dataset_id=dataset.id,
            number=number,
            kind="imported",
            file_name=name,
            content_object_id=source.object_id,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        return self.view(record, dataset)

    def get(self, owner_id: UUID, version_id: UUID) -> DatasetVersion:
        row = self.db.execute(
            select(VersionRecord, DatasetRecord)
            .join(DatasetRecord)
            .where(VersionRecord.id == version_id, DatasetRecord.owner_id == owner_id)
        ).first()
        if not row:
            raise ApplicationError("VERSION_NOT_FOUND", "Versión no encontrada.", 404)
        return self.view(row[0], row[1])

    def versions(
        self, owner_id: UUID, project_id: UUID, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]:
        query = (
            select(VersionRecord, DatasetRecord)
            .join(DatasetRecord)
            .where(
                DatasetRecord.owner_id == owner_id,
                DatasetRecord.project_id == project_id,
                VersionRecord.kind.in_(["imported", "derived"]),
            )
        )
        total = int(self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        records = self.db.execute(
            query.order_by(VersionRecord.number.desc()).limit(limit).offset(offset)
        )
        return [self.view(v, d) for v, d in records], total

    def bind_import(self, version_id: UUID, execution_id: UUID) -> None:
        self.db.add(ImportBindingRecord(version_id=version_id, execution_id=execution_id))
        self.db.flush()

    def binding(self, owner_id: UUID, version_id: UUID) -> ImportBinding:
        self.get(owner_id, version_id)
        record = self.db.get(ImportBindingRecord, version_id)
        if not record:
            raise ApplicationError(
                "IMPORT_BINDING_NOT_FOUND", "No existe ingesta baseline para esta versión.", 404
            )
        return ImportBinding(
            record.version_id,
            record.execution_id,
            record.table_artifact_id,
            record.diagnostic_artifact_id,
            record.profile_artifact_id,
            record.quality_artifact_id,
        )

    def materialized(
        self, version_id: UUID, execution_id: UUID, artifacts: dict[str, UUID]
    ) -> None:
        binding = self.db.get(ImportBindingRecord, version_id)
        if not binding or binding.execution_id != execution_id:
            return
        if binding.table_artifact_id is not None:
            raise ApplicationError(
                "BASELINE_ALREADY_PUBLISHED", "La representación baseline ya está publicada.", 409
            )
        binding.table_artifact_id = artifacts["table"]
        binding.profile_artifact_id = artifacts.get("profile")
        binding.quality_artifact_id = artifacts.get("quality")
        version = self.db.get(VersionRecord, version_id)
        assert version is not None
        self.db.scalar(
            select(DatasetRecord).where(DatasetRecord.id == version.dataset_id).with_for_update()
        )
        current = self.db.get(DatasetDefaultRecord, version.dataset_id)
        previous = self.db.get(VersionRecord, current.version_id) if current else None
        if not current:
            self.db.add(
                DatasetDefaultRecord(
                    dataset_id=version.dataset_id,
                    version_id=version_id,
                    table_artifact_id=artifacts["table"],
                    revision=1,
                )
            )
        elif previous and version.number >= previous.number:
            current.version_id, current.table_artifact_id = version_id, artifacts["table"]
            current.revision += 1
        self.db.flush()

    def register_derived(
        self,
        parent: DatasetVersion,
        version_id: UUID,
        producer_execution_id: UUID,
        content: StoredObject,
    ) -> DatasetVersion:
        dataset = self.db.scalar(
            select(DatasetRecord).where(DatasetRecord.id == parent.dataset_id).with_for_update()
        )
        assert dataset is not None
        number = (
            int(
                self.db.scalar(
                    select(func.max(VersionRecord.number)).where(
                        VersionRecord.dataset_id == dataset.id
                    )
                )
                or 0
            )
            + 1
        )
        self.register_object(dataset.owner_id, content, "application/vnd.apache.parquet")
        record = VersionRecord(
            id=version_id,
            dataset_id=dataset.id,
            number=number,
            kind="derived",
            file_name=f"{parent.file_name} · limpieza",
            content_object_id=content.object_id,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        self.db.add(
            VersionLineageRecord(
                version_id=version_id,
                parent_version_id=parent.id,
                producer_execution_id=producer_execution_id,
            )
        )
        self.db.flush()
        return self.view(record, dataset)

    def bind_derived(self, version_id: UUID, execution_id: UUID, table_artifact_id: UUID) -> None:
        # Compatibilidad (ADR-015): las derivadas reutilizan el vínculo "baseline" de las
        # importaciones; su ejecución de referencia es el perfil/calidad encolado al publicar.
        self.db.add(
            ImportBindingRecord(
                version_id=version_id,
                execution_id=execution_id,
                table_artifact_id=table_artifact_id,
            )
        )
        self.db.flush()

    def materialize_derived(
        self, version_id: UUID, execution_id: UUID, artifacts: dict[str, UUID]
    ) -> bool:
        """Completa el diagnóstico de una derivada. No modifica la versión predeterminada."""
        binding = self.db.get(ImportBindingRecord, version_id)
        if (
            not binding
            or binding.execution_id != execution_id
            or self.db.get(VersionLineageRecord, version_id) is None
        ):
            return False
        binding.profile_artifact_id = artifacts.get("profile")
        binding.quality_artifact_id = artifacts.get("quality")
        self.db.flush()
        return True

    def lineage(self, owner_id: UUID, version_id: UUID) -> VersionLineage | None:
        self.get(owner_id, version_id)
        record = self.db.get(VersionLineageRecord, version_id)
        if not record:
            return None
        return VersionLineage(
            record.version_id, record.parent_version_id, record.producer_execution_id
        )
