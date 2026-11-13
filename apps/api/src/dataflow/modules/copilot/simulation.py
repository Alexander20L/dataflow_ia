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


def comprehension(context: dict[str, Any]) -> dict[str, Any]:
    """Hipótesis deterministas: describe cada columna por su rol y relaciona la primera medida
    con la primera dimensión (y, para mostrar la validación, con una columna inexistente)."""
    columns = [(plain(item["nombre"]), item["rol"]) for item in context["columnas"]]
    measures = [name for name, role in columns if role == "measure"]
    dimensions = [name for name, role in columns if role == "dimension"]
    relations = []
    if measures and dimensions:
        relations.append(
            {
                "columnas": [measures[0], dimensions[0]],
                "tipo": "asociacion",
                "hipotesis": f"{measures[0]} podría variar según {dimensions[0]}.",
            }
        )
    if measures:
        relations.append(
            {
                "columnas": [measures[0], "Columna inventada"],
                "tipo": "asociacion",
                "hipotesis": "Relación con una columna que no existe.",
            }
        )
    return {
        "dominio": "Registros de actividad con medidas y dimensiones para agrupar.",
        "entidades": [{"nombre": "Registro", "columnas": [name for name, _ in columns][:5]}],
        "columnas": [
            {
                "columna": name,
                "significado": f"Columna con rol {role}.",
                "entidad": "Registro",
                "justificacion": f"El perfil la clasifica con el rol {role}.",
            }
            for name, role in columns
        ],
        "ordenes": [],
        "relaciones": relations,
        "preguntas": [f"¿Qué grupo concentra más {measures[0]}?"] if measures else [],
    }


def exploration_queries(context: dict[str, Any]) -> dict[str, Any]:
    """Una consulta válida (promedio de la primera medida por la primera dimensión), una suma de
    una medida no aditiva si la hay (para mostrar el rechazo) y una columna inventada."""
    columns = context["columnas"]
    measures = [plain(c["columna"]) for c in columns if c["tipo"] == "medida"]
    additive = {plain(c["columna"]) for c in columns if c.get("aditiva")}
    dimensions = [plain(c["columna"]) for c in columns if c["tipo"] == "dimension"]
    found: list[dict[str, Any]] = []
    if measures and dimensions:
        found.append(
            {
                "tipo": "aggregate",
                "medida": measures[0],
                "dimensiones": [dimensions[-1]],
                "agregacion": "mean",
                "motivo": f"Cómo varía el promedio de {measures[0]} según {dimensions[-1]}.",
                "pregunta": f"¿Cambia el promedio de {measures[0]} según {dimensions[-1]}?",
                "hipotesis": f"El promedio de {measures[0]} no es igual en todos los grupos.",
                "esperado": f"El promedio de {measures[0]} de cada {dimensions[-1]}.",
                "prioridad": 2,
            }
        )
        flat = [m for m in measures if m not in additive]
        if flat:
            found.append(
                {
                    "tipo": "aggregate",
                    "medida": flat[0],
                    "dimensiones": [dimensions[0]],
                    "agregacion": "sum",
                    "motivo": "Sumar una medida que no es aditiva.",
                }
            )
    found.append(
        {
            "tipo": "aggregate",
            "dimensiones": ["Columna inventada"],
            "agregacion": "count",
            "motivo": "Una columna que no existe.",
        }
    )
    return {"consultas": found}


def relevance(context: dict[str, Any]) -> dict[str, Any]:
    """El primer resultado es relevante; los demás no. Desde la Fase 25 (con catálogo), el
    primero propone profundizar con una consulta inventada (para mostrar el rechazo)."""
    deepen = (
        [
            {
                "tipo": "aggregate",
                "dimensiones": ["Columna inventada"],
                "agregacion": "count",
                "motivo": "Una columna que no existe.",
                "pregunta": "¿Se reparte igual en una columna que no existe?",
            }
        ]
        if "catalogo" in context
        else []
    )
    return {
        "juicios": [
            {
                "clave": item["clave"],
                "relevante": index == 0,
                "motivo": "El reparto entre grupos es desigual."
                if index == 0
                else "Sin diferencias destacables entre grupos.",
                "profundizar": deepen if index == 0 else [],
            }
            for index, item in enumerate(context["resultados"])
        ]
    }


def report_narrative(context: dict[str, Any]) -> dict[str, Any]:
    """Cita la primera evidencia, escribe un número libre (se retira) y añade una conclusión
    causal (se retira): la verificación debe dejar sólo lo comprobable."""
    figures = context["cifras"]
    if not figures:
        return {
            "resumen": "No se encontraron hallazgos relevantes en este análisis.",
            "conclusiones": ["Los datos no muestran resultados relevantes."],
            "recomendaciones": ["Revisar la calidad y el periodo de los datos."],
        }
    first = figures[0]["evidencia"]
    return {
        "resumen": f"El hallazgo principal alcanza {{{{evidence:{first}}}}} en 12 meses. "
        "Las ventas bajaron porque cambió el precio.",
        "conclusiones": [
            f"El resultado principal es {{{{evidence:{first}}}}}.",
            "La caída se debe a la competencia.",
        ],
        "recomendaciones": ["Revisar los grupos que más aportan antes de decidir."],
    }


def dashboard_design(context: dict[str, Any]) -> dict[str, Any]:
    """Primero un indicador y la exploración; después los hallazgos en orden inverso. Incluye
    un gráfico incompatible, un elemento inventado y un título con una cifra propia."""
    items = context["elementos"]

    def chart(item: dict[str, Any]) -> str:
        options = [w for w in item["graficos_compatibles"] if w != "kpi"]
        return "pie" if "pie" in options else options[0]

    essentials: list[dict[str, Any]] = []
    with_figures = [i for i in items if i["cifras"]]
    if with_figures:
        essentials.append(
            {
                "elemento": with_figures[0]["id"],
                "grafico": "kpi",
                "cifra": with_figures[0]["cifras"][0],
                "titulo": "Cifra principal",
            }
        )
    essentials += [
        {"elemento": i["id"], "grafico": chart(i), "titulo": "Top 99 de la exploración"}
        for i in items
        if i["origen"] == "exploration"
    ]
    essentials = essentials[:12]  # el esquema admite 12 elementos por sección
    detail = [
        {"elemento": i["id"], "grafico": chart(i)}
        for i in reversed(items)
        if i["origen"] == "insight"
    ]
    wrong: list[dict[str, Any]] = [{"elemento": "insight:inventado", "grafico": "bar"}]
    if items and "line" not in items[0]["graficos_compatibles"]:
        wrong.append({"elemento": items[0]["id"], "grafico": "line"})
    return {
        "titulo": "Panorama del negocio",
        "secciones": [
            {
                "titulo": "Lo esencial",
                "descripcion": "Lo primero que mirar.",
                "elementos": essentials,
            },
            {"titulo": "Detalle", "elementos": (wrong + detail)[:12]},
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
    if task == "business_comprehension":
        return comprehension(context)
    if task == "exploration_proposal":
        return exploration_queries(context)
    if task == "exploration_relevance":
        return relevance(context)
    if task == "dashboard_design":
        return dashboard_design(context)
    if task == "report_narrative":
        return report_narrative(context)
    raise ValueError(f"Tarea de IA no simulada: {task}")
