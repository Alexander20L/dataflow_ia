"""Reglas puras de la sesión de análisis (sin SQL)."""

from uuid import UUID

from dataflow.modules.analysis_sessions.contracts import SessionInput
from dataflow.platform.errors import ApplicationError


def require_expected(current: int, expected: int) -> None:
    if current != expected:
        raise ApplicationError(
            "ANALYSIS_SESSION_CONFLICT",
            "La fuente activa cambió mientras tanto. Recarga la sesión y vuelve a intentarlo.",
            409,
        )


def unchanged(active: SessionInput | None, version: UUID, table: UUID) -> bool:
    """Seleccionar la misma versión y tabla que ya están activas no crea revisión."""
    return active is not None and active.version_id == version and active.table_artifact_id == table
