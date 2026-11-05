from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from dataflow.modules.datasets.contracts import StoredObject

__all__ = ["StoredObject", "Version", "ENGINE_VERSION", "ImportState"]

ImportState = Literal["queued", "processing", "succeeded", "failed", "cancelled"]
MAX_ATTEMPTS = 3
LEASE_SECONDS = 120
ENGINE_VERSION = "csv-ingestion-1"


@dataclass(frozen=True)
class Version:
    id: UUID
    dataset_id: UUID
    project_id: UUID
    number: int
    file_name: str
    sha256: str
    byte_size: int
    created_at: datetime
    execution_id: UUID
    state: ImportState
    row_count: int | None
    column_count: int | None
    error_code: str | None
    error_message: str | None
    attempts: int
    kind: Literal["imported", "derived"] = "imported"
    parent_version_id: UUID | None = None
