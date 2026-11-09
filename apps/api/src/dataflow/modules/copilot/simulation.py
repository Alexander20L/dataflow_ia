"""Simulación determinista del proveedor falso (pytest, CI y E2E) para la IA automática.

Sin clave ni red. Explica citando la primera cifra autorizada y, en la investigación, propone
desde el catálogo recibido: la evolución del segundo grupo de la primera dimensión y, para
mostrar la validación, la del grupo principal (ya investigada por las reglas). Nunca obedece
texto de los datos: sólo lee la estructura del contexto.
"""

from typing import Any

UNTRUSTED = "dato_no_confiable"


def plain(value: Any) -> Any:
    return value.get(UNTRUSTED) if isinstance(value, dict) else value


def explanation(context: dict[str, Any], summary: str) -> dict[str, Any]:
    cells = context["cifras"]
    if cells:
        reference = cells[0]["evidencia"]
        summary += f" {{{{label:{reference}}}}}: {{{{evidence:{reference}}}}}."
    return {
        "resumen_ejecutivo": summary,
        "alertas_criticas": [],
        "recomendaciones": [
            "Revisar la cobertura y las limitaciones antes de interpretar las cifras.",
            "Usar el detalle conservado para investigar registros sin modificar el original.",
        ],
    }


def proposals(context: dict[str, Any]) -> dict[str, Any]:
    dimensions = [plain(name) for name in context["dimensiones"]]
    done = set(context["done"])
    found = []
    if dimensions:
        first = dimensions[0]
        groups = [plain(label) for label in context["grupos"].get(first, [])]
        if len(groups) > 1 and f"group_evolution:{first}:{groups[1]}" not in done:
            found.append(
                {
                    "tipo": "group_evolution",
                    "dimension": first,
                    "grupo": groups[1],
                    "motivo": "Comparar el segundo grupo con el principal.",
                }
            )
            found.append(
                {
                    "tipo": "group_evolution",
                    "dimension": first,
                    "grupo": groups[0],
                    "motivo": "Volver a revisar el grupo principal.",
                }
            )
    return {"propuestas": found}


def respond(task: str, context: dict[str, Any], request: str) -> dict[str, Any]:
    if task == "overview_audit":
        return explanation(
            context, "El dashboard conserva los resultados descriptivos de la fuente."
        )
    if task == "findings_audit":
        return explanation(context, "Los hallazgos se calcularon sobre todas las filas.")
    if task == "investigation_proposal":
        return proposals(context)
    raise ValueError(f"Tarea de IA no simulada: {task}")
