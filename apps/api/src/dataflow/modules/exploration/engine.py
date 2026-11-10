"""Motor de la exploración (`explore-v1`): calcula una consulta sobre todas las filas.

Sumas, conteos y medianas son exactos (Decimal sobre las celdas canónicas). Promedios y
cocientes se redondean a 6 decimales y las correlaciones a 4; el método lo declara. Las columnas
se leen por nombre exacto con alias neutros; los valores no numéricos de una medida no cuentan.
"""

import hashlib
import io
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from statistics import median

import polars as pl

from dataflow.modules.exploration.contracts import (
    MAX_GROUPS,
    ExploreFigure,
    ExploreQuery,
    ExploreResult,
    ExploreRow,
)
from dataflow.modules.exploration.domain import AGGREGATIONS, title

SIX = Decimal("0.000001")
FOUR = Decimal("0.0001")
MIN_CORRELATION_ROWS = 10


def decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize() if value == value.to_integral() else value, "f")


def evidence(execution: str, key: str, groups: Sequence[str], label: str) -> str:
    raw = "\x1f".join([execution, key, *groups, label])
    return hashlib.sha256(raw.encode()).hexdigest()


def columns(content: bytes, names: Sequence[str]) -> dict[str, list[object]]:
    table = pl.read_parquet(io.BytesIO(content))
    return {name: table.get_column(name).to_list() for name in dict.fromkeys(names)}


def ranks(values: Sequence[Decimal]) -> list[Decimal]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [Decimal(0)] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = Decimal(i + j + 2) / 2
        for k in range(i, j + 1):
            result[order[k]] = average
        i = j + 1
    return result


def spearman(pairs: Sequence[tuple[Decimal, Decimal]]) -> Decimal | None:
    if len(pairs) < MIN_CORRELATION_ROWS:
        return None
    x, y = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    with localcontext() as context:
        context.prec = 40
        n = Decimal(len(pairs))
        mx, my = sum(x) / n, sum(y) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
        vx = sum((a - mx) ** 2 for a in x)
        vy = sum((b - my) ** 2 for b in y)
        if vx == 0 or vy == 0:
            return None
        return (cov / (vx * vy).sqrt()).quantize(FOUR, rounding=ROUND_HALF_EVEN)


def compute(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """Resultado de la consulta o el motivo por el que no se puede calcular."""
    names = [
        *query.dimensions,
        *[m for m in (query.measure, query.measure_b) if m],
        *([query.filter_column] if query.filter_column else []),
    ]
    data = columns(content, names)
    total = len(next(iter(data.values()))) if data else 0
    indices: Sequence[int] = range(total)
    if query.filter_column:
        indices = [i for i in indices if str(data[query.filter_column][i]) == query.filter_value]
        if not indices:
            return f"Ningún registro tiene {query.filter_column} = {query.filter_value}."
    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i in indices:
        labels = tuple(data[d][i] for d in query.dimensions)
        if any(label is None for label in labels):
            continue
        groups[tuple(str(label) for label in labels)].append(i)
    if query.dimensions and not groups:
        return "Ninguna fila tiene valor en las dimensiones pedidas."
    if not query.dimensions:
        groups = {(): list(indices)}

    figures: list[tuple[tuple[str, ...], int, list[tuple[str, Decimal | None]]]] = []
    method = ""
    for labels, members in groups.items():
        if query.kind in {"aggregate", "top", "crosstab"}:
            aggregation = query.aggregation or "count"
            if aggregation == "count":
                value: Decimal | None = Decimal(len(members))
                used = len(members)
                method = "Conteo exacto de registros."
            else:
                assert query.measure
                numbers = [
                    n for n in (decimal(data[query.measure][i]) for i in members) if n is not None
                ]
                used = len(numbers)
                if not numbers:
                    value = None
                elif aggregation == "sum":
                    value = sum(numbers, Decimal(0))
                    method = "Suma exacta de las celdas numéricas."
                elif aggregation == "mean":
                    value = (sum(numbers, Decimal(0)) / len(numbers)).quantize(SIX)
                    method = "Promedio simple, redondeado a 6 decimales."
                else:
                    value = Decimal(median(numbers))
                    method = "Mediana exacta (promedio de los dos centrales si es par)."
            label = AGGREGATIONS[aggregation] + (f" de {query.measure}" if query.measure else "")
            figures.append((labels, used, [(label, value)]))
        elif query.kind == "ratio":
            assert query.measure and query.measure_b
            a = [decimal(data[query.measure][i]) for i in members]
            b = [decimal(data[query.measure_b][i]) for i in members]
            pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
            top = sum((x for x, _ in pairs), Decimal(0))
            bottom = sum((y for _, y in pairs), Decimal(0))
            value = (top / bottom).quantize(SIX) if bottom != 0 else None
            method = "Cociente de sumas sobre filas con ambas medidas, redondeado a 6 decimales."
            figures.append(
                (
                    labels,
                    len(pairs),
                    [
                        (f"Suma de {query.measure}", top),
                        (f"Suma de {query.measure_b}", bottom),
                        (f"{query.measure} / {query.measure_b}", value),
                    ],
                )
            )
        else:  # correlation_by_group
            assert query.measure and query.measure_b
            pairs = [
                (x, y)
                for x, y in (
                    (decimal(data[query.measure][i]), decimal(data[query.measure_b][i]))
                    for i in members
                )
                if x is not None and y is not None
            ]
            value = spearman(pairs)
            method = (
                "Spearman (rangos promedio) dentro de cada grupo con al menos "
                f"{MIN_CORRELATION_ROWS} filas, redondeado a 4 decimales."
            )
            figures.append((labels, len(pairs), [("Spearman", value)]))

    def sort_key(
        item: tuple[tuple[str, ...], int, list[tuple[str, Decimal | None]]],
    ) -> tuple[bool, Decimal, tuple[str, ...]]:
        main = item[2][-1][1]
        return (main is None, -(main or Decimal(0)), item[0])

    figures.sort(key=sort_key)
    if query.kind == "top" and query.limit:
        figures = figures[: query.limit]
    total_groups = len(figures)
    kept = figures[:MAX_GROUPS]
    headers = [*query.dimensions, *[label for label, _ in (kept[0][2] if kept else [])], "Filas"]
    rows = [
        ExploreRow(
            groups=list(labels),
            rows=used,
            figures=[
                ExploreFigure(
                    label=label,
                    value=text(value),
                    evidence_id=evidence(execution, query.key, labels, label),
                )
                for label, value in values
            ],
        )
        for labels, used, values in kept
    ]
    return ExploreResult(
        key=query.key,
        query=query,
        title=title(query),
        method=method,
        columns=headers,
        rows=rows,
        total_groups=total_groups,
        truncated=total_groups > len(kept),
        covered_rows=sum(r.rows for r in rows),
    )
