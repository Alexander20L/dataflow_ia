"""Correcciones manuales del diccionario (Fase 22, migración 0022; Fase 23, migración 0023).

Registro inmutable y sólo de añadir: cada corrección es una fila nueva y vale la última de cada
columna de la misma fuente (mismo archivo y misma hoja o tabla), también en versiones
posteriores. Recalcular la inspección nunca las toca. Desde la Fase 23 cada corrección se
completa con una fila en `column_annotation_details` (textos nulos y datos personales).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column

from dataflow.modules.inspection.contracts import AnnotationRequest, ColumnAnnotation
from dataflow.platform.database import Base


class ColumnAnnotationRecord(Base):
    __tablename__ = "column_annotations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_version_records.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(700))
    column_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nature: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ColumnAnnotationDetailRecord(Base):
    __tablename__ = "column_annotation_details"
    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("column_annotations.id"), primary_key=True
    )
    null_tokens: Mapped[list[str]] = mapped_column(JSON)
    personal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


def meaningful(row: ColumnAnnotationRecord, detail: ColumnAnnotationDetailRecord | None) -> bool:
    """Una corrección vacía (todo nulo, sin confirmar ni decidir) vuelve a la automática."""
    return bool(
        row.role
        or row.nature
        or row.time_format
        or row.notes
        or row.confirmed
        or (detail is not None and (detail.null_tokens or detail.personal is not None))
    )


class SQLColumnAnnotations:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        source: str,
        column: str,
        request: AnnotationRequest,
    ) -> None:
        annotation = uuid4()
        self.db.add(
            ColumnAnnotationRecord(
                id=annotation,
                owner_id=owner,
                project_id=project,
                version_id=version,
                source_key=source,
                column_name=column,
                role=request.role,
                nature=request.nature,
                time_format=request.time_format,
                notes=request.notes.strip() if request.notes else None,
                confirmed=request.confirmed,
                created_at=datetime.now(UTC),
            )
        )
        self.db.flush()
        # Sólo si hay algo que guardar: una corrección de la Fase 22 no necesita detalle.
        if request.null_tokens or request.personal is not None:
            self.db.add(
                ColumnAnnotationDetailRecord(
                    annotation_id=annotation,
                    null_tokens=list(dict.fromkeys(request.null_tokens)),
                    personal=request.personal,
                )
            )
            self.db.flush()

    def for_source(self, owner: UUID, project: UUID, source: str) -> dict[str, ColumnAnnotation]:
        """Última corrección de cada columna de la fuente. Una corrección vacía (todo nulo y sin
        confirmar) devuelve la columna a la clasificación automática. Sin la tabla (esquema
        anterior a 0022, durante un despliegue) no hay correcciones; sin la de 0023, no hay textos
        nulos ni decisiones sobre datos personales."""
        try:
            with self.db.begin_nested():
                rows = list(
                    self.db.scalars(
                        select(ColumnAnnotationRecord)
                        .where(
                            ColumnAnnotationRecord.owner_id == owner,
                            ColumnAnnotationRecord.project_id == project,
                            ColumnAnnotationRecord.source_key == source,
                        )
                        .order_by(ColumnAnnotationRecord.created_at, ColumnAnnotationRecord.id)
                    )
                )
        except ProgrammingError:
            return {}
        latest = {row.column_name: row for row in rows}
        details: dict[UUID, ColumnAnnotationDetailRecord] = {}
        if latest:
            try:
                with self.db.begin_nested():
                    details = {
                        d.annotation_id: d
                        for d in self.db.scalars(
                            select(ColumnAnnotationDetailRecord).where(
                                ColumnAnnotationDetailRecord.annotation_id.in_(
                                    [row.id for row in latest.values()]
                                )
                            )
                        )
                    }
            except ProgrammingError:
                details = {}
        result = {}
        for name, row in latest.items():
            detail = details.get(row.id)
            if not meaningful(row, detail):
                continue
            result[name] = ColumnAnnotation(
                column=name,
                role=row.role,
                nature=row.nature,
                time_format=row.time_format,
                notes=row.notes,
                confirmed=row.confirmed,
                version_id=row.version_id,
                created_at=row.created_at,
                null_tokens=list(detail.null_tokens) if detail else [],
                personal=detail.personal if detail else None,
            )
        return result
