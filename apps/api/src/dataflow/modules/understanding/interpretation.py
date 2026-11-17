"""Interpretación descriptiva por reglas: sin llamadas IA, mapeos ni escrituras SQL."""

import re
import unicodedata
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from dataflow.modules.understanding.contracts import (
    AutomaticColumnHint,
    AutomaticInterpretation,
    AutomaticTemplateHint,
    DatasetProfile,
)
from dataflow.modules.understanding.templates import TableColumn, candidates

IDENTIFIERS = {"id", "codigo", "code", "sku", "postal", "telefono", "phone", "dni", "ruc"}
LABELS = {
    "generic": "Perfil general de datos",
    "sales": "Posible contexto de ventas",
    "inventory": "Posible contexto de inventario",
    "ambiguous": "Contexto de negocio no concluyente",
}


def name_tokens(name: str) -> set[str]:
    # Separar camelCase/ID sin interpretar el nombre aportado por la persona como regex.
    spaced = re.sub(r"([a-záéíóúñ])([A-Z])", r"\1 \2", name)
    normalized = unicodedata.normalize("NFKD", spaced.casefold())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return set(re.findall(r"[a-z0-9]+", plain))


def interpret(profile: DatasetProfile) -> AutomaticInterpretation:
    hints: list[AutomaticColumnHint] = []
    for ordinal, column in enumerate(profile.columns):
        role: Literal["identifier", "date", "numeric", "category", "text", "empty"] = "text"
        evidence = [f"{profile.row_count - column.null_count} valores no nulos."]
        if name_tokens(column.name) & IDENTIFIERS:
            role = "identifier"
            evidence.append("El nombre sugiere un identificador: no se agrega como medida.")
        elif column.null_count == profile.row_count:
            role = "empty"
            evidence.append("No hay valores para interpretar su tipo.")
        elif column.suggested_type == "date":
            role = "date"
            evidence.append("El tipo o formato de fecha es reconocible; su función de negocio no.")
        elif column.numeric is not None:
            role = "numeric"
            evidence.append("Los valores admiten estadísticas numéricas; no se infiere aditividad.")
        elif column.unique_count <= 50 and column.unique_count <= max(
            1, (profile.row_count - column.null_count) // 2
        ):
            role = "category"
            evidence.append("Hay valores repetidos con cardinalidad acotada para frecuencias.")
        else:
            evidence.append("Se conserva como texto: sin interpretación numérica inequívoca.")
        hints.append(
            AutomaticColumnHint(
                ordinal=ordinal,
                name=column.name,
                role=role,
                evidence=evidence,
                statistics_allowed=role == "numeric",
            )
        )

    columns = [
        TableColumn(
            id=uuid5(NAMESPACE_URL, f"automatic-column:{index}:{column.name}"),
            name=column.name,
            technical_type=column.technical_type,
            scale=None,
            suggested_type=column.suggested_type,
        )
        for index, column in enumerate(profile.columns)
        if hints[index].role not in {"empty", "identifier"}
    ]
    proposed: list[AutomaticTemplateHint] = []
    for candidate in candidates(columns):
        if candidate.template == "generic@1":
            continue
        matched = [item.role for item in candidate.roles if item.column is not None]
        # Exigir señales centrales, no dos roles accesorios como fecha + región.
        core = (
            {"product", "quantity"} if candidate.template == "inventory@1" else {"date", "amount"}
        )
        if core <= set(matched):
            proposed.append(
                AutomaticTemplateHint(
                    template=candidate.template,
                    label=candidate.label,
                    matched_roles=matched,
                    missing_roles=candidate.missing_required,
                )
            )
    ready = [candidate for candidate in proposed if not candidate.missing_roles]
    context: Literal["generic", "sales", "inventory", "ambiguous"] = "generic"
    if len(ready) > 1:
        context = "ambiguous"
    elif ready:
        context = "inventory" if ready[0].template == "inventory@1" else "sales"
    elif proposed:
        context = "ambiguous"

    mixed_currency = any(
        name_tokens(column.name) & {"moneda", "currency", "divisa"} and column.unique_count > 1
        for column in profile.columns
    )
    if mixed_currency:
        for index, hint in enumerate(hints):
            if hint.role == "numeric" and name_tokens(hint.name) & {
                "importe",
                "monto",
                "amount",
                "precio",
                "price",
                "cost",
                "costo",
                "coste",
                "revenue",
                "ingresos",
                "total",
            }:
                hints[index] = hint.model_copy(
                    update={
                        "statistics_allowed": False,
                        "evidence": [
                            *hint.evidence,
                            "Más de una moneda: no se agregan estos valores entre monedas.",
                        ],
                    }
                )
    available = ["Conteos, completitud, duplicados y detalle del archivo."]
    if any(hint.statistics_allowed for hint in hints):
        available.append("Promedios, mínimos y máximos de columnas numéricas reconocibles.")
    if any(hint.role == "date" for hint in hints):
        available.append("Frecuencia de registros por mes, sin asumir fecha de venta o de corte.")
    if any(hint.role == "category" for hint in hints):
        available.append("Frecuencia y ranking de categorías, con cobertura visible.")
    limitations = [
        "Moneda, unidad y significado de cada fila no se deducen de nombres o tipos.",
        "No se calculan ingresos, número de ventas ni stock actual sin una definición sustentable.",
    ]
    if mixed_currency:
        limitations.append(
            "Hay más de una moneda en la fuente: se omitieron estadísticas monetarias "
            "combinadas. No se aplicaron tipos de cambio."
        )
    if proposed:
        limitations.append(
            "Los contextos son candidatos por coincidencias de nombre y tipo, no confirmaciones."
        )
    if any(candidate.template == "inventory@1" for candidate in proposed):
        limitations.append(
            "No se suman cortes de inventario entre fechas ni se infiere valoración monetaria."
        )
    return AutomaticInterpretation(
        context=context,
        label=LABELS[context],
        summary=(
            "Se preparó una lectura descriptiva de las columnas y se seleccionaron análisis "
            "técnicos compatibles. Las ambigüedades no requieren respuestas: se omiten "
            "las conclusiones de negocio que no pueden justificarse."
        ),
        columns=hints,
        candidates=proposed,
        available_analyses=available,
        limitations=limitations,
    )
