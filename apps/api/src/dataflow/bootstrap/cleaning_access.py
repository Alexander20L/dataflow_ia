from uuid import UUID

from dataflow.modules.datasets.public import Datasets
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.contracts import PlanView
from dataflow.modules.projects.public import ProjectPermissions


class CleaningPlanAccess:
    """Puerto de cleaning sobre planning y proyectos (planes guardados, validación y permisos)."""

    def __init__(
        self, planning: PlanningService, projects: ProjectPermissions, datasets: Datasets
    ) -> None:
        self.planning, self.projects, self.datasets = planning, projects, datasets

    def plan(self, owner: UUID, revision: UUID) -> PlanView:
        return self.planning.get(owner, revision)

    def require_write(self, owner: UUID, project: UUID) -> None:
        self.projects.require(owner, project, writable=True)

    def lock_owner(self, owner: UUID) -> None:
        self.datasets.lock_owner(owner)
