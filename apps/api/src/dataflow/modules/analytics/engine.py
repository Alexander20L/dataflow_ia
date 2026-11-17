"""Motor de analytics.query@1, @2 y @3 (subproceso aislado, sin base de datos).

Polars lee la tabla publicada; la agregación se calcula en Python con aritmética exacta
(`int` y `Decimal`), porque la media de Polars sobre decimales devuelve un float. Sumas con la
escala de la columna, media cuantizada a `avg_scale` con HALF_EVEN, nulos excluidos y contados,
grupos con valor nulo explícitos y orden estable por todas las dimensiones.

@2 calcula el periodo consultado exactamente como @1 y, para cada comparación, hace una segunda
pasada sin el filtro de periodo, limitada a los periodos base que hacen falta.

@3 (11E) es @2 más dos clases de métrica: `sum_product` (Σ medida × segunda medida por fila,
escala = suma de escalas) y la medida semi-aditiva `last_snapshot` (sólo las filas del último
corte de cada periodo, común a todos los grupos; nunca se suman cortes de fechas distintas).
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal, cast
from uuid import UUID

from dataflow.modules.analytics.contracts import (
    MISSING,
    SHAREABLE,
    AnalysisResult,
    AnalysisResultV2,
    AnalysisResultV3,
    BaseCounts,
    ChangeStatus,
    ComparisonCell,
    EvidenceScope,
    Filter,
    MetricContent,
    MetricCounts,
    MetricDefinition,
    MetricDefinitionV2,
    MetricDefinitionV3,
    MetricReference,
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
    RankCell,
    RankingPartition,
    RankingSummary,
    ResultColumn,
    ResultRow,
    ResultRowV2,
    ResultRowV3,
    ShareCell,
    ShareTotal,
    SnapshotCounts,
)
from dataflow.modules.analytics.domain import parse_value
from dataflow.modules.analytics.periods import ComparisonKind, TimeGrain, period, shift
from dataflow.platform.canonical import digest
from dataflow.platform.data_types import MAX_DECIMAL_PRECISION, DataType
from dataflow.platform.decimal_context import exact_context
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


def group_id(components: list[Any]) -> str:
    return json.dumps(components, sort_keys=True)


def check_precision(text: str, label: str) -> str:
    if len(text.lstrip("-").replace(".", "")) > MAX_DECIMAL_PRECISION:
        raise ApplicationError(
            "RESULT_PRECISION_EXCEEDED", f"«{label}» supera 38 dígitos de precisión.", 422
        )
    return text


# --- Pasos comunes de @1 y @2 --------------------------------------------------------------


@dataclass
class Table:
    headers: list[str]
    rows: Sequence[Sequence[Any]]
    index: dict[UUID, int]
    kinds: dict[UUID, DataType]
    params: dict[UUID, dict[str, Any]]

    def position(self, column: UUID) -> int:
        if column not in self.index:
            raise ApplicationError("UNKNOWN_COLUMN", "Una columna no existe en la tabla.", 422)
        return self.index[column]

    def accepted(self, row: Sequence[Any], filters: list[Filter]) -> bool:
        return all(
            matches(row[self.position(f.column_id)], f, self.kinds[f.column_id]) for f in filters
        )


def load_table(
    headers: list[str], rows: Sequence[Sequence[Any]], columns: list[dict[str, Any]]
) -> Table:
    if [str(c["name"]) for c in columns] != headers:
        raise ApplicationError("SCHEMA_MISMATCH", "El esquema no coincide con la tabla.", 409)
    return Table(
        headers,
        rows,
        {UUID(str(c["id"])): position for position, c in enumerate(columns)},
        {UUID(str(c["id"])): cast(DataType, c.get("technical_type", "string")) for c in columns},
        {UUID(str(c["id"])): dict(c.get("type_parameters", {})) for c in columns},
    )


def resolve_time_column(
    table: Table, metrics: list[Metric], parameters: QueryParameters
) -> UUID | None:
    if parameters.time_grain is None and parameters.time_range is None:
        return None
    time_columns = {m.content.time_column_id for m in metrics}
    if len(time_columns) != 1 or None in time_columns:
        raise ApplicationError(
            "TIME_COLUMN_MISMATCH",
            "Todas las métricas deben declarar la misma columna temporal.",
            422,
        )
    time_column = next(iter(time_columns))
    assert time_column is not None
    if table.kinds[time_column] != "date":
        raise ApplicationError("COLUMN_TYPE_MISMATCH", "La columna temporal no es fecha.", 422)
    return time_column


def current_filters(parameters: QueryParameters, time_column: UUID | None) -> list[Filter]:
    """Filtros del periodo consultado: los de la consulta y el rango como `gte`/`lte`."""
    query_filters = list(parameters.filters)
    if parameters.time_range is not None and time_column is not None:
        bounds = parameters.time_range
        if bounds.start:
            query_filters.append(
                Filter(column_id=time_column, operator="gte", values=[bounds.start])
            )
        if bounds.end:
            query_filters.append(Filter(column_id=time_column, operator="lte", values=[bounds.end]))
    return query_filters


@dataclass
class Tally:
    filtered: int = 0
    outside: int = 0
    nulls: int = 0
    superseded: int = 0  # @3: filas de fechas anteriores al último corte de su periodo


@dataclass
class Grouped:
    groups: dict[str, dict[str, Any]]
    accumulators: dict[tuple[str, str], Accumulator]
    tallies: list[Tally]
    # @3: (partición, métrica) → fecha del último corte. Partición: el periodo de la fila
    # (`partition_key`) o todo el resultado si no se agrupa por tiempo.
    cuts: dict[tuple[str, int], date] = field(default_factory=dict)


def partition_key(day: date, grain: TimeGrain | None) -> str:
    """Partición del último corte: el periodo de la fila o todo el resultado."""
    if grain is None:
        return "null"
    return json.dumps({"grain": grain, "start": period(day, grain)[0].isoformat()}, sort_keys=True)


def require_query_v3(metrics: list[Metric], version: int) -> None:
    """@1 y @2 no cambian: rechazan las métricas que sólo calcula @3."""
    for metric in metrics:
        if metric.content.requires_query_v3:
            raise ApplicationError(
                "METRIC_UNSUPPORTED",
                f"«{metric.content.label}» usa sum_product o el último corte: se calcula con "
                f"analytics.query@3 (esta consulta es @{version}).",
                422,
            )


def aggregate(
    table: Table,
    metrics: list[Metric],
    parameters: QueryParameters,
    time_column: UUID | None,
    query_filters: list[Filter],
    in_period: Callable[[date], bool] | None = None,
) -> Grouped:
    # Las sumas de decimales se acumulan en el contexto exacto: con el de Python (28 dígitos)
    # un total de Decimal(38, s) se redondeaba sin aviso.
    with exact_context():
        return accumulate(table, metrics, parameters, time_column, query_filters, in_period)


def accumulate(
    table: Table,
    metrics: list[Metric],
    parameters: QueryParameters,
    time_column: UUID | None,
    query_filters: list[Filter],
    in_period: Callable[[date], bool] | None = None,
) -> Grouped:
    """Agrupa y acumula. Orden de exclusión por fila y métrica: filtros (consulta y métrica),
    periodo base (`in_period`, sólo en la base de una comparación) y nulos de la medida."""
    rows = table.rows
    dims = [table.position(column) for column in parameters.dimensions]
    time_position = table.position(time_column) if time_column is not None else None
    groups: dict[str, dict[str, Any]] = {}
    accumulators: dict[tuple[str, str], Accumulator] = {}
    tallies: list[Tally] = []
    cuts: dict[tuple[str, int], date] = {}
    base = [table.accepted(row, query_filters) for row in rows]

    for number, metric in enumerate(metrics):
        key_name = f"m{number}"
        content = metric.content
        measure = table.position(content.measure_column_id)
        measure_type = table.kinds[content.measure_column_id]
        second = (
            None
            if content.second_measure_column_id is None
            else table.position(content.second_measure_column_id)
        )
        snapshot_position: int | None = None
        if content.semi_additive is not None:
            assert content.time_column_id is not None
            snapshot_position = table.position(content.time_column_id)
            if table.kinds[content.time_column_id] != "date":
                raise ApplicationError(
                    "COLUMN_TYPE_MISMATCH", "La columna del corte no es fecha.", 422
                )
        tally = Tally()
        tallies.append(tally)
        candidates: list[tuple[Sequence[Any], Any]] = []
        for row, keep in zip(rows, base, strict=True):
            if not (keep and table.accepted(row, content.filters)):
                tally.filtered += 1
                continue
            if in_period is not None:
                assert time_position is not None
                when = row[time_position]
                if when is None or not in_period(when):
                    tally.outside += 1
                    continue
            value = row[measure]
            if second is not None:
                # sum_product: un nulo en cualquiera de las dos medidas excluye la fila; el
                # producto es exacto (contexto de `aggregate`).
                factor = row[second]
                value = None if value is None or factor is None else value * factor
            if value is None or (snapshot_position is not None and row[snapshot_position] is None):
                # El último corte necesita la fecha: una fila sin fecha no pertenece a ninguno.
                tally.nulls += 1
                continue
            candidates.append((row, value))
        if snapshot_position is not None:
            # Último corte de cada periodo, común a todos los grupos de ese periodo.
            for row, _ in candidates:
                day = row[snapshot_position]
                cut = (partition_key(day, parameters.time_grain), number)
                if cut not in cuts or day > cuts[cut]:
                    cuts[cut] = day
        for row, value in candidates:
            components: list[Any] = [
                canonical_key(
                    row[d],
                    table.kinds[parameters.dimensions[i]],
                    table.params[parameters.dimensions[i]],
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
                    start, _ = period(day, parameters.time_grain)
                    components.append({"grain": parameters.time_grain, "start": start.isoformat()})
                    sort_values.append(start)
            group = group_id(components)
            if group not in groups:
                groups[group] = {"components": components, "sort": sort_values, "row": row}
            if snapshot_position is not None:
                day = row[snapshot_position]
                if day != cuts[(partition_key(day, parameters.time_grain), number)]:
                    # Corte anterior: la fila está incluida y el grupo existe, pero el valor
                    # sólo suma el último corte; un grupo sin filas en él vale nulo, no 0.
                    tally.superseded += 1
                    continue
            acc = accumulators.setdefault((group, key_name), Accumulator())
            acc.count += 1
            if content.aggregation in {"sum", "avg", "sum_product"}:
                acc.total += value
            elif content.aggregation in {"min", "max"}:
                acc.minimum = value if acc.minimum is None else min(acc.minimum, value)
                acc.maximum = value if acc.maximum is None else max(acc.maximum, value)
            elif content.aggregation == "count_distinct":
                acc.distinct.add(
                    json.dumps(
                        canonical_cell(value, measure_type, table.params[content.measure_column_id])
                    )
                )
    return Grouped(groups, accumulators, tallies, cuts)


def column_scale(table: Table, column: UUID) -> int:
    """Escala de una columna numérica: la del decimal o 0 para enteros."""
    if table.kinds[column] == "decimal":
        return int(table.params[column].get("scale") or 0)
    return 0


def result_scale(table: Table, metric: Metric, avg_scale: int) -> int | None:
    content = metric.content
    if content.aggregation == "avg":
        return avg_scale
    if content.aggregation == "sum_product":
        assert content.second_measure_column_id is not None
        columns = (content.measure_column_id, content.second_measure_column_id)
        if all(table.kinds[column] == "integer" for column in columns):
            return None
        # Producto exacto: la escala del resultado es la suma de las escalas.
        return sum(column_scale(table, column) for column in columns)
    if table.kinds[content.measure_column_id] == "decimal":
        scale = table.params[content.measure_column_id].get("scale")
        return None if scale is None else int(scale)
    return None


def definition_fields(
    table: Table, metric: Metric, number: int, tally: Tally, avg_scale: int
) -> dict[str, Any]:
    content = metric.content
    included = len(table.rows) - tally.filtered - tally.nulls
    return {
        "key": f"m{number}",
        "revision_id": metric.reference.revision_id,
        "revision": metric.revision,
        "content_sha256": metric.reference.content_sha256,
        "label": content.label,
        "aggregation": content.aggregation,
        "measure_column_id": content.measure_column_id,
        "measure_column": table.headers[table.position(content.measure_column_id)],
        "time_column_id": content.time_column_id,
        "filters": content.filters,
        "null_policy": content.null_policy,
        "unit": metric.unit,
        "currency": metric.currency,
        "scale": result_scale(table, metric, avg_scale),
        "counts": MetricCounts(
            input_rows=len(table.rows),
            excluded_by_filters=tally.filtered,
            excluded_by_nulls=tally.nulls,
            included_rows=included,
        ),
    }


def check_budget(grouped: Grouped, parameters: QueryParameters) -> None:
    if len(grouped.groups) > parameters.max_result_rows:
        raise ApplicationError(
            "RESULT_TOO_LARGE",
            f"El resultado tendría {len(grouped.groups)} filas y el límite de la consulta es "
            f"{parameters.max_result_rows}. Añade filtros o usa menos dimensiones.",
            422,
        )


def metric_value(
    table: Table, grouped: Grouped, group: str, number: int, metric: Metric, avg_scale: int
) -> str | None:
    content = metric.content
    acc = grouped.accumulators.get((group, f"m{number}"))
    if content.aggregation in {"count", "count_distinct"}:
        if acc is None:
            return "0"
        return str(acc.count if content.aggregation == "count" else len(acc.distinct))
    if acc is None:
        return None  # ninguna fila de esta métrica en el grupo: no es 0
    kind = table.kinds[content.measure_column_id]
    parameters_of = table.params[content.measure_column_id]
    if content.aggregation == "avg":
        with exact_context():
            mean = Decimal(acc.total) / Decimal(acc.count)
            text = canonical_decimal(mean, avg_scale)
    elif content.aggregation == "sum":
        text = (
            str(int(acc.total))
            if kind == "integer"
            else canonical_decimal(Decimal(acc.total), int(parameters_of["scale"]))
        )
    elif content.aggregation == "sum_product":
        scale = result_scale(table, metric, avg_scale)
        total = Decimal(acc.total)
        text = str(int(total)) if scale is None else canonical_decimal(total, scale)
    else:
        chosen = acc.minimum if content.aggregation == "min" else acc.maximum
        text = display_cell(chosen, kind, parameters_of) or ""
    return check_precision(text, content.label)


def result_dimensions(
    table: Table, parameters: QueryParameters, time_column: UUID | None
) -> list[ResultColumn]:
    dimensions = [
        ResultColumn(
            key=f"d{i}",
            column_id=column,
            name=table.headers[table.index[column]],
            technical_type=table.kinds[column],
        )
        for i, column in enumerate(parameters.dimensions)
    ]
    if parameters.time_grain is not None and time_column is not None:
        dimensions.append(
            ResultColumn(
                key="period",
                column_id=time_column,
                name=table.headers[table.index[time_column]],
                technical_type="date",
                time_grain=parameters.time_grain,
            )
        )
    return dimensions


@dataclass
class RowParts:
    group: str
    components: list[Any]
    key: dict[str, Any]
    labels: dict[str, str | None]
    values: dict[str, str | None]
    evidence: dict[str, str]


def row_parts(
    table: Table,
    grouped: Grouped,
    metrics: list[Metric],
    parameters: QueryParameters,
    time_column: UUID | None,
    scope: EvidenceScope,
    with_evidence: bool = True,
) -> list[RowParts]:
    """Filas en orden estable: dimensiones en el orden declarado y después el periodo, con
    valores tipados y nulos al final. Sin evidencia, se añade después sólo a las visibles."""
    dims = [table.position(column) for column in parameters.dimensions]
    time_position = table.position(time_column) if time_column is not None else None
    ordered = sorted(
        grouped.groups.items(), key=lambda item: [sort_component(v) for v in item[1]["sort"]]
    )
    parts: list[RowParts] = []
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
                row[d],
                table.kinds[parameters.dimensions[i]],
                table.params[parameters.dimensions[i]],
            )
            for i, d in enumerate(dims)
        }
        if parameters.time_grain is not None and time_position is not None:
            day = row[time_position]
            labels["period"] = (
                MISSING_LABEL if day is None else period(day, parameters.time_grain)[1]
            )
        values = {
            f"m{n}": metric_value(table, grouped, group, n, metric, parameters.avg_scale)
            for n, metric in enumerate(metrics)
        }
        part = RowParts(group, components, key, labels, values, {})
        if with_evidence:
            attach_evidence(part, metrics, scope)
        parts.append(part)
    return parts


def attach_evidence(part: RowParts, metrics: list[Metric], scope: EvidenceScope) -> None:
    part.evidence = {
        f"m{n}": evidence_reference(scope, metric, part.key)[0] for n, metric in enumerate(metrics)
    }


# --- analytics.query@1 ---------------------------------------------------------------------


def run_query(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    metrics: list[Metric],
    parameters: QueryParameters,
    scope: EvidenceScope,
) -> AnalysisResult:
    require_query_v3(metrics, 1)
    table = load_table(headers, rows, columns)
    time_column = resolve_time_column(table, metrics, parameters)
    grouped = aggregate(
        table, metrics, parameters, time_column, current_filters(parameters, time_column)
    )
    definitions = [
        MetricDefinition(**definition_fields(table, m, n, grouped.tallies[n], parameters.avg_scale))
        for n, m in enumerate(metrics)
    ]
    check_budget(grouped, parameters)
    parts = row_parts(table, grouped, metrics, parameters, time_column, scope)
    return AnalysisResult(
        scope=scope,
        avg_scale=parameters.avg_scale,
        dimensions=result_dimensions(table, parameters, time_column),
        metrics=definitions,
        rows=[
            ResultRow(key=p.key, labels=p.labels, values=p.values, evidence=p.evidence)
            for p in parts
        ],
        row_count=len(parts),
    )


# --- analytics.query@2 ---------------------------------------------------------------------


@dataclass
class Base:
    """Segunda pasada de una comparación: periodo base de cada grupo y sus acumulados."""

    kind: ComparisonKind
    starts: dict[str, date | None]  # grupo actual → inicio del periodo base (None: sin él)
    grouped: Grouped


def comparison_base(
    table: Table,
    metrics: list[Metric],
    parameters: QueryParametersV2,
    time_column: UUID,
    grouped: Grouped,
    kind: ComparisonKind,
) -> Base:
    """La base no aplica el periodo consultado (sus filas están fuera de él): aplica los
    filtros de la consulta que no son de periodo y los de la métrica, y sólo acepta filas de
    los periodos base que necesita algún grupo del resultado."""
    grain = parameters.time_grain
    assert grain is not None
    starts: dict[str, date | None] = {}
    for group, info in grouped.groups.items():
        current = info["components"][len(parameters.dimensions)]
        starts[group] = (
            None if current == MISSING else shift(date.fromisoformat(current["start"]), grain, kind)
        )
    needed = {start for start in starts.values() if start is not None}
    based = aggregate(
        table,
        metrics,
        parameters,
        time_column,
        list(parameters.filters),
        in_period=lambda day: period(day, grain)[0] in needed,
    )
    return Base(kind, starts, based)


def change_of(
    current: str | None, base: str | None, scale: int | None, change_scale: int, label: str
) -> tuple[str | None, str | None, ChangeStatus]:
    """Variación absoluta sobre las cifras mostradas (ya cuantizadas) y porcentual respecto a
    |base|, HALF_EVEN con `change_scale`. Base 0: hay variación absoluta pero no porcentual."""
    if current is None:
        return None, None, "current_missing"
    if base is None:
        return None, None, "base_missing"
    with exact_context():
        difference = Decimal(current) - Decimal(base)
    change = check_precision(
        str(int(difference)) if scale is None else canonical_decimal(difference, scale), label
    )
    if Decimal(base) == 0:
        return change, None, "base_zero"
    with exact_context():
        ratio = difference / abs(Decimal(base)) * 100
    return change, check_precision(canonical_decimal(ratio, change_scale), label), "available"


ShareStatus = Literal["available", "total_zero", "value_missing"]


def partition_of(part: RowParts) -> str:
    """Partición de participación y ranking: el periodo del grupo (o todo el resultado)."""
    return json.dumps(part.key["period"], sort_keys=True)


def partition_order(period_key: dict[str, Any] | None) -> tuple[int, str]:
    if period_key is None:
        return (0, "")
    return (1, "") if period_key == MISSING else (0, str(period_key["start"]))


def partitions(parts: list[RowParts]) -> list[list[RowParts]]:
    """Grupos por partición, en orden de periodo (sin fecha al final) y, dentro, en el orden
    estable de las filas (dimensiones en el orden declarado)."""
    split: dict[str, list[RowParts]] = {}
    for part in parts:
        split.setdefault(partition_of(part), []).append(part)
    return sorted(split.values(), key=lambda items: partition_order(items[0].key["period"]))


def compute_shares(
    parts: list[RowParts],
    metrics: list[Metric],
    parameters: QueryParametersV2,
    fields: list[dict[str, Any]],
    shareable: frozenset[str] = SHAREABLE,
) -> tuple[dict[tuple[str, int], tuple[str | None, ShareStatus]], list[ShareTotal]]:
    """Participación de cada grupo sobre el total de su partición, calculado sobre todos los
    grupos (antes del top N y del presupuesto). Cada porcentaje se redondea por separado con
    `share_scale` (HALF_EVEN); la tolerancia de la suma se declara por partición."""
    wanted = set(parameters.share_of_total)
    cells: dict[tuple[str, int], tuple[str | None, ShareStatus]] = {}
    totals: list[ShareTotal] = []
    scale = parameters.share_scale
    for number, metric in enumerate(metrics):
        if metric.reference.revision_id not in wanted:
            continue
        content = metric.content
        if content.aggregation not in shareable:
            raise ApplicationError(
                "SHARE_NOT_ADDITIVE",
                f"La participación sólo se calcula para sumas y conteos; «{content.label}» "
                f"usa {content.aggregation}.",
                422,
            )
        key = f"m{number}"
        for items in partitions(parts):
            values = [Decimal(v) for p in items if (v := p.values[key]) is not None]
            with exact_context():
                total = sum(values, Decimal(0))
            result_scale_of = fields[number]["scale"]
            total_text = check_precision(
                str(int(total))
                if result_scale_of is None
                else canonical_decimal(total, result_scale_of),
                content.label,
            )
            totals.append(
                ShareTotal(
                    metric=key,
                    period=items[0].key["period"],
                    total=total_text,
                    groups=len(values),
                    tolerance=canonical_decimal(
                        Decimal(len(values)) * Decimal(5).scaleb(-(scale + 1)), scale + 1
                    ),
                    mixed_signs=any(v < 0 for v in values),
                )
            )
            for part in items:
                text = part.values[key]
                if text is None:
                    cells[(part.group, number)] = (None, "value_missing")
                elif total == 0:
                    cells[(part.group, number)] = (None, "total_zero")
                else:
                    with exact_context():
                        ratio = Decimal(text) / total * 100
                    cells[(part.group, number)] = (
                        check_precision(canonical_decimal(ratio, scale), content.label),
                        "available",
                    )
    return cells, totals


def rank_parts(
    parts: list[RowParts], metrics: list[Metric], parameters: QueryParametersV2
) -> tuple[list[tuple[RowParts, tuple[int, bool] | None]], RankingSummary]:
    """Top N por partición. Posiciones 1, 2, 3 sin empates compartidos: la ordenación es
    estable, así que dos valores iguales conservan el orden por dimensiones y la segunda fila
    se marca `tied_with_previous`. Los grupos sin valor no tienen posición y se ocultan."""
    ranking = parameters.ranking
    assert ranking is not None
    number = next(
        n for n, m in enumerate(metrics) if m.reference.revision_id == ranking.metric_revision_id
    )
    key = f"m{number}"
    shown: list[tuple[RowParts, tuple[int, bool] | None]] = []
    summaries: list[RankingPartition] = []
    for items in partitions(parts):
        candidates = [p for p in items if p.values[key] is not None]
        ordered = sorted(
            candidates,
            key=lambda p: Decimal(cast(str, p.values[key])),
            reverse=ranking.direction == "desc",
        )
        top = ordered[: ranking.top_n]
        previous: Decimal | None = None
        for position, part in enumerate(top, start=1):
            value = Decimal(cast(str, part.values[key]))
            shown.append((part, (position, previous is not None and value == previous)))
            previous = value
        summaries.append(
            RankingPartition(
                period=items[0].key["period"],
                groups=len(items),
                ranked=len(candidates),
                shown=len(top),
                hidden=len(items) - len(top),
            )
        )
    summary = RankingSummary(
        metric=key,
        direction=ranking.direction,
        top_n=ranking.top_n,
        partitions=summaries,
        hidden_groups=sum(s.hidden for s in summaries),
    )
    return shown, summary


def run_query_v2(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    metrics: list[Metric],
    parameters: QueryParametersV2,
    scope: EvidenceScope,
) -> AnalysisResultV2:
    require_query_v3(metrics, 2)
    result = run_extended(headers, rows, columns, metrics, parameters, scope, 2)
    assert isinstance(result, AnalysisResultV2)
    return result


# Agregaciones que se pueden sumar entre grupos en @3: las de @2 y `sum_product`.
SHAREABLE_V3: frozenset[str] = SHAREABLE | {"sum_product"}


def run_query_v3(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    metrics: list[Metric],
    parameters: QueryParametersV3,
    scope: EvidenceScope,
) -> AnalysisResultV3:
    """@2 con las métricas `sum_product` y `last_snapshot`. Con las métricas de @2 calcula las
    mismas cifras, conteos y `evidence_id`."""
    result = run_extended(headers, rows, columns, metrics, parameters, scope, 3)
    assert isinstance(result, AnalysisResultV3)
    return result


def snapshot_fields(
    table: Table, metric: Metric, tally: Tally, bases: list["Base"], number: int
) -> dict[str, Any]:
    """Campos de @3 en la definición: segunda medida, último corte y sus filas superadas."""
    content = metric.content
    second = content.second_measure_column_id
    return {
        "second_measure_column_id": second,
        "second_measure_column": None if second is None else table.headers[table.position(second)],
        "semi_additive": content.semi_additive,
        "snapshot": None
        if content.semi_additive is None
        else SnapshotCounts(
            superseded_rows=tally.superseded,
            base_superseded_rows={
                base.kind: base.grouped.tallies[number].superseded for base in bases
            },
        ),
    }


def row_snapshots(grouped: Grouped, part: RowParts, metrics: list[Metric]) -> dict[str, str]:
    """Fecha del corte usado en el periodo de la fila, por métrica semi-aditiva."""
    snapshots: dict[str, str] = {}
    for number, metric in enumerate(metrics):
        if metric.content.semi_additive is None:
            continue
        cut = grouped.cuts.get((partition_of(part), number))
        if cut is not None:
            snapshots[f"m{number}"] = cut.isoformat()
    return snapshots


def run_extended(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    metrics: list[Metric],
    parameters: QueryParametersV2,
    scope: EvidenceScope,
    version: Literal[2, 3],
) -> AnalysisResultV2 | AnalysisResultV3:
    table = load_table(headers, rows, columns)
    time_column = resolve_time_column(table, metrics, parameters)
    grouped = aggregate(
        table, metrics, parameters, time_column, current_filters(parameters, time_column)
    )
    fields = [
        definition_fields(table, m, n, grouped.tallies[n], parameters.avg_scale)
        for n, m in enumerate(metrics)
    ]
    if parameters.ranking is None:
        check_budget(grouped, parameters)
    # Todas las filas (sin evidencia): la participación y el ranking se calculan sobre todos
    # los grupos, antes de recortar.
    every = row_parts(table, grouped, metrics, parameters, time_column, scope, False)
    shares, share_totals = compute_shares(
        every, metrics, parameters, fields, SHAREABLE_V3 if version == 3 else SHAREABLE
    )
    summary: RankingSummary | None = None
    if parameters.ranking is not None:
        ranked, summary = rank_parts(every, metrics, parameters)
        # Decisión 7B-3: el presupuesto se aplica después del top N.
        if len(ranked) > parameters.max_result_rows:
            raise ApplicationError(
                "RESULT_TOO_LARGE",
                f"El resultado tendría {len(ranked)} filas tras el top N y el límite de la "
                f"consulta es {parameters.max_result_rows}. Reduce el top N o añade filtros.",
                422,
            )
    else:
        ranked = [(part, None) for part in every]
    for part, _ in ranked:
        attach_evidence(part, metrics, scope)
    bases: list[Base] = []
    if parameters.comparisons:
        assert time_column is not None and parameters.time_grain is not None
        bases = [
            comparison_base(table, metrics, parameters, time_column, grouped, kind)
            for kind in parameters.comparisons
        ]
    definition_model = MetricDefinitionV3 if version == 3 else MetricDefinitionV2
    definitions = [
        definition_model(
            **fields[n],
            **(
                snapshot_fields(table, metrics[n], grouped.tallies[n], bases, n)
                if version == 3
                else {}
            ),
            base_counts={
                base.kind: BaseCounts(
                    input_rows=len(rows),
                    excluded_by_filters=base.grouped.tallies[n].filtered,
                    outside_base_periods=base.grouped.tallies[n].outside,
                    excluded_by_nulls=base.grouped.tallies[n].nulls,
                    included_rows=len(rows)
                    - base.grouped.tallies[n].filtered
                    - base.grouped.tallies[n].outside
                    - base.grouped.tallies[n].nulls,
                )
                for base in bases
            },
        )
        for n in range(len(metrics))
    ]
    result_rows: list[ResultRowV2 | ResultRowV3] = []
    for part, position in ranked:
        comparisons: dict[str, dict[ComparisonKind, ComparisonCell]] = {}
        share: dict[str, ShareCell] = {}
        for n, metric in enumerate(metrics):
            cells: dict[ComparisonKind, ComparisonCell] = {}
            for base in bases:
                cells[base.kind] = comparison_cell(
                    table, base, part, n, metric, parameters, scope, fields[n]["scale"]
                )
            if cells:
                comparisons[f"m{n}"] = cells
            if (part.group, n) in shares:
                value, status = shares[(part.group, n)]
                share[f"m{n}"] = ShareCell(
                    value=value,
                    status=status,
                    evidence=cell_evidence(
                        scope,
                        metric,
                        part.key,
                        "share_of_total",
                        share_detail(parameters.share_scale),
                    ),
                )
        rank: RankCell | None = None
        if position is not None and parameters.ranking is not None:
            number, tied = position
            by = next(
                m
                for m in metrics
                if m.reference.revision_id == parameters.ranking.metric_revision_id
            )
            rank = RankCell(
                position=number,
                tied_with_previous=tied,
                evidence=cell_evidence(
                    scope,
                    by,
                    part.key,
                    "rank",
                    rank_detail(parameters.ranking.direction, parameters.ranking.top_n, tied),
                ),
            )
        cells_of_row: dict[str, Any] = {
            "key": part.key,
            "labels": part.labels,
            "values": part.values,
            "evidence": part.evidence,
            "comparisons": comparisons,
            "share": share,
            "rank": rank,
        }
        result_rows.append(
            ResultRowV3(**cells_of_row, snapshots=row_snapshots(grouped, part, metrics))
            if version == 3
            else ResultRowV2(**cells_of_row)
        )
    common: dict[str, Any] = {
        "scope": scope,
        "avg_scale": parameters.avg_scale,
        "comparisons": parameters.comparisons,
        "change_scale": parameters.change_scale,
        "share_scale": parameters.share_scale,
        "shares": share_totals,
        "ranking": summary,
        "dimensions": result_dimensions(table, parameters, time_column),
        "metrics": definitions,
        "rows": result_rows,
        "row_count": len(result_rows),
    }
    if version == 3:
        return AnalysisResultV3(**common)
    return AnalysisResultV2(**common)


def comparison_cell(
    table: Table,
    base: Base,
    part: RowParts,
    number: int,
    metric: Metric,
    parameters: QueryParametersV2,
    scope: EvidenceScope,
    scale: int | None,
) -> ComparisonCell:
    grain = parameters.time_grain
    assert grain is not None
    current_period = part.components[len(parameters.dimensions)]
    start = base.starts[part.group]
    base_period: dict[str, str] | None = None
    base_label: str | None = None
    value: str | None = None
    if current_period == MISSING:
        status: Any = "missing_period"
    elif start is None:
        status = "no_counterpart"
    else:
        base_period = {"grain": grain, "start": start.isoformat()}
        base_label = period(start, grain)[1]
        base_group = group_id([*part.components[: len(parameters.dimensions)], base_period])
        # El grupo base existe si alguna métrica tiene filas en él (regla de @1); si no, nulo.
        if base_group in base.grouped.groups:
            value = metric_value(
                table, base.grouped, base_group, number, metric, parameters.avg_scale
            )
        status = "available" if value is not None else "no_base_data"
    change, change_pct, change_status = change_of(
        part.values[f"m{number}"], value, scale, parameters.change_scale, metric.content.label
    )
    detail = comparison_detail(base.kind, base_period)
    return ComparisonCell(
        base_period=base_period,
        base_label=base_label,
        base=value,
        base_status=status,
        change=change,
        change_pct=change_pct,
        change_status=change_status,
        evidence={
            "base": cell_evidence(scope, metric, part.key, base.kind, detail),
            "change": cell_evidence(scope, metric, part.key, "change", detail),
            "change_pct": cell_evidence(
                scope,
                metric,
                part.key,
                "change_pct",
                change_pct_detail(base.kind, base_period, parameters.change_scale),
            ),
        },
    )


# --- Evidencia ------------------------------------------------------------------------------


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


def comparison_detail(kind: str, base_period: dict[str, str] | None) -> dict[str, Any]:
    """Detalle de las celdas de una comparación (base y variación absoluta)."""
    return {"comparison": kind, "base_period": base_period}


def change_pct_detail(
    kind: str, base_period: dict[str, str] | None, change_scale: int
) -> dict[str, Any]:
    return {**comparison_detail(kind, base_period), "change_scale": change_scale}


def share_detail(share_scale: int) -> dict[str, Any]:
    return {"share_scale": share_scale}


def rank_detail(direction: str, top_n: int, tied: bool) -> dict[str, Any]:
    """El indicador de empate forma parte de la dirección de la posición."""
    return {"direction": direction, "top_n": top_n, "tied_with_previous": tied}


def cell_reference(
    scope: EvidenceScope,
    metric: Metric,
    row_key: dict[str, Any],
    cell: str,
    detail: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Dirección de una cifra derivada (comparación, variación…): la de `value` con otra
    `cell` y su detalle. La dirección de `value` no cambia (misma fórmula que @1)."""
    payload = {**evidence_payload(scope, metric, row_key), "cell": cell, "detail": detail}
    return digest("evidence", payload), payload


def cell_evidence(
    scope: EvidenceScope,
    metric: Metric,
    row_key: dict[str, Any],
    cell: str,
    detail: dict[str, Any],
) -> str:
    return cell_reference(scope, metric, row_key, cell, detail)[0]
