"""Reglas puras de analytics: tipos admitidos, valores de filtro y periodos de negocio.

Sin Polars ni SQL. Los valores de filtro se escriben con la representación canónica de la
Fase 6 y se interpretan según el tipo de la columna.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from dataflow.modules.analytics.contracts import (
    Filter,
    MetricDraft,
    MetricProblem,
    TimeGrain,
    measure_types,
)
from dataflow.platform.conversion import Converted, convert
from dataflow.platform.errors import ApplicationError

DECIMAL = re.compile(r"[+-]?(0|[1-9][0-9]*)(\.[0-9]+)?", re.ASCII)
ORDERED: frozenset[str] = frozenset({"gt", "gte", "lt", "lte", "between"})


def parse_value(text: str, data_type: str) -> Any:
    """Valor tipado de un filtro; ApplicationError si no corresponde al tipo de la columna."""
    if data_type == "string":
        return text
    if data_type == "decimal":
        if DECIMAL.fullmatch(text):
            return Decimal(text)
    elif data_type in {"integer", "date"}:
        result = convert(text, "integer" if data_type == "integer" else "date")
        if isinstance(result, Converted):
            return result.value
    elif data_type == "boolean" and text in {"true", "false"}:
        return text == "true"
    raise ApplicationError(
        "INVALID_FILTER_VALUE", f"«{text[:40]}» no es un valor válido de tipo {data_type}.", 422
    )


def filter_problems(filters: list[Filter], types: dict[UUID, str]) -> list[MetricProblem]:
    problems: list[MetricProblem] = []
    for item in filters:
        data_type = types.get(item.column_id)
        if data_type is None:
            problems.append(
                MetricProblem(
                    code="UNKNOWN_COLUMN", message="Un filtro usa una columna inexistente."
                )
            )
            continue
        if item.operator in ORDERED and data_type in {"string", "boolean"}:
            problems.append(
                MetricProblem(
                    code="COLUMN_TYPE_MISMATCH",
                    message=f"«{item.operator}» sólo admite columnas numéricas o de fecha.",
                )
            )
            continue
        try:
            for value in item.values:
                parse_value(value, data_type)
        except ApplicationError as error:
            problems.append(MetricProblem(code="INVALID_FILTER_VALUE", message=error.message))
    return problems


def metric_problems(draft: MetricDraft, columns: list[dict[str, Any]]) -> list[MetricProblem]:
    """Problemas de una métrica frente al esquema de una tabla (IDs y tipos)."""
    types = {UUID(str(c["id"])): str(c.get("technical_type", "string")) for c in columns}
    names = {UUID(str(c["id"])): str(c["name"]) for c in columns}
    problems: list[MetricProblem] = []
    measure = types.get(draft.measure_column_id)
    if measure is None:
        problems.append(
            MetricProblem(code="UNKNOWN_COLUMN", message="La columna medida no existe en la tabla.")
        )
    elif measure not in measure_types(draft.aggregation):
        problems.append(
            MetricProblem(
                code="COLUMN_TYPE_MISMATCH",
                message=f"«{draft.aggregation}» necesita una columna numérica; "
                f"«{names[draft.measure_column_id]}» es {measure}. Conviértela en Limpieza.",
            )
        )
    if draft.time_column_id is not None:
        time_type = types.get(draft.time_column_id)
        if time_type is None:
            problems.append(
                MetricProblem(
                    code="UNKNOWN_COLUMN", message="La columna temporal no existe en la tabla."
                )
            )
        elif time_type != "date":
            problems.append(
                MetricProblem(
                    code="COLUMN_TYPE_MISMATCH",
                    message=f"La columna temporal «{names[draft.time_column_id]}» debe ser "
                    "una fecha. Conviértela en Limpieza.",
                )
            )
    return problems + filter_problems(draft.filters, types)


def period(value: date, grain: TimeGrain) -> tuple[date, str]:
    """Inicio y etiqueta del periodo de negocio. Semanas ISO 8601: empiezan en lunes y
    pertenecen al año ISO (2025-12-29 es 2026-W01)."""
    if grain == "day":
        return value, value.isoformat()
    if grain == "week":
        year, week, _ = value.isocalendar()
        return value - timedelta(days=value.weekday()), f"{year}-W{week:02d}"
    if grain == "month":
        return value.replace(day=1), f"{value.year}-{value.month:02d}"
    if grain == "quarter":
        quarter = (value.month - 1) // 3 + 1
        return date(value.year, 3 * quarter - 2, 1), f"{value.year}-Q{quarter}"
    return date(value.year, 1, 1), str(value.year)
