from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID, uuid5


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    byte_size: int

    @property
    def object_id(self) -> UUID:
        return uuid5(UUID("389f2079-a6dd-491b-b13c-8dcadcb07475"), self.key)


@dataclass(frozen=True)
class DatasetVersion:
    id: UUID
    dataset_id: UUID
    project_id: UUID
    owner_id: UUID
    number: int
    kind: Literal["imported", "derived"]
    file_name: str
    content: StoredObject
    created_at: datetime


@dataclass(frozen=True)
class ImportBinding:
    version_id: UUID
    execution_id: UUID
    table_artifact_id: UUID | None
    diagnostic_artifact_id: UUID | None
    profile_artifact_id: UUID | None
    quality_artifact_id: UUID | None


class ObjectStore(Protocol):
    def put(self, key: str, content: bytes) -> StoredObject: ...
    def read(self, reference: StoredObject) -> bytes: ...


class DatasetRepository(Protocol):
    def register_object(self, owner_id: UUID, reference: StoredObject, media_type: str) -> None: ...
    def object(self, owner_id: UUID, object_id: UUID) -> StoredObject: ...
    def lock_owner(self, owner_id: UUID) -> None: ...
    def used_bytes(self, owner_id: UUID) -> int: ...
    def count(self, owner_id: UUID) -> int: ...
    def register(
        self, owner_id: UUID, project_id: UUID, version_id: UUID, name: str, source: StoredObject
    ) -> DatasetVersion: ...
    def get(self, owner_id: UUID, version_id: UUID) -> DatasetVersion: ...
    def versions(
        self, owner_id: UUID, project_id: UUID, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]: ...
    def bind_import(self, version_id: UUID, execution_id: UUID) -> None: ...
    def binding(self, owner_id: UUID, version_id: UUID) -> ImportBinding: ...
    def materialized(
        self, version_id: UUID, execution_id: UUID, artifacts: dict[str, UUID]
    ) -> None: ...
