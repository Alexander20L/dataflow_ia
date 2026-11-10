"""Valoraciones del usuario sobre las relaciones (Fase 19, migración 0020).

Registro inmutable y sólo de añadir: cada valoración es una fila nueva y vale la última. Se
agrupan por proyecto y fuente (`source_key`: archivo y hoja o tabla) para que la siguiente carga
del mismo archivo las tenga en cuenta.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.comprehension.contracts import FeedbackItem, Verdict
from dataflow.platform.database import Base


class FeedbackRecord(Base):
    __tablename__ = "comprehension_feedback"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(600), index=True)
    relationship_key: Mapped[str] = mapped_column(String(400))
    verdict: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLFeedbackRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        source_key: str,
        relationship_key: str,
        verdict: Verdict,
    ) -> None:
        self.db.add(
            FeedbackRecord(
                id=uuid4(),
                owner_id=owner,
                project_id=project,
                version_id=version,
                source_key=source_key,
                relationship_key=relationship_key,
                verdict=verdict,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def for_version(self, owner: UUID, version: UUID) -> list[FeedbackItem]:
        """Última valoración de cada relación hecha sobre esta versión."""
        rows = self.db.scalars(
            select(FeedbackRecord)
            .where(FeedbackRecord.owner_id == owner, FeedbackRecord.version_id == version)
            .order_by(FeedbackRecord.created_at, FeedbackRecord.id)
        )
        latest = {row.relationship_key: row for row in rows}
        return [
            FeedbackItem(
                relationship_key=row.relationship_key,
                verdict=row.verdict,
                created_at=row.created_at,
            )
            for row in latest.values()
        ]

    def for_source(self, owner: UUID, project: UUID, source_key: str) -> dict[str, Verdict]:
        """Última valoración de cada relación en cualquier versión de la misma fuente. Sin la
        tabla (esquema anterior a 0020, durante un despliegue) no hay valoraciones."""
        try:
            with self.db.begin_nested():
                return self._for_source(owner, project, source_key)
        except ProgrammingError:
            return {}

    def _for_source(self, owner: UUID, project: UUID, source_key: str) -> dict[str, Verdict]:
        rows = self.db.scalars(
            select(FeedbackRecord)
            .where(
                FeedbackRecord.owner_id == owner,
                FeedbackRecord.project_id == project,
                FeedbackRecord.source_key == source_key,
            )
            .order_by(FeedbackRecord.created_at, FeedbackRecord.id)
        )
        return {row.relationship_key: row.verdict for row in rows}  # type: ignore[misc]
