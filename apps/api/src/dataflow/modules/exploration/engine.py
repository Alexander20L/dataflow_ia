"""Motor de la exploración (`explore-v1` y, desde la Fase 25, `explore-v2`): calcula una
consulta sobre todas las filas.

Sumas, conteos y medianas son exactos (Decimal sobre las celdas canónicas). Promedios y
cocientes se redondean a 6 decimales y las correlaciones a 4; el método lo declara. Las columnas
se leen por nombre exacto con alias neutros; los valores no numéricos de una medida no cuentan.
"""

import hashlib
import io
import re
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from statistics import median

import polars as pl

from dataflow.modules.exploration.contracts import (
    MAX_GROUPS,
    TEMPORAL_KINDS,
    ExploreFigure,
    ExploreQuery,
    ExploreResult,
    ExploreRow,
)
from dataflow.modules.exploration.domain import AGGREGATIONS, title
from dataflow.modules.understanding.public import month_number

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


def row_count(content: bytes) -> int:
    """Registros de la tabla publicada (Fase 25: la base de «registros considerados»)."""
    names = list(pl.read_parquet_schema(io.BytesIO(content)))
    return pl.read_parquet(io.BytesIO(content), columns=names[:1]).height if names else 0


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


def compute(
    content: bytes,
    query: ExploreQuery,
    execution: str,
    period: tuple[str, list[str]] | None = None,
) -> ExploreResult | str:
    """Resultado de la consulta o el motivo por el que no se puede calcular. `period`: tipo y
    columnas del periodo de la comprensión (Fase 25, sólo para las consultas temporales)."""
    if query.kind in TEMPORAL_KINDS:
        return compute_temporal(content, query, execution, period)
    if query.kind == "outliers":
        return compute_outliers(content, query, execution)
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

    return build(query, execution, method, figures)


Figures = list[tuple[tuple[str, ...], int, list[tuple[str, Decimal | None]]]]


def build(
    query: ExploreQuery, execution: str, method: str, figures: Figures, ordered: bool = True
) -> ExploreResult:
    """El resultado con sus evidencias. `ordered`: de mayor a menor por la última cifra (si no,
    se conserva el orden recibido, p. ej. el cronológico)."""

    def sort_key(
        item: tuple[tuple[str, ...], int, list[tuple[str, Decimal | None]]],
    ) -> tuple[bool, Decimal, tuple[str, ...]]:
        main = item[2][-1][1]
        return (main is None, -(main or Decimal(0)), item[0])

    if ordered:
        figures = sorted(figures, key=sort_key)
    if query.kind == "top" and query.limit:
        figures = figures[: query.limit]
    total_groups = len(figures)
    kept = figures[:MAX_GROUPS]
    headers = [
        *(["Periodo"] if query.kind == "evolution" else query.dimensions),
        *[label for label, _ in (kept[0][2] if kept else [])],
        "Filas",
    ]
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


# --- Fase 25 (explore-v2): periodos y valores atípicos -----------------------------------------

DATE = re.compile(r"^(\d{4})-(\d{2})")


def month_of(kind: str, cells: Sequence[object]) -> str | None:
    """Mes «AAAA-MM» de una fila: una fecha o un año y un mes (como en el eje del perfil)."""
    if kind == "date":
        found = DATE.match(str(cells[0])) if cells[0] is not None else None
        return f"{found.group(1)}-{found.group(2)}" if found else None
    year, month = cells
    if year is None or month is None:
        return None
    try:
        number = int(Decimal(str(year)))
    except InvalidOperation:
        return None
    value = month_number(str(month))
    return f"{number:04d}-{value:02d}" if value and 1900 <= number <= 2100 else None


def aggregate(values: Sequence[Decimal], rows: int, aggregation: str) -> Decimal | None:
    if aggregation == "count":
        return Decimal(rows)
    if not values:
        return None
    if aggregation == "sum":
        return sum(values, Decimal(0))
    if aggregation == "mean":
        return (sum(values, Decimal(0)) / len(values)).quantize(SIX)
    return Decimal(median(values))


METHODS = {
    "count": "conteo exacto de registros",
    "sum": "suma exacta de las celdas numéricas",
    "mean": "promedio simple redondeado a 6 decimales",
    "median": "mediana exacta",
}


def span(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{items[0]} a {items[-1]}"


def compute_temporal(
    content: bytes, query: ExploreQuery, execution: str, period: tuple[str, list[str]] | None
) -> ExploreResult | str:
    if period is None:
        return "La tabla no tiene una columna temporal: no se calcula una evolución."
    kind, period_columns = period
    names = [
        *period_columns,
        *query.dimensions,
        *([query.measure] if query.measure else []),
        *([query.filter_column] if query.filter_column else []),
    ]
    data = columns(content, names)
    total = len(next(iter(data.values()))) if data else 0
    aggregation = query.aggregation or ("count" if query.measure is None else "sum")
    label = AGGREGATIONS[aggregation] + (f" de {query.measure}" if query.measure else "")
    # (mes, grupo) -> (valores numéricos, filas)
    cells: dict[tuple[str, tuple[str, ...]], tuple[list[Decimal], list[int]]] = {}
    for i in range(total):
        if query.filter_column and str(data[query.filter_column][i]) != query.filter_value:
            continue
        month = month_of(kind, [data[c][i] for c in period_columns])
        if month is None:
            continue
        labels = tuple(data[d][i] for d in query.dimensions)
        if any(item is None for item in labels):
            continue
        group = tuple(str(item) for item in labels)
        values, members = cells.setdefault((month, group), ([], []))
        members.append(i)
        if query.measure:
            number = decimal(data[query.measure][i])
            if number is not None:
                values.append(number)
    if not cells:
        return "Ninguna fila tiene un periodo reconocible con los filtros pedidos."
    months = sorted({month for month, _ in cells})
    if query.kind == "evolution":
        series: Figures = []
        for month in months:
            values, members = cells.get((month, ()), ([], []))
            used = len(members) if aggregation == "count" else len(values)
            series.append(((month,), used, [(label, aggregate(values, len(members), aggregation))]))
        method = (
            f"Serie mensual ({METHODS[aggregation]}) sobre todas las filas con periodo; los "
            "meses sin registros no aparecen."
        )
        return build(query, execution, method, series, ordered=False)
    window = query.limit or 3
    if len(months) < 2 * window:
        return (
            f"Hacen falta al menos {2 * window} meses con datos para comparar dos ventanas de "
            f"{window}; hay {len(months)}."
        )
    recent, previous = months[-window:], months[-2 * window : -window]
    groups = sorted({group for _, group in cells})

    def pooled(group: tuple[str, ...], window_months: list[str]) -> tuple[list[Decimal], int]:
        values: list[Decimal] = []
        rows = 0
        for month in window_months:
            found = cells.get((month, group))
            if found:
                values.extend(found[0])
                rows += len(found[1])
        return values, rows

    figures: Figures = []
    for group in groups:
        before, before_rows = pooled(group, previous)
        after, after_rows = pooled(group, recent)
        first = aggregate(before, before_rows, aggregation)
        last = aggregate(after, after_rows, aggregation)
        change = last - first if first is not None and last is not None else None
        percent = (
            (change / abs(first) * 100).quantize(Decimal("0.01"))
            if change is not None and first is not None and first != 0
            else None
        )
        used = before_rows + after_rows if aggregation == "count" else len(before) + len(after)
        figures.append(
            (
                group,
                used,
                [
                    (f"{label} ({span(previous)})", first),
                    (f"{label} ({span(recent)})", last),
                    ("Variación", change),
                    ("Variación %", percent),
                ],
            )
        )
    figures.sort(
        key=lambda item: (item[2][2][1] is None, -abs(item[2][2][1] or Decimal(0)), item[0])
    )
    method = (
        f"Compara los últimos {window} meses con datos ({span(recent)}) con los {window} "
        f"anteriores ({span(previous)}): {METHODS[aggregation]} de cada ventana; la variación "
        "porcentual se redondea a 2 decimales."
    )
    return build(query, execution, method, figures, ordered=False)


def quartile(ordered: Sequence[Decimal], q: Decimal) -> Decimal:
    """Cuartil por interpolación lineal entre posiciones (tipo 7)."""
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def compute_outliers(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    assert query.measure
    names = [
        query.measure,
        *query.dimensions,
        *([query.filter_column] if query.filter_column else []),
    ]
    data = columns(content, names)
    total = len(data[query.measure])
    groups: dict[tuple[str, ...], list[Decimal]] = defaultdict(list)
    for i in range(total):
        if query.filter_column and str(data[query.filter_column][i]) != query.filter_value:
            continue
        labels = tuple(data[d][i] for d in query.dimensions)
        if any(item is None for item in labels):
            continue
        number = decimal(data[query.measure][i])
        if number is not None:
            groups[tuple(str(item) for item in labels)].append(number)
    if not groups:
        return f"Ninguna fila tiene un valor numérico de {query.measure}."
    figures: Figures = []
    for labels, values in groups.items():
        ordered = sorted(values)
        if len(ordered) < 4:
            figures.append(
                (
                    labels,
                    len(ordered),
                    [
                        ("Q1", None),
                        ("Q3", None),
                        ("Límite inferior", None),
                        ("Límite superior", None),
                        ("Atípicos", None),
                        ("% atípicos", None),
                    ],
                )
            )
            continue
        with localcontext() as context:
            context.prec = 40
            q1 = quartile(ordered, Decimal("0.25"))
            q3 = quartile(ordered, Decimal("0.75"))
            spread = q3 - q1
            low, high = q1 - spread * Decimal("1.5"), q3 + spread * Decimal("1.5")
            count = sum(1 for value in ordered if value < low or value > high)
            share = (Decimal(count) / len(ordered) * 100).quantize(Decimal("0.01"))
        figures.append(
            (
                labels,
                len(ordered),
                [
                    ("Q1", q1.quantize(SIX)),
                    ("Q3", q3.quantize(SIX)),
                    ("Límite inferior", low.quantize(SIX)),
                    ("Límite superior", high.quantize(SIX)),
                    ("Atípicos", Decimal(count)),
                    ("% atípicos", share),
                ],
            )
        )
    method = (
        "Regla de Tukey: valores fuera de [Q1 - 1,5·RIC, Q3 + 1,5·RIC], con cuartiles por "
        "interpolación lineal (redondeados a 6 decimales); hacen falta al menos 4 valores."
    )
    return build(query, execution, method, figures)
