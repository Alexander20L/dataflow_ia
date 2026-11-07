"""Simulación determinista del copiloto para el proveedor falso (pytest, CI y E2E).

No pretende entender lenguaje natural: aplica reglas simples sobre la petición y el contexto
autorizado para recorrer el ciclo completo (aclaración → métrica → consulta → explicación) sin
clave ni red. Nunca obedece texto de los datos: sólo lee estructura (tipos, roles, IDs).
"""

import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from dataflow.modules.copilot.domain import UNTRUSTED

GRAINS = [
    ("mensual", "month"),
    ("mes", "month"),
    ("trimestr", "quarter"),
    ("anual", "year"),
    ("semana", "week"),
    ("diari", "day"),
]


def normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def raw(value: Any) -> Any:
    return value.get(UNTRUSTED) if isinstance(value, dict) else value


def respond(task: str, context: dict[str, Any], request: str) -> dict[str, Any]:
    if task == "explain_result":
        return explain(context)
    if task == "text_audit":
        return audit(context)
    return turn(context, normalized(request))


def empty(action: str, message: str) -> dict[str, Any]:
    return {
        "action": action,
        "message": message,
        "query": None,
        "metric": None,
        "cleaning_steps": [],
        "clarification": None,
    }


def clarify(topic: str, question: str) -> dict[str, Any]:
    return {
        **empty("ask_clarification", question),
        "clarification": {"topic": topic, "question": question},
    }


def turn(context: dict[str, Any], text: str) -> dict[str, Any]:
    columns = context["tabla"]["columnas"]
    if any(word in text for word in ("limpi", "espacio")):
        targets = [c["id"] for c in columns if c["tipo"] == "string"]
        if not targets:
            return clarify("other", "No encuentro columnas de texto que recortar.")
        return {
            **empty(
                "propose_cleaning_plan",
                "Propongo recortar los espacios de los bordes en las columnas de texto.",
            ),
            "cleaning_steps": [
                {
                    "operation": "cleaning.trim_whitespace",
                    "version": 1,
                    "parameters_json": '{"column_ids": ['
                    + ", ".join(f'"{t}"' for t in targets)
                    + "]}",
                }
            ],
        }
    grain = next((g for word, g in GRAINS if word in text), None)
    dimensions = [
        c["id"]
        for c in columns
        if c["tipo"] == "string" and normalized(str(raw(c["nombre"]))) in text
    ][:4]
    dates = [
        c
        for c in columns
        if c["tipo"] == "date" and c["rol"] == "business_date" and c["rol_confirmado"]
    ]
    if grain and not dates:
        return clarify(
            "business_date",
            "Para agrupar por periodo necesito una fecha de negocio confirmada. "
            "Confírmala en Entendimiento.",
        )
    metrics = [
        m
        for m in context["metricas"]
        if m["aplicable"] and m["agregacion"] in {"sum", "avg", "min", "max"}
    ]
    if metrics:
        metric = metrics[0]["id"]
        return {
            **empty(
                "propose_query",
                "Propongo calcular la métrica definida con la agrupación que pides.",
            ),
            "query": {
                "metric_ids": [metric],
                "dimension_ids": dimensions,
                "filters": [],
                "time_grain": grain,
                "time_start": None,
                "time_end": None,
                "comparisons": ["previous_period"] if grain and "anterior" in text else [],
                "ranking_metric_id": None,
                "ranking_direction": None,
                "top_n": None,
                "share_metric_ids": [],
            },
        }
    measures = [
        c
        for c in columns
        if c["tipo"] in {"integer", "decimal"} and c["rol"] == "measure" and c["rol_confirmado"]
    ]
    if len(measures) == 1:
        measure = measures[0]
        label = "Ventas" if "venta" in text else f"Total de {raw(measure['nombre'])}"
        return {
            **empty(
                "propose_metric",
                "Aún no hay una métrica para esto. Propongo definirla como la suma de la medida "
                "confirmada; revísala antes de crearla.",
            ),
            "metric": {
                "label": label,
                "description": None,
                "measure_column_id": measure["id"],
                "aggregation": "sum",
                "time_column_id": dates[0]["id"] if dates else None,
                "filters": [],
            },
        }
    if len(measures) > 1:
        return clarify("measure", "Hay varias medidas confirmadas: ¿cuál representa lo que pides?")
    return clarify(
        "measure",
        "No hay ninguna columna numérica confirmada como medida. Indica cuál representa lo que "
        "pides y confírmala en Entendimiento.",
    )


def explain(context: dict[str, Any]) -> dict[str, Any]:
    result = context["resultado"]
    values = []
    for cell in result["cifras"]:
        if cell["celda"] != "value" or cell["valor"] is None:
            continue
        try:
            values.append((Decimal(cell["valor"]), cell["evidencia"]))
        except InvalidOperation:
            continue
    if not values:
        return {"text": "El resultado no tiene cifras con valor para comparar."}
    values.sort(key=lambda item: (item[0], item[1]))
    low, high = values[0][1], values[-1][1]
    text = (
        f"El valor más alto es {{{{evidence:{high}}}}} en {{{{label:{high}}}}}."
        if low == high
        else f"El valor más alto es {{{{evidence:{high}}}}} en {{{{label:{high}}}}} y el más "
        f"bajo, {{{{evidence:{low}}}}} en {{{{label:{low}}}}}."
    )
    return {"text": text}


def audit(context: dict[str, Any]) -> dict[str, Any]:
    """Auditoría textual determinista (11F): la cifra más alta y la más baja de todo el
    dashboard, citadas por evidencia; una alerta si alguna tarjeta quedó fuera."""
    values = []
    for card in context["tarjetas"]:
        for cell in card["resultado"]["cifras"]:
            if cell["celda"] != "value" or cell["valor"] is None:
                continue
            try:
                values.append((Decimal(cell["valor"]), cell["evidencia"]))
            except InvalidOperation:
                continue
    if values:
        values.sort(key=lambda item: (item[0], item[1]))
        low, high = values[0][1], values[-1][1]
        summary = (
            f"La cifra más alta del dashboard es {{{{evidence:{high}}}}} en "
            f"{{{{label:{high}}}}} y la más baja, {{{{evidence:{low}}}}} en {{{{label:{low}}}}}."
        )
    else:
        summary = "Los resultados publicados no tienen cifras con valor que comparar."
    alerts = []
    if context["tarjetas_sin_resultado"]:
        alerts.append(
            {
                "titulo": "Tarjetas sin resultado",
                "detalle": "Algunas tarjetas no tienen una ejecución terminada y no se auditaron.",
                "severidad": "media",
            }
        )
    return {
        "resumen_ejecutivo": summary,
        "alertas_criticas": alerts,
        "recomendaciones": [
            "Revisa el origen de las cifras extremas antes de compartir el dashboard.",
            "Actualiza el dashboard cuando cargues una versión nueva de los datos.",
        ],
    }
