"""Valoraciones de hallazgos (Fase 21, migración 0021).

Registro inmutable y sólo de añadir: cada marca es una fila nueva y vale la última de cada
elemento. Se guardan por versión: ordenan el dashboard y el informe de esa carga.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.curation.contracts import FindingFeedback, FindingVerdict
from dataflow.platform.database import Base


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
