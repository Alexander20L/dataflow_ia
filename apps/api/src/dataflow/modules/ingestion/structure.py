"""Cambios de estructura entre versiones del mismo archivo (Fase 18, `structure-comparison-v1`).

Puro: compara los perfiles publicados de dos versiones. Sólo informa; no renombra ni mapea
columnas (un nombre distinto es una columna quitada y otra añadida).
"""

from dataflow.modules.ingestion.contracts import ColumnChange, StructureComparison
from dataflow.modules.understanding.contracts import DatasetProfile

TYPES = {
    "string": "texto",
    "integer": "entero",
    "decimal": "decimal",
    "date": "fecha",
    "boolean": "verdadero/falso",
}
ROLES = {
    "identifier": "identificador",
    "dimension": "dimensión",
    "measure": "medida",
    "time": "tiempo",
    "text": "texto",
    "empty": "vacía",
}


def roles(profile: DatasetProfile) -> dict[str, str]:
    analysis = profile.overview.analysis if profile.overview else None
    return {c.name: c.role for c in analysis.columns} if analysis else {}


def compare(
    previous: DatasetProfile, current: DatasetProfile, previous_id: str, previous_number: int
) -> StructureComparison:
    before = {c.name: c for c in previous.columns}
    after = {c.name: c for c in current.columns}
    old_roles, new_roles = roles(previous), roles(current)
    changes: list[ColumnChange] = []
    unchanged = 0
    for column in current.columns:
        if column.name not in before:
            changes.append(ColumnChange(column=column.name, change="added"))
            continue
        old = before[column.name]
        if old.suggested_type != column.suggested_type:
            changes.append(
                ColumnChange(
                    column=column.name,
                    change="type_changed",
                    before=TYPES[old.suggested_type],
                    after=TYPES[column.suggested_type],
                )
            )
        elif (
            column.name in old_roles
            and column.name in new_roles
            and old_roles[column.name] != new_roles[column.name]
        ):
            changes.append(
                ColumnChange(
                    column=column.name,
                    change="role_changed",
                    before=ROLES.get(old_roles[column.name], old_roles[column.name]),
                    after=ROLES.get(new_roles[column.name], new_roles[column.name]),
                )
            )
        else:
            unchanged += 1
    changes.extend(
        ColumnChange(column=c.name, change="removed")
        for c in previous.columns
        if c.name not in after
    )
    return StructureComparison(
        previous_version_id=previous_id,
        previous_version_number=previous_number,
        changes=[c.model_copy(update={"description": describe(c)}) for c in changes],
        unchanged=unchanged,
    )


def describe(change: ColumnChange) -> str:
    """Frase en español para la interfaz y el informe."""
    if change.change == "added":
        return f"Columna nueva: «{change.column}»."
    if change.change == "removed":
        return f"Ya no está la columna «{change.column}»."
    what = "el tipo" if change.change == "type_changed" else "el papel"
    return f"«{change.column}» cambió {what}: de {change.before} a {change.after}."
