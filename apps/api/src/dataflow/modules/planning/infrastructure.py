from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.planning.contracts import PlanValidation, Problem
from dataflow.modules.planning.domain import plan_status
from dataflow.platform.database import Base


class PlanningValidationRecord(Base):
    """Validación inmutable de una revisión para una versión de catálogo."""

    __tablename__ = "planning_validations"
    plan_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_plan_revisions.id"), primary_key=True
    )
    catalog_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    problems: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    valid: Mapped[bool]
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanningCreateRequest(Base):
    """Identidad de POST /projects/{id}/plans (Idempotency-Key) y revisión resultante."""

    __tablename__ = "planning_create_requests"
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    request_key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    plan_revision_id: Mapped[UUID] = mapped_column(ForeignKey("execution_plan_revisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLPlanningRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def validation(self, plan: UUID, catalog_version: str) -> PlanValidation | None:
        record = self.db.get(PlanningValidationRecord, (plan, catalog_version))
        if not record:
            return None
        problems = [Problem.model_validate(problem) for problem in record.problems]
        return PlanValidation(
            catalog_version=record.catalog_version,
            status=plan_status(problems),
            valid=record.valid,
            problems=problems,
            validated_at=record.validated_at,
        )

    def save_validation(self, plan: UUID, validation: PlanValidation) -> None:
        # Idempotente: dos lecturas concurrentes pueden revalidar a la vez el mismo catálogo;
        # el resultado es determinista y prevalece el primero (la fila es inmutable).
        self.db.execute(
            insert(PlanningValidationRecord)
            .values(
                plan_revision_id=plan,
                catalog_version=validation.catalog_version,
                problems=[problem.model_dump(mode="json") for problem in validation.problems],
                valid=validation.valid,
                validated_at=validation.validated_at,
            )
            .on_conflict_do_nothing(index_elements=["plan_revision_id", "catalog_version"])
        )

    def request(self, project: UUID, key: UUID) -> tuple[str, UUID] | None:
        record = self.db.get(PlanningCreateRequest, (project, key))
        return (record.fingerprint, record.plan_revision_id) if record else None

    def remember(self, project: UUID, key: UUID, owner: UUID, fingerprint: str, plan: UUID) -> None:
        self.db.add(
            PlanningCreateRequest(
                project_id=project,
                request_key=key,
                owner_id=owner,
                fingerprint=fingerprint,
                plan_revision_id=plan,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()
