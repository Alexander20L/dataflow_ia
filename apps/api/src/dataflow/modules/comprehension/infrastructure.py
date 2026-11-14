"""Valoraciones del usuario sobre las relaciones (Fase 19, migración 0020) y significados
escritos por el usuario (Fase 24, migración 0024) o marcados como desconocidos (Fase 24B,
migración 0025).

Registro inmutable y sólo de añadir: cada valoración es una fila nueva y vale la última. Se
agrupan por proyecto y fuente (`source_key`: archivo y hoja o tabla) para que la siguiente carga
del mismo archivo las tenga en cuenta.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.comprehension.contracts import (
    FeedbackItem,
    TargetChoice,
    UserMeaning,
    Verdict,
)
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


class MeaningRecord(Base):
    """Fase 24 (migración 0024): significado escrito o confirmado por el usuario."""

    __tablename__ = "column_meanings"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(700), index=True)
    column_name: Mapped[str] = mapped_column(String(200))
    meaning: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MeaningMarkRecord(Base):
    """Fase 24B (migración 0025): el usuario marca la columna como desconocida. Completa un
    significado de `column_meanings` (tabla nueva en vez de una columna nueva)."""

    __tablename__ = "column_meaning_marks"
    meaning_id: Mapped[UUID] = mapped_column(ForeignKey("column_meanings.id"), primary_key=True)
    unknown: Mapped[bool] = mapped_column(Boolean)


class SQLMeaningRepository:
    """Registro inmutable y sólo de añadir: vale el último de cada columna de la misma fuente,
    también en versiones posteriores. Uno vacío, sin confirmar y sin marcar vuelve al de la IA."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        source_key: str,
        column: str,
        meaning: str | None,
        confirmed: bool,
        unknown: bool = False,
    ) -> None:
        record = MeaningRecord(
            id=uuid4(),
            owner_id=owner,
            project_id=project,
            version_id=version,
            source_key=source_key,
            column_name=column,
            meaning=meaning.strip() if meaning and meaning.strip() and not unknown else None,
            confirmed=confirmed,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        if unknown:
            self.db.add(MeaningMarkRecord(meaning_id=record.id, unknown=True))
            self.db.flush()

    def for_source(self, owner: UUID, project: UUID, source_key: str) -> dict[str, UserMeaning]:
        """Último significado de cada columna (texto, ¿confirmado?, ¿desconocida?). Sin la
        tabla (esquema anterior a 0024, durante un despliegue) no hay ninguno; sin la de 0025,
        ninguna columna está marcada como desconocida."""
        try:
            with self.db.begin_nested():
                rows = list(
                    self.db.scalars(
                        select(MeaningRecord)
                        .where(
                            MeaningRecord.owner_id == owner,
                            MeaningRecord.project_id == project,
                            MeaningRecord.source_key == source_key,
                        )
                        .order_by(MeaningRecord.created_at, MeaningRecord.id)
                    )
                )
        except ProgrammingError:
            return {}
        latest = {row.column_name: row for row in rows}
        marked: set[UUID] = set()
        if latest:
            try:
                with self.db.begin_nested():
                    marked = {
                        mark.meaning_id
                        for mark in self.db.scalars(
                            select(MeaningMarkRecord).where(
                                MeaningMarkRecord.meaning_id.in_([r.id for r in latest.values()]),
                                MeaningMarkRecord.unknown.is_(True),
                            )
                        )
                    }
            except ProgrammingError:
                marked = set()
        return {
            name: UserMeaning(row.meaning, row.confirmed, row.id in marked)
            for name, row in latest.items()
            if row.meaning or row.confirmed or row.id in marked
        }


class TargetRecord(Base):
    """Fase 29 (migración 0028): el objetivo del análisis elegido por el usuario."""

    __tablename__ = "analysis_targets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(700), index=True)
    column_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLTargetRepository:
    """Registro inmutable y sólo de añadir: vale el último objetivo de la misma fuente (también
    en versiones posteriores). Uno sin columna vuelve al propuesto por las reglas o la IA."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        source_key: str,
        column: str | None,
        value: str | None,
    ) -> None:
        self.db.add(
            TargetRecord(
                id=uuid4(),
                owner_id=owner,
                project_id=project,
                version_id=version,
                source_key=source_key,
                column_name=column or None,
                value=(value or None) if column else None,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()

    def for_source(self, owner: UUID, project: UUID, source_key: str) -> TargetChoice | None:
        """El último objetivo elegido para la fuente. Sin la tabla (esquema anterior a 0028,
        durante un despliegue) no hay ninguno."""
        try:
            with self.db.begin_nested():
                row = self.db.scalars(
                    select(TargetRecord)
                    .where(
                        TargetRecord.owner_id == owner,
                        TargetRecord.project_id == project,
                        TargetRecord.source_key == source_key,
                    )
                    .order_by(TargetRecord.created_at.desc(), TargetRecord.id.desc())
                    .limit(1)
                ).first()
        except ProgrammingError:
            return None
        if row is None or row.column_name is None:
            return None
        return TargetChoice(column=row.column_name, value=row.value)
