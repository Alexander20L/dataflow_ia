"""Motor de analytics.query@1 (subproceso aislado, sin base de datos).

Polars lee la tabla publicada; la agregación se calcula en Python con aritmética exacta
(`int` y `Decimal`), porque la media de Polars sobre decimales devuelve un float. Sumas con la
escala de la columna, media cuantizada a `avg_scale` con HALF_EVEN, nulos excluidos y contados,
grupos con valor nulo explícitos y orden estable por todas las dimensiones.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

from dataflow.modules.analytics.contracts import (
    MISSING,
    AnalysisResult,
    EvidenceScope,
    Filter,
    MetricContent,
    MetricCounts,
    MetricDefinition,
    MetricReference,
    QueryParameters,
    ResultColumn,
    ResultRow,
)
from dataflow.modules.analytics.domain import parse_value, period
from dataflow.platform.canonical import digest
from dataflow.platform.data_types import MAX_DECIMAL_PRECISION, DataType
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import Cell, canonical_cell, canonical_decimal, display_cell

MISSING_LABEL = "(sin valor)"


@dataclass(frozen=True)
class Metric:
    reference: MetricReference
    revision: int
    content: MetricContent
    unit: str | None = None
    currency: str | None = None


@dataclass
class Accumulator:
    count: int = 0
    total: Any = 0
    minimum: Any = None
    maximum: Any = None
    distinct: set[str] = field(default_factory=set)


@lru_cache(maxsize=4096)
def parsed(text: str, data_type: str) -> Any:
    """Valor de filtro interpretado una sola vez (no por fila)."""
    return parse_value(text, data_type)


def matches(value: Cell, item: Filter, data_type: str) -> bool:
    """Semántica de filtros: un nulo sólo cumple `is_null`; nunca se compara con valores."""
    if item.operator == "is_null":
        return value is None
    if item.operator == "is_not_null":
        return value is not None
    if value is None:
        return False
    values = [parsed(text, data_type) for text in item.values]
    if item.operator == "eq":
        return bool(value == values[0])
    if item.operator == "neq":
        return bool(value != values[0])
    if item.operator == "in":
        return value in values
    if item.operator == "not_in":
        return value not in values
    if item.operator == "between":
        return bool(values[0] <= value <= values[1])
    compare: Callable[[Any, Any], bool] = {
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
    }[item.operator]
    return compare(value, values[0])


def canonical_key(value: Cell, data_type: DataType, parameters: dict[str, Any]) -> Any:
    """Valor de una dimensión en la clave de evidencia: celda canónica de la Fase 6 o la marca
    explícita {"missing": true}, nunca una cadena que pueda confundirse con un dato."""
    return dict(MISSING) if value is None else canonical_cell(value, data_type, parameters)


def sort_component(value: Any) -> tuple[int, Any]:
    return (1, "") if value is None else (0, value)


def run_query(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    metrics: list[Metric],
    parameters: QueryParameters,
    scope: EvidenceScope,
) -> AnalysisResult:
    if [str(c["name"]) for c in columns] != headers:
        raise ApplicationError("SCHEMA_MISMATCH", "El esquema no coincide con la tabla.", 409)
    index = {UUID(str(c["id"])): position for position, c in enumerate(columns)}
    kinds: dict[UUID, DataType] = {
        UUID(str(c["id"])): cast(DataType, c.get("technical_type", "string")) for c in columns
    }
    params = {UUID(str(c["id"])): dict(c.get("type_parameters", {})) for c in columns}

    def position(column: UUID) -> int:
        if column not in index:
            raise ApplicationError("UNKNOWN_COLUMN", "Una columna no existe en la tabla.", 422)
        return index[column]

    time_columns = {m.content.time_column_id for m in metrics}
    uses_time = parameters.time_grain is not None or parameters.time_range is not None
    time_column: UUID | None = None
    if uses_time:
        if len(time_columns) != 1 or None in time_columns:
            raise ApplicationError(
                "TIME_COLUMN_MISMATCH",
                "Todas las métricas deben declarar la misma columna temporal.",
                422,
            )
        time_column = next(iter(time_columns))
        assert time_column is not None
        if kinds[time_column] != "date":
            raise ApplicationError("COLUMN_TYPE_MISMATCH", "La columna temporal no es fecha.", 422)

    query_filters = list(parameters.filters)
    if parameters.time_range is not None and time_column is not None:
        bounds = parameters.time_range
        if bounds.start:
            query_filters.append(
                Filter(column_id=time_column, operator="gte", values=[bounds.start])
            )
        if bounds.end:
            query_filters.append(Filter(column_id=time_column, operator="lte", values=[bounds.end]))

    def accepted(row: Sequence[Any], filters: list[Filter]) -> bool:
        return all(matches(row[position(f.column_id)], f, kinds[f.column_id]) for f in filters)

    dims = [position(column) for column in parameters.dimensions]
    time_position = position(time_column) if time_column is not None else None
    groups: dict[str, dict[str, Any]] = {}
    accumulators: dict[tuple[str, str], Accumulator] = {}
    definitions: list[MetricDefinition] = []
    base = [accepted(row, query_filters) for row in rows]

    for number, metric in enumerate(metrics):
        key_name = f"m{number}"
        content = metric.content
        measure = position(content.measure_column_id)
        measure_type = kinds[content.measure_column_id]
        filtered = excluded_nulls = 0
        for row, keep in zip(rows, base, strict=True):
            if not (keep and accepted(row, content.filters)):
                filtered += 1
                continue
            value = row[measure]
            if value is None:
                excluded_nulls += 1
                continue
            components: list[Any] = [
                canonical_key(
                    row[d], kinds[parameters.dimensions[i]], params[parameters.dimensions[i]]
                )
                for i, d in enumerate(dims)
            ]
            sort_values: list[Any] = [row[d] for d in dims]
            if parameters.time_grain is not None and time_position is not None:
                day = row[time_position]
                if day is None:
                    components.append(dict(MISSING))
                    sort_values.append(None)
                else:
                    start, label = period(day, parameters.time_grain)
                    components.append({"grain": parameters.time_grain, "start": start.isoformat()})
                    sort_values.append(start)
            group = json.dumps(components, sort_keys=True)
            if group not in groups:
                groups[group] = {"components": components, "sort": sort_values, "row": row}
            acc = accumulators.setdefault((group, key_name), Accumulator())
            acc.count += 1
            if content.aggregation in {"sum", "avg"}:
                acc.total += value
            elif content.aggregation in {"min", "max"}:
                acc.minimum = value if acc.minimum is None else min(acc.minimum, value)
                acc.maximum = value if acc.maximum is None else max(acc.maximum, value)
            elif content.aggregation == "count_distinct":
                acc.distinct.add(
                    json.dumps(
                        canonical_cell(value, measure_type, params[content.measure_column_id])
                    )
                )
        included = len(rows) - filtered - excluded_nulls
        scale = (
            params[content.measure_column_id].get("scale") if measure_type == "decimal" else None
        )
        definitions.append(
            MetricDefinition(
                key=key_name,
                revision_id=metric.reference.revision_id,
                revision=metric.revision,
                content_sha256=metric.reference.content_sha256,
                label=content.label,
                aggregation=content.aggregation,
                measure_column_id=content.measure_column_id,
                measure_column=headers[measure],
                time_column_id=content.time_column_id,
                filters=content.filters,
                null_policy=content.null_policy,
                unit=metric.unit,
                currency=metric.currency,
                scale=parameters.avg_scale if content.aggregation == "avg" else scale,
                counts=MetricCounts(
                    input_rows=len(rows),
                    excluded_by_filters=filtered,
                    excluded_by_nulls=excluded_nulls,
                    included_rows=included,
                ),
            )
        )

    if len(groups) > parameters.max_result_rows:
        raise ApplicationError(
            "RESULT_TOO_LARGE",
            f"El resultado tendría {len(groups)} filas y el límite de la consulta es "
            f"{parameters.max_result_rows}. Añade filtros o usa menos dimensiones.",
            422,
        )

    def value_of(group: str, number: int, metric: Metric) -> str | None:
        content = metric.content
        acc = accumulators.get((group, f"m{number}"))
        if content.aggregation in {"count", "count_distinct"}:
            if acc is None:
                return "0"
            return str(acc.count if content.aggregation == "count" else len(acc.distinct))
        if acc is None:
            return None  # ninguna fila de esta métrica en el grupo: no es 0
        kind = kinds[content.measure_column_id]
        parameters_of = params[content.measure_column_id]
        if content.aggregation == "avg":
            with localcontext() as context:
                context.prec = 2 * MAX_DECIMAL_PRECISION
                mean = Decimal(acc.total) / Decimal(acc.count)
                text = canonical_decimal(mean, parameters.avg_scale)
        elif content.aggregation == "sum":
            text = (
                str(int(acc.total))
                if kind == "integer"
                else canonical_decimal(Decimal(acc.total), int(parameters_of["scale"]))
            )
        else:
            chosen = acc.minimum if content.aggregation == "min" else acc.maximum
            text = display_cell(chosen, kind, parameters_of) or ""
        if len(text.lstrip("-").replace(".", "")) > MAX_DECIMAL_PRECISION:
            raise ApplicationError(
                "RESULT_PRECISION_EXCEEDED",
                f"«{content.label}» supera 38 dígitos de precisión.",
                422,
            )
        return text

    ordered = sorted(groups.items(), key=lambda item: [sort_component(v) for v in item[1]["sort"]])
    dimensions = [
        ResultColumn(
            key=f"d{i}",
            column_id=column,
            name=headers[index[column]],
            technical_type=kinds[column],
        )
        for i, column in enumerate(parameters.dimensions)
    ]
    if parameters.time_grain is not None and time_column is not None:
        dimensions.append(
            ResultColumn(
                key="period",
                column_id=time_column,
                name=headers[index[time_column]],
                technical_type="date",
                time_grain=parameters.time_grain,
            )
        )
    result_rows: list[ResultRow] = []
    for group, info in ordered:
        components = info["components"]
        row = info["row"]
        key: dict[str, Any] = {
            "dimensions": [
                {"column_id": str(column), "value": components[i]}
                for i, column in enumerate(parameters.dimensions)
            ],
            "period": components[len(dims)] if parameters.time_grain is not None else None,
        }
        labels: dict[str, str | None] = {
            f"d{i}": MISSING_LABEL
            if row[d] is None
            else display_cell(
                row[d], kinds[parameters.dimensions[i]], params[parameters.dimensions[i]]
            )
            for i, d in enumerate(dims)
        }
        if parameters.time_grain is not None and time_position is not None:
            day = row[time_position]
            labels["period"] = (
                MISSING_LABEL if day is None else period(day, parameters.time_grain)[1]
            )
        values = {f"m{n}": value_of(group, n, metric) for n, metric in enumerate(metrics)}
        evidence = {
            f"m{n}": evidence_reference(scope, metric, key)[0] for n, metric in enumerate(metrics)
        }
        result_rows.append(ResultRow(key=key, labels=labels, values=values, evidence=evidence))
    return AnalysisResult(
        scope=scope,
        avg_scale=parameters.avg_scale,
        dimensions=dimensions,
        metrics=definitions,
        rows=result_rows,
        row_count=len(result_rows),
    )


def evidence_payload(
    scope: EvidenceScope, metric: Metric, row_key: dict[str, Any]
) -> dict[str, Any]:
    return {
        "execution_id": str(scope.execution_id),
        "step_id": scope.step_id,
        "slot": scope.slot,
        "input": scope.input.model_dump(mode="json"),
        "semantic_ref": scope.semantic_ref,
        "metric": metric.reference.model_dump(mode="json"),
        "metric_filters": [f.model_dump(mode="json") for f in metric.content.filters],
        "query_filters": [f.model_dump(mode="json") for f in scope.query_filters],
        "time_grain": scope.time_grain,
        "time_range": scope.time_range.model_dump(mode="json") if scope.time_range else None,
        "row_key": row_key,
        "cell": "value",
    }


def evidence_reference(
    scope: EvidenceScope, metric: Metric, row_key: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """`evidence_id` = hash canónico (dominio `evidence`) de la dirección completa de la cifra."""
    payload = evidence_payload(scope, metric, row_key)
    return digest("evidence", payload), payload
