from uuid import UUID

from dataflow.modules.analysis_sessions.public import ReadyInput
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.errors import ApplicationError


class AnalysisSessionInputs:
    """Puerto de la sesión de análisis sobre proyectos, versiones y ejecuciones (Fase 11A).

    Una versión está lista cuando su procesamiento terminó bien y tiene tabla publicada: la
    importación (CSV) o el perfil y la calidad de una derivada."""

    def __init__(
        self, projects: ProjectPermissions, datasets: Datasets, executions: Executions
    ) -> None:
        self.projects, self.datasets, self.executions = projects, datasets, executions

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None:
        self.projects.require(owner, project, writable=writable)

    def ready_input(self, owner: UUID, project: UUID, version: UUID) -> ReadyInput:
        record = self.datasets.get(owner, version)
        if record.project_id != project:
            raise ApplicationError(
                "INPUT_NOT_FOUND", "La versión no pertenece a este proyecto.", 404
            )
        binding = self.datasets.binding(owner, version)
        run = self.executions.get(owner, binding.execution_id)
        if run.state in {"failed", "cancelled"}:
            raise ApplicationError(
                "INPUT_INVALID",
                "Esta versión no se pudo procesar; la fuente activa no cambia.",
                409,
            )
        if run.state != "succeeded" or binding.table_artifact_id is None:
            raise ApplicationError(
                "INPUT_NOT_READY",
                "Esta versión todavía se está procesando; la fuente activa no cambia.",
                409,
            )
        table = self.executions.artifact(owner, binding.table_artifact_id)
        return ReadyInput(
            version_id=record.id,
            version_number=record.number,
            version_kind=record.kind,
            file_name=record.file_name,
            table_artifact_id=table.id,
            table_sha256=table.content.sha256,
        )
