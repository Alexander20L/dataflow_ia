from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from dataflow.bootstrap.dependencies import CurrentIdentity, Projects
from dataflow.modules.projects.domain import ProjectStatus

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(default="", max_length=300)
    file_name: str | None = Field(default=None, min_length=1, max_length=255)


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(default="", max_length=300)
    expected_revision: int = Field(ge=1)


class ArchiveProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    file_name: str | None
    status: ProjectStatus
    revision: int
    created_at: datetime
    updated_at: datetime


class ProjectPageResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


@router.get("", response_model=ProjectPageResponse, operation_id="listProjects")
def list_projects(
    identity: CurrentIdentity,
    service: Projects,
    q: Annotated[str, Query(max_length=80)] = "",
    status: ProjectStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectPageResponse:
    page = service.list(identity.user.id, q.strip(), status, limit, offset)
    return ProjectPageResponse(
        items=[ProjectResponse.model_validate(p) for p in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=ProjectResponse, status_code=201, operation_id="createProject")
def create_project(
    body: CreateProjectRequest, identity: CurrentIdentity, service: Projects
) -> ProjectResponse:
    return ProjectResponse.model_validate(
        service.create(
            identity.user.id,
            body.name,
            body.description,
            body.file_name,
        )
    )


@router.get("/{project_id}", response_model=ProjectResponse, operation_id="getProject")
def get_project(project_id: UUID, identity: CurrentIdentity, service: Projects) -> ProjectResponse:
    return ProjectResponse.model_validate(service.get(identity.user.id, project_id))


@router.patch("/{project_id}", response_model=ProjectResponse, operation_id="updateProject")
def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    identity: CurrentIdentity,
    service: Projects,
) -> ProjectResponse:
    return ProjectResponse.model_validate(
        service.edit(
            identity.user.id,
            project_id,
            body.name,
            body.description,
            body.expected_revision,
        )
    )


@router.post("/{project_id}/archive", response_model=ProjectResponse, operation_id="archiveProject")
def archive_project(
    project_id: UUID,
    body: ArchiveProjectRequest,
    identity: CurrentIdentity,
    service: Projects,
) -> ProjectResponse:
    return ProjectResponse.model_validate(
        service.archive(
            identity.user.id,
            project_id,
            body.expected_revision,
        )
    )
