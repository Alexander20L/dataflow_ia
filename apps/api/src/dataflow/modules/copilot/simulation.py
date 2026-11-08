"""Simulación determinista del proveedor falso (pytest, CI y E2E) para la explicación automática.

Sin clave ni red: produce una explicación válida que cita la primera cifra autorizada. Nunca
obedece texto de los datos: sólo lee la estructura del contexto.
"""

from typing import Any


def respond(task: str, context: dict[str, Any], request: str) -> dict[str, Any]:
    if task != "overview_audit":
        raise ValueError(f"Tarea de IA no simulada: {task}")
    cells = context["cifras"]
    summary = "El dashboard conserva los resultados descriptivos de la fuente."
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
