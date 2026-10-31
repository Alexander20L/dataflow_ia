from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dataflow.modules.projects.infrastructure import ProjectRecord
from dataflow.platform.errors import ApplicationError


class ProjectPermissions:
    """Interfaz pública de acceso; el lock coordina subida y archivo del proyecto."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def require(self, owner_id: UUID, project_id: UUID, writable: bool = False) -> None:
        statement = select(ProjectRecord).where(
            ProjectRecord.id == project_id, ProjectRecord.owner_id == owner_id
        )
        if writable:
            statement = statement.with_for_update()
        project = self.db.scalar(statement)
        if not project:
            raise ApplicationError("PROJECT_NOT_FOUND", "Proyecto no encontrado.", 404)
        if writable and project.status == "archived":
            raise ApplicationError(
                "PROJECT_ARCHIVED", "No se pueden subir datos a un proyecto archivado.", 409
            )
