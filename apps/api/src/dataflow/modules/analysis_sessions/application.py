from uuid import UUID

from dataflow.modules.analysis_sessions.contracts import (
    AnalysisSessionView,
    SessionInputPage,
    SessionInputs,
    SessionRepository,
    SessionState,
)
from dataflow.modules.analysis_sessions.domain import require_expected, unchanged
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork

NOT_FOUND = ("ANALYSIS_SESSION_NOT_FOUND", "Sesión de análisis no encontrada.", 404)


class AnalysisSessionService:
    """Una sesión por proyecto con una sola tabla activa (Fase 11A).

    - Una candidata no sustituye a la activa hasta estar lista: si está en proceso, falló o se
      canceló, la selección se rechaza y la fuente anterior sigue activa.
    - Cambiar de fuente no modifica planes ni resultados: cada ejecución conserva su entrada.
    """

    def __init__(
        self, repository: SessionRepository, inputs: SessionInputs, uow: UnitOfWork
    ) -> None:
        self.repository, self.inputs, self.uow = repository, inputs, uow

    def view(self, session: SessionState) -> AnalysisSessionView:
        active = self.repository.head(session)
        return AnalysisSessionView(
            id=session.id,
            project_id=session.project_id,
            revision=session.revision,
            status="ready" if active else "empty",
            active=active,
            created_at=session.created_at,
        )

    def open(self, owner: UUID, project: UUID) -> tuple[AnalysisSessionView, bool]:
        """Devuelve la sesión del proyecto o la crea (una por proyecto)."""
        existing = self.repository.by_project(owner, project)
        if existing:
            self.inputs.require_project(owner, project, writable=False)
            return self.view(existing), False
        try:
            # Bloquea el proyecto: dos aperturas simultáneas crean una sola sesión.
            self.inputs.require_project(owner, project, writable=True)
            existing = self.repository.by_project(owner, project)
            created = existing is None
            session = existing or self.repository.create(owner, project)
            result = self.view(session)
            self.uow.commit()
            return result, created
        except Exception:
            self.uow.rollback()
            raise

    def for_project(self, owner: UUID, project: UUID) -> AnalysisSessionView:
        self.inputs.require_project(owner, project, writable=False)
        session = self.repository.by_project(owner, project)
        if not session:
            raise ApplicationError(*NOT_FOUND)
        return self.view(session)

    def get(self, owner: UUID, session: UUID) -> AnalysisSessionView:
        return self.view(self.repository.get(owner, session))

    def select(
        self, owner: UUID, session_id: UUID, version: UUID, expected: int, correlation: str
    ) -> AnalysisSessionView:
        try:
            session = self.repository.get(owner, session_id, lock=True)
            self.inputs.require_project(owner, session.project_id, writable=True)
            require_expected(session.revision, expected)
            ready = self.inputs.ready_input(owner, session.project_id, version)
            if unchanged(self.repository.head(session), ready.version_id, ready.table_artifact_id):
                result = self.view(session)
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return result
            self.repository.append(session, ready, owner, correlation)
            result = self.view(self.repository.get(owner, session_id))
            self.uow.commit()
            return result
        except Exception:
            self.uow.rollback()
            raise

    def history(self, owner: UUID, session_id: UUID, limit: int, offset: int) -> SessionInputPage:
        session = self.repository.get(owner, session_id)
        items, total = self.repository.history(session, limit, offset)
        return SessionInputPage(items=items, total=total)
