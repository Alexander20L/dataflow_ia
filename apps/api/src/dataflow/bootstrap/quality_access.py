from typing import Any
from uuid import UUID

from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import Executions
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.quality.rules_contracts import BaseTable
from dataflow.platform.errors import ApplicationError


class QualityTableAccess:
    """Puerto de quality: tablas publicadas, permisos e informes, por interfaces públicas."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        projects: ProjectPermissions,
        objects: ObjectStore,
    ) -> None:
        self.datasets, self.executions = datasets, executions
        self.projects, self.objects = projects, objects

    def table(self, owner: UUID, artifact: UUID) -> tuple[UUID, BaseTable, list[dict[str, Any]]]:
        table = self.executions.artifact(owner, artifact)
        if table.kind != "table" or not table.columns:
            raise ApplicationError(
                "PLAN_TABLE_REQUIRED",
                "Selecciona una representación tabular publicada con esquema.",
                409,
            )
        version = self.datasets.get(owner, table.version_id)
        self.projects.require(owner, version.project_id)
        return (
            version.project_id,
            BaseTable(
                version_id=version.id,
                artifact_id=table.id,
                artifact_sha256=table.content.sha256,
            ),
            table.columns,
        )

    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None:
        self.projects.require(owner, project, writable)

    def rules_report(self, owner: UUID, execution: UUID) -> bytes | None:
        for artifact in self.executions.artifacts(owner, execution):
            if artifact.kind == "quality_rules":
                return self.objects.read(artifact.content)
        return None
