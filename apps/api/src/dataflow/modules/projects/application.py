from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from dataflow.modules.projects.domain import Project, ProjectStatus
from dataflow.platform.errors import ApplicationError


@dataclass(frozen=True)
class ProjectPage:
    items: list[Project]
    total: int
    limit: int
    offset: int


class ProjectRepository(Protocol):
    def page(
        self, owner_id: UUID, q: str, status: ProjectStatus | None, limit: int, offset: int
    ) -> ProjectPage: ...
    def get(self, owner_id: UUID, project_id: UUID) -> Project | None: ...
    def create(self, project: Project) -> None: ...
    def update(self, project: Project, expected_revision: int, action: str) -> None: ...


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    def list(
        self, owner_id: UUID, q: str, status: ProjectStatus | None, limit: int, offset: int
    ) -> ProjectPage:
        return self.repository.page(owner_id, q, status, limit, offset)

    def get(self, owner_id: UUID, project_id: UUID) -> Project:
        project = self.repository.get(owner_id, project_id)
        if not project:
            raise ApplicationError("PROJECT_NOT_FOUND", "Proyecto no encontrado.", 404)
        return project

    def create(self, owner_id: UUID, name: str, description: str, file_name: str | None) -> Project:
        now = datetime.now(UTC)
        project = Project(uuid4(), owner_id, name, description, file_name, "draft", 1, now, now)
        self.repository.create(project)
        return project

    def edit(
        self, owner_id: UUID, project_id: UUID, name: str, description: str, revision: int
    ) -> Project:
        project = self.get(owner_id, project_id).edit(name, description, revision)
        self.repository.update(project, revision, "project.updated")
        return project

    def archive(self, owner_id: UUID, project_id: UUID, revision: int) -> Project:
        current = self.get(owner_id, project_id)
        edited = current.edit(current.name, current.description, revision)
        project = replace(edited, status="archived")
        self.repository.update(project, revision, "project.archived")
        return project
