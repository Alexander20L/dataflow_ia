from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.audit.public import record_event
from dataflow.modules.projects.application import ProjectPage
from dataflow.modules.projects.domain import Project, ProjectStatus
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class ProjectRecord(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_status", "owner_id", "status"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLProjectRepository:
    def __init__(self, db: Session, correlation_id: str) -> None:
        self.db = db
        self.correlation_id = correlation_id

    @staticmethod
    def domain(record: ProjectRecord) -> Project:
        return Project(
            record.id,
            record.owner_id,
            record.name,
            record.description,
            record.file_name,
            cast(ProjectStatus, record.status),
            record.revision,
            record.created_at,
            record.updated_at,
        )

    def page(
        self, owner_id: UUID, q: str, status: ProjectStatus | None, limit: int, offset: int
    ) -> ProjectPage:
        conditions = [ProjectRecord.owner_id == owner_id]
        if q:
            conditions.append(func.lower(ProjectRecord.name).contains(q.lower(), autoescape=True))
        if status:
            conditions.append(ProjectRecord.status == status)
        total = (
            self.db.scalar(select(func.count()).select_from(ProjectRecord).where(*conditions)) or 0
        )
        records = self.db.scalars(
            select(ProjectRecord)
            .where(*conditions)
            .order_by(ProjectRecord.updated_at.desc(), ProjectRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return ProjectPage([self.domain(row) for row in records], total, limit, offset)

    def get(self, owner_id: UUID, project_id: UUID) -> Project | None:
        record = self.db.scalar(
            select(ProjectRecord).where(
                ProjectRecord.id == project_id,
                ProjectRecord.owner_id == owner_id,
            )
        )
        return self.domain(record) if record else None

    def create(self, project: Project) -> None:
        self.db.add(ProjectRecord(**vars(project)))
        record_event(self.db, project.owner_id, project.id, "project.created", self.correlation_id)
        self.db.commit()

    def update(self, project: Project, expected_revision: int, action: str) -> None:
        result = self.db.execute(
            update(ProjectRecord)
            .where(
                ProjectRecord.id == project.id,
                ProjectRecord.owner_id == project.owner_id,
                ProjectRecord.revision == expected_revision,
            )
            .values(
                name=project.name,
                description=project.description,
                status=project.status,
                revision=project.revision,
                updated_at=project.updated_at,
            )
            .returning(ProjectRecord.id)
        )
        if result.scalar_one_or_none() is None:
            self.db.rollback()
            raise ApplicationError(
                "REVISION_CONFLICT", "El proyecto cambió. Recarga y reintenta.", 409
            )
        record_event(self.db, project.owner_id, project.id, action, self.correlation_id)
        self.db.commit()
