from uuid import UUID

from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.templates.contracts import TableColumn
from dataflow.modules.understanding.public import SemanticService


class TemplateTablesAccess:
    """Puerto de templates sobre understanding (columnas y sugerencias) y proyectos."""

    def __init__(self, semantics: SemanticService, projects: ProjectPermissions) -> None:
        self.semantics, self.projects = semantics, projects

    def columns(self, owner: UUID, artifact: UUID) -> tuple[UUID, list[TableColumn]]:
        context = self.semantics.context(owner, artifact)
        hints = {hint.column_id: hint for hint in context.suggestions}
        version = self.semantics_project(owner, artifact)
        return version, [
            TableColumn(
                id=column.id,
                name=column.name,
                technical_type=column.technical_type,
                scale=column.type_parameters.get("scale"),
                suggested_role=hints[column.id].suggested_role if column.id in hints else None,
                suggested_type=hints[column.id].suggested_type if column.id in hints else None,
            )
            for column in context.columns
        ]

    def semantics_project(self, owner: UUID, artifact: UUID) -> UUID:
        return self.semantics.access.resolve(owner, artifact).project_id

    def require_project(self, owner: UUID, project: UUID, writable: bool) -> None:
        self.projects.require(owner, project, writable=writable)
