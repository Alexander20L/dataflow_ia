"""Valoraciones de hallazgos (Fase 21, migración 0021) y versiones personalizadas del dashboard
(Fase 26, migración 0027).

Registro inmutable y sólo de añadir: cada marca es una fila nueva y vale la última de cada
elemento. Se guardan por versión: ordenan el dashboard y el informe de esa carga.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.curation.contracts import (
    CustomSection,
    DashboardCustomization,
    FindingFeedback,
    FindingVerdict,
)
from dataflow.platform.canonical import digest
from dataflow.platform.database import Base
from dataflow.platform.errors import ApplicationError


class FindingFeedbackRecord(Base):
    __tablename__ = "finding_feedback"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(700))
    verdict: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLFindingFeedback:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self, owner: UUID, project: UUID, version: UUID, item: str, verdict: FindingVerdict
    ) -> None:
        self.db.add(
            FindingFeedbackRecord(
                id=uuid4(),
                owner_id=owner,
                project_id=project,
                version_id=version,
                item_key=item,
                verdict=verdict,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def for_version(self, owner: UUID, version: UUID) -> list[FindingFeedback]:
        """Última marca de cada elemento de esta versión, sin las retiradas («none»). Sin la
        tabla (esquema anterior a 0021, durante un despliegue) no hay marcas."""
        try:
            with self.db.begin_nested():
                rows = list(
                    self.db.scalars(
                        select(FindingFeedbackRecord)
                        .where(
                            FindingFeedbackRecord.owner_id == owner,
                            FindingFeedbackRecord.version_id == version,
                        )
                        .order_by(FindingFeedbackRecord.created_at, FindingFeedbackRecord.id)
                    )
                )
        except ProgrammingError:
            return []
        latest = {row.item_key: row for row in rows}
        return [
            FindingFeedback(
                item=row.item_key,
                verdict=row.verdict,
                created_at=row.created_at,
            )
            for row in latest.values()
            if row.verdict != "none"
        ]


class DashboardCustomizationRecord(Base):
    """Revisión inmutable de la versión personalizada del dashboard de una versión del dataset."""

    __tablename__ = "dashboard_customizations"
    __table_args__ = (
        UniqueConstraint("owner_id", "version_id", "revision", name="uq_dashboard_customization"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    dashboard_execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_runs.id"))
    revision: Mapped[int] = mapped_column(Integer)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON)
    layout_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLDashboardCustomizations:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest(self, owner: UUID, version: UUID) -> DashboardCustomization | None:
        """La última revisión de la versión. Sin la tabla (esquema anterior a 0027, durante un
        despliegue) no hay versión personalizada."""
        try:
            with self.db.begin_nested():
                row = self.db.scalars(
                    select(DashboardCustomizationRecord)
                    .where(
                        DashboardCustomizationRecord.owner_id == owner,
                        DashboardCustomizationRecord.version_id == version,
                    )
                    .order_by(DashboardCustomizationRecord.revision.desc())
                    .limit(1)
                ).first()
        except ProgrammingError:
            return None
        if row is None:
            return None
        return DashboardCustomization(
            revision=row.revision,
            dashboard_execution_id=row.dashboard_execution_id,
            sections=[CustomSection.model_validate(s) for s in row.layout["sections"]],
            created_at=row.created_at,
        )

    def add(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        execution: UUID,
        expected: int,
        sections: list[CustomSection],
    ) -> DashboardCustomization:
        """Guarda una revisión nueva si `expected` es la vigente; si el contenido no cambia, no
        crea ninguna y devuelve la vigente."""
        current = self.latest(owner, version)
        if (current.revision if current else 0) != expected:
            raise ApplicationError(
                "DASHBOARD_REVISION_CONFLICT",
                "La versión personalizada cambió mientras la editabas: recarga el dashboard.",
                409,
            )
        layout = {"sections": [s.model_dump(mode="json") for s in sections]}
        if (
            current is not None
            and current.dashboard_execution_id == execution
            and [s.model_dump(mode="json") for s in current.sections] == layout["sections"]
        ):
            return current
        record = DashboardCustomizationRecord(
            id=uuid4(),
            owner_id=owner,
            project_id=project,
            version_id=version,
            dashboard_execution_id=execution,
            revision=expected + 1,
            layout=layout,
            layout_sha256=digest("dashboard_customization", layout),
            created_at=datetime.now(UTC),
        )
        try:
            with self.db.begin_nested():
                self.db.add(record)
                self.db.flush()
        except IntegrityError as error:
            raise ApplicationError(
                "DASHBOARD_REVISION_CONFLICT",
                "La versión personalizada cambió mientras la editabas: recarga el dashboard.",
                409,
            ) from error
        return DashboardCustomization(
            revision=record.revision,
            dashboard_execution_id=execution,
            sections=sections,
            created_at=record.created_at,
        )
