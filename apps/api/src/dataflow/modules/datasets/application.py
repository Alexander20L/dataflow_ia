from uuid import UUID

from dataflow.modules.datasets.contracts import (
    DatasetRepository,
    DatasetVersion,
    ImportBinding,
    StoredObject,
)


class Datasets:
    def __init__(self, repository: DatasetRepository) -> None:
        self.repository = repository

    def register_object(self, owner: UUID, reference: StoredObject, media_type: str) -> None:
        self.repository.register_object(owner, reference, media_type)

    def object(self, owner: UUID, object_id: UUID) -> StoredObject:
        return self.repository.object(owner, object_id)

    def lock_owner(self, owner: UUID) -> None:
        self.repository.lock_owner(owner)

    def used_bytes(self, owner: UUID) -> int:
        return self.repository.used_bytes(owner)

    def count(self, owner: UUID) -> int:
        return self.repository.count(owner)

    def register(
        self, owner: UUID, project: UUID, version: UUID, name: str, source: StoredObject
    ) -> DatasetVersion:
        return self.repository.register(owner, project, version, name, source)

    def get(self, owner: UUID, version: UUID) -> DatasetVersion:
        return self.repository.get(owner, version)

    def versions(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]:
        return self.repository.versions(owner, project, limit, offset)

    def bind_import(self, version: UUID, execution: UUID) -> None:
        self.repository.bind_import(version, execution)

    def binding(self, owner: UUID, version: UUID) -> ImportBinding:
        return self.repository.binding(owner, version)

    def materialized(self, version: UUID, execution: UUID, artifacts: dict[str, UUID]) -> None:
        self.repository.materialized(version, execution, artifacts)
