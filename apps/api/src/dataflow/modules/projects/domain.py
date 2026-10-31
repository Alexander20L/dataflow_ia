from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from dataflow.platform.errors import ApplicationError

ProjectStatus = Literal["draft", "archived"]


@dataclass(frozen=True)
class Project:
    id: UUID
    owner_id: UUID
    name: str
    description: str
    file_name: str | None
    status: ProjectStatus
    revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not 3 <= len(self.name.strip()) <= 80 or len(self.description) > 300:
            raise ApplicationError("INVALID_PROJECT", "Nombre o descripción no válidos.", 422)
        if self.revision < 1:
            raise ApplicationError("INVALID_REVISION", "Revisión no válida.", 422)

    def edit(self, name: str, description: str, expected_revision: int) -> "Project":
        if self.status == "archived":
            raise ApplicationError("PROJECT_ARCHIVED", "El proyecto está archivado.", 409)
        if self.revision != expected_revision:
            raise ApplicationError(
                "REVISION_CONFLICT", "El proyecto cambió. Recarga y reintenta.", 409
            )
        return replace(
            self,
            name=name,
            description=description,
            revision=self.revision + 1,
            updated_at=datetime.now(UTC),
        )
