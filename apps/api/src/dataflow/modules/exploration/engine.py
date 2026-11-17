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
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from statistics import median

import polars as pl

from dataflow.modules.exploration import statistics as stats
from dataflow.modules.exploration.contracts import (
    MAX_BINS,
    MAX_GROUPS,
    MAX_POINTS,
    TEMPORAL_KINDS,
    ControlCheck,
    ExploreFigure,
    ExploreQuery,
    ExploreResult,
    ExploreRow,
    StatisticalTest,
)
from dataflow.modules.exploration.domain import AGGREGATIONS, derived_base, title
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
    """Las columnas pedidas, por nombre exacto. Fase 29: una variable derivada («antigüedad de
    X», «cuartil de X») que no sea una columna real se calcula a partir de su columna base."""
    table = pl.read_parquet(io.BytesIO(content))
    found: dict[str, list[object]] = {}
    for name in dict.fromkeys(names):
        if name in table.columns:
            found[name] = table.get_column(name).to_list()
            continue
        derived = derived_base(name)
        if derived is None or derived[1] not in table.columns:
            found[name] = table.get_column(name).to_list()  # error del motor: no existe
            continue
        kind, base = derived
        values = table.get_column(base).to_list()
        found[name] = tenure_bands(values) if kind == "tenure" else quartile_bands(values)
    return found


TENURE_BANDS = ("Menos de 1 año", "1 a 3 años", "3 a 5 años", "5 años o más")


def as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def tenure_bands(values: Sequence[object]) -> list[object]:
    """Antigüedad en tramos de años hasta la fecha más reciente de la columna (la de referencia
    del archivo, no el día de hoy: así el resultado no cambia con el tiempo)."""
    dates = [as_date(v) for v in values]
    known = [d for d in dates if d is not None]
    if not known:
        return [None] * len(values)
    reference = max(known)
    labels: list[object] = []
    for day in dates:
        if day is None:
            labels.append(None)
            continue
        years = (reference - day).days / 365.25
        band = 0 if years < 1 else 1 if years < 3 else 2 if years < 5 else 3
        labels.append(TENURE_BANDS[band])
    return labels


def quartile_bands(values: Sequence[object]) -> list[object]:
    """Cuartil de cada valor (Q1 a Q4) con sus límites (cuartiles de tipo 7 sobre todos los
    valores numéricos de la columna)."""
    numbers = [decimal(v) for v in values]
    ordered = sorted(n for n in numbers if n is not None)
    if len(ordered) < 4:
        return [None] * len(values)
    q1, q2, q3 = (quartile(ordered, Decimal(q)) for q in ("0.25", "0.5", "0.75"))
    names = (
        f"Q1 (hasta {text(q1)})",
        f"Q2 ({text(q1)} a {text(q2)})",
        f"Q3 ({text(q2)} a {text(q3)})",
        f"Q4 (más de {text(q3)})",
    )
    labels: list[object] = []
    for number in numbers:
        if number is None:
            labels.append(None)
        else:
            labels.append(
                names[0 if number <= q1 else 1 if number <= q2 else 2 if number <= q3 else 3]
            )
    return labels


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
    if query.kind == "distribution":
        return compute_distribution(content, query, execution)
    if query.kind == "scatter":
        return compute_scatter(content, query, execution)
    if query.kind == "rate":
        return compute_rate(content, query, execution)
    if query.kind == "cohort":
        return compute_cohort(content, query, execution)
    if query.kind == "factor":
        return compute_factor(content, query, execution)
    if query.kind == "stratified":
        return compute_stratified(content, query, execution)
    names = [
        *query.dimensions,
        *[m for m in (query.measure, query.measure_b) if m],
        *([query.filter_column] if query.filter_column else []),
    ]
    data = columns(content, names)
    # Fase 26: un conteo total no lee ninguna columna; se cuentan las filas de la tabla.
    total = len(next(iter(data.values()))) if data else row_count(content)
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
    first = {
        "evolution": ["Periodo"],
        "distribution": ["Intervalo"],
        "scatter": ["Fila"],
        "cohort": ["Año"],
    }
    headers = [
        *first.get(query.kind, query.dimensions),
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


# --- Fase 26 (dashboard-design-v2): histograma, dispersión y subconjunto filtrado ---------------


def compute_distribution(
    content: bytes, query: ExploreQuery, execution: str
) -> ExploreResult | str:
    """Histograma de una medida: intervalos de igual ancho (regla de Sturges) sobre todos los
    valores numéricos; cada intervalo cuenta sus registros."""
    assert query.measure
    values = [
        n
        for n in (decimal(v) for v in columns(content, [query.measure])[query.measure])
        if n is not None
    ]
    if len(values) < 2:
        return f"Hacen falta al menos dos valores numéricos de {query.measure}."
    low, high = min(values), max(values)
    if low == high:
        bins = 1
    else:
        bins = min(MAX_BINS, (len(values) - 1).bit_length() + 1)
    with localcontext() as context:
        context.prec = 40
        width = (high - low) / bins if bins > 1 else Decimal(0)
        counts = [0] * bins
        for value in values:
            index = 0 if width == 0 else min(int((value - low) / width), bins - 1)
            counts[index] += 1
        edges = [low + width * i for i in range(bins)] + [high]

    def edge(value: Decimal) -> str:
        return text(value.quantize(SIX)) or "0"

    figures: Figures = [
        (
            (f"[{edge(edges[i])}, {edge(edges[i + 1])}" + ("]" if i == bins - 1 else ")"),),
            counts[i],
            [("Registros", Decimal(counts[i]))],
        )
        for i in range(bins)
    ]
    method = (
        f"Histograma de {bins} intervalo{'s' if bins != 1 else ''} de igual ancho (regla de "
        f"Sturges, máximo {MAX_BINS}) sobre los {len(values)} valores numéricos; los extremos "
        "se muestran redondeados a 6 decimales."
    )
    return build(query, execution, method, figures, ordered=False)


def compute_scatter(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """Pares de dos medidas: todas las filas con ambas o, si hay más de `MAX_POINTS`, una
    muestra a intervalos regulares del orden de las filas (determinista)."""
    assert query.measure and query.measure_b
    data = columns(content, [query.measure, query.measure_b])
    pairs = [
        (index, x, y)
        for index, (x, y) in enumerate(
            zip(
                (decimal(v) for v in data[query.measure]),
                (decimal(v) for v in data[query.measure_b]),
                strict=True,
            )
        )
        if x is not None and y is not None
    ]
    if len(pairs) < 2:
        return f"Hacen falta al menos dos filas con {query.measure} y {query.measure_b}."
    total = len(pairs)
    chosen = (
        pairs
        if total <= MAX_POINTS
        else [pairs[i * total // MAX_POINTS] for i in range(MAX_POINTS)]
    )
    figures: Figures = [
        ((f"Fila {index + 1}",), 1, [(query.measure, x), (query.measure_b, y)])
        for index, x, y in chosen
    ]
    method = (
        f"Pares de {query.measure} y {query.measure_b} de las {total} filas con ambas medidas"
        + (
            f"; se muestran {MAX_POINTS} a intervalos regulares del orden de las filas."
            if total > MAX_POINTS
            else "."
        )
    )
    result = build(query, execution, method, figures, ordered=False)
    return result.model_copy(
        update={"total_groups": total, "truncated": total > len(chosen), "covered_rows": total}
    )


def subset(
    content: bytes,
    period: tuple[str, list[str]] | None,
    start: str | None,
    end: str | None,
    categories: Mapping[str, Sequence[str]],
) -> tuple[bytes, int, int]:
    """La tabla publicada con sólo las filas que cumplen los filtros (mes «AAAA-MM» entre
    `start` y `end`, ambos incluidos, y cada columna en sus valores). Devuelve el contenido, las
    filas que quedan y las filas de la tabla. Con filtro de periodo, una fila sin mes
    reconocible queda fuera."""
    table = pl.read_parquet(io.BytesIO(content))
    total = table.height
    keep = [True] * total
    if (start or end) and period is not None:
        kind, names = period
        cells = [table.get_column(name).to_list() for name in names]
        for i in range(total):
            month = month_of(kind, [column[i] for column in cells])
            keep[i] = (
                month is not None
                and (start is None or month >= start)
                and (end is None or month <= end)
            )
    for name, values in categories.items():
        allowed = set(values)
        column = table.get_column(name).to_list()
        for i in range(total):
            if keep[i] and (column[i] is None or str(column[i]) not in allowed):
                keep[i] = False
    filtered = table.filter(pl.Series(keep, dtype=pl.Boolean))
    buffer = io.BytesIO()
    filtered.write_parquet(buffer)
    return buffer.getvalue(), filtered.height, total


# --- Fase 28 (explore-v3): tasas y cohortes ------------------------------------------------------

TWO = Decimal("0.01")
YEAR = re.compile(r"^(\d{4})")


def compute_rate(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """Proporción de una categoría de una columna de dos valores, en total o por grupo. Sin
    categoría pedida se cuenta la menos frecuente (en empate, la primera en orden alfabético),
    que suele ser el caso que interesa (bajas, rechazos, impagos)."""
    assert query.target
    data = columns(content, [query.target, *query.dimensions])
    target = data[query.target]
    present = [str(v) for v in target if v is not None]
    values = sorted(set(present))
    if len(values) != 2:
        return f"{query.target} no tiene exactamente dos valores."
    category = query.target_value or min(values, key=lambda v: (present.count(v), v))
    if category not in values:
        return f"{query.target} no tiene el valor «{category}»."
    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, value in enumerate(target):
        if value is None:
            continue
        labels = tuple(data[d][i] for d in query.dimensions)
        if any(label is None for label in labels):
            continue
        groups[tuple(str(label) for label in labels)].append(i)
    if not groups:
        return "Ninguna fila tiene valor en las columnas pedidas."
    figures: Figures = []
    for labels, members in groups.items():
        cases = sum(1 for i in members if str(target[i]) == category)
        share = (Decimal(cases) * 100 / len(members)).quantize(TWO)
        # La proporción va primero: es la cifra que dibujan los gráficos y la que ordena.
        figures.append(
            (
                labels,
                len(members),
                [
                    (f"Proporción de «{category}» (%)", share),
                    (f"Casos «{category}»", Decimal(cases)),
                ],
            )
        )
    figures.sort(key=lambda item: (-(item[2][0][1] or Decimal(0)), item[0]))
    result = build(
        query,
        execution,
        f"Casos con {query.target} = «{category}» sobre las filas con valor en "
        f"{query.target}{' y en ' + ', '.join(query.dimensions) if query.dimensions else ''}; "
        "porcentaje redondeado a 2 decimales.",
        figures,
        ordered=False,
    )
    return result.model_copy(
        update={"title": title(query.model_copy(update={"target_value": category}))}
    )


def compute_cohort(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """Registros por año de una fecha que describe al registro (p. ej. ingresos por año)."""
    assert query.target
    data = columns(content, [query.target])
    years: dict[str, int] = defaultdict(int)
    for value in data[query.target]:
        found = YEAR.match(str(value)) if value is not None else None
        if found:
            years[found.group(1)] += 1
    if not years:
        return f"{query.target} no tiene años reconocibles."
    figures: Figures = [
        ((year,), count, [("Registros", Decimal(count))]) for year, count in sorted(years.items())
    ]
    return build(
        query,
        execution,
        f"Conteo exacto de registros por año de {query.target} (los años sin registros no "
        "aparecen).",
        figures,
        ordered=False,
    )


# --- Fase 29 (explore-v4): el objetivo por cada factor y su comprobación ------------------------

MIN_TESTED = 10  # registros de un grupo para entrar en la prueba (como `relevance-v2`)


def number_text(value: float, places: str = "0.000001") -> str:
    return text(Decimal(repr(value)).quantize(Decimal(places))) or "0"


def outcome(
    content: bytes, query: ExploreQuery, extra: Sequence[str]
) -> tuple[dict[str, list[object]], str | None, str | None]:
    """Datos del objetivo (tasa o medida) y de las dimensiones pedidas; la categoría contada de
    una tasa (sin categoría pedida, la menos frecuente) o el motivo por el que no se puede."""
    target = query.target or query.measure
    assert target
    data = columns(content, [target, *extra])
    if query.target is None:
        return data, None, None
    present = [str(v) for v in data[target] if v is not None]
    values = sorted(set(present))
    if len(values) != 2:
        return data, None, f"{target} no tiene exactamente dos valores."
    category = query.target_value or min(values, key=lambda v: (present.count(v), v))
    if category not in values:
        return data, None, f"{target} no tiene el valor «{category}»."
    return data, category, None


def scores(
    data: dict[str, list[object]], query: ExploreQuery, category: str | None, dims: Sequence[str]
) -> dict[tuple[str, ...], list[float]]:
    """Por cada combinación de grupos, el valor de cada registro: 1/0 para una tasa (¿es la
    categoría contada?) o el número de la medida. Sin valor en alguna columna, no cuenta."""
    target = query.target or query.measure
    assert target
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for i, value in enumerate(data[target]):
        if value is None:
            continue
        labels = tuple(data[d][i] for d in dims)
        if any(label is None for label in labels):
            continue
        if category is not None:
            score = 1.0 if str(value) == category else 0.0
        else:
            found = decimal(value)
            if found is None:
                continue
            score = float(found)
        groups[tuple(str(label) for label in labels)].append(score)
    return groups


def compute_factor(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """El objetivo en cada grupo de una dimensión: tasa (con intervalo de Wilson) o promedio
    (con intervalo t), y la prueba de que los grupos difieren (chi-cuadrado o Kruskal-Wallis)
    sobre los grupos con al menos `MIN_TESTED` registros."""
    data, category, problem = outcome(content, query, query.dimensions)
    if problem:
        return problem
    groups = scores(data, query, category, query.dimensions)
    if not groups:
        return "Ninguna fila tiene valor en las columnas pedidas."
    rate = category is not None
    figures: Figures = []
    for labels, values in groups.items():
        n = len(values)
        if rate:
            cases = int(sum(values))
            low, high = stats.wilson(cases, n)
            share = Decimal(cases) * 100 / n
            figures.append(
                (
                    labels,
                    n,
                    [
                        (f"Tasa de «{category}» (%)", share.quantize(TWO)),
                        ("IC 95 % inferior (%)", Decimal(repr(low * 100)).quantize(TWO)),
                        ("IC 95 % superior (%)", Decimal(repr(high * 100)).quantize(TWO)),
                        (f"Casos «{category}»", Decimal(cases)),
                    ],
                )
            )
        else:
            interval = stats.mean_interval(values)
            mean = Decimal(repr(sum(values) / n)).quantize(SIX)
            figures.append(
                (
                    labels,
                    n,
                    [
                        (f"Promedio de {query.measure}", mean),
                        (
                            "IC 95 % inferior",
                            Decimal(repr(interval[1])).quantize(SIX) if interval else None,
                        ),
                        (
                            "IC 95 % superior",
                            Decimal(repr(interval[2])).quantize(SIX) if interval else None,
                        ),
                    ],
                )
            )
    figures.sort(key=lambda item: (-(item[2][0][1] or Decimal(0)), item[0]))
    tested = [values for values in groups.values() if len(values) >= MIN_TESTED]
    test: StatisticalTest | None = None
    if rate:
        found = stats.chi_square([(int(sum(v)), len(v) - int(sum(v))) for v in tested])
        if found:
            statistic, df, p, effect = found
            test = StatisticalTest(
                name="chi_square",
                statistic=number_text(statistic, "0.0001"),
                df=df,
                p_value=number_text(p),
                effect_name="cramers_v",
                effect=number_text(effect, "0.0001"),
                groups=len(tested),
                method="Prueba chi-cuadrado de independencia sobre los grupos con al menos "
                f"{MIN_TESTED} registros; V de Cramér como tamaño del efecto.",
            )
    else:
        found = stats.kruskal_wallis(tested)
        if found:
            statistic, df, p, effect = found
            test = StatisticalTest(
                name="kruskal_wallis",
                statistic=number_text(statistic, "0.0001"),
                df=df,
                p_value=number_text(p),
                effect_name="epsilon_squared",
                effect=number_text(effect, "0.0001"),
                groups=len(tested),
                method="Prueba de Kruskal-Wallis (con corrección por empates) sobre los grupos "
                f"con al menos {MIN_TESTED} registros; épsilon cuadrado como tamaño del efecto.",
            )
    what = (
        f"Casos con {query.target} = «{category}» sobre las filas con valor; intervalo de Wilson "
        "al 95 %"
        if rate
        else f"Promedio de {query.measure} sobre las filas con valor; intervalo t al 95 %"
    )
    result = build(
        query,
        execution,
        f"{what}. Cifras redondeadas a {'2' if rate else '6'} decimales.",
        figures,
        ordered=False,
    )
    return result.model_copy(
        update={
            "test": test,
            "title": title(query.model_copy(update={"target_value": category})),
        }
    )


def compute_stratified(content: bytes, query: ExploreQuery, execution: str) -> ExploreResult | str:
    """¿La diferencia del objetivo entre los grupos de la dimensión se mantiene al tener en
    cuenta la de control? Para cada grupo se compara lo observado con lo esperado sólo por su
    composición en la variable de control (estandarización indirecta: el valor de cada nivel de
    control en todo el archivo, ponderado por cuántos registros del grupo tiene en ese nivel).
    Funciona aunque haya combinaciones con pocos registros."""
    factor, control = query.dimensions
    data, category, problem = outcome(content, query, [factor, control])
    if problem:
        return problem
    cells = scores(data, query, category, [factor, control])
    if not cells:
        return "Ninguna fila tiene valor en las columnas pedidas."
    level_values: dict[str, list[float]] = defaultdict(list)
    group_values: dict[str, list[float]] = defaultdict(list)
    composition: dict[str, dict[str, int]] = defaultdict(dict)
    for (group, level), values in cells.items():
        level_values[level].extend(values)
        group_values[group].extend(values)
        composition[group][level] = len(values)
    level_mean = {level: sum(v) / len(v) for level, v in level_values.items()}
    scale = 100.0 if category is not None else 1.0
    places = TWO if category is not None else SIX
    rows: list[tuple[str, int, float, float]] = []
    for group, values in group_values.items():
        n = len(values)
        observed = sum(values) / n
        expected = sum(level_mean[level] * count for level, count in composition[group].items()) / n
        rows.append((group, n, observed * scale, expected * scale))
    rows.sort(key=lambda item: (-item[2], item[0]))
    figures: Figures = [
        (
            (group,),
            n,
            [
                ("Observado", Decimal(repr(observed)).quantize(places)),
                (f"Esperado por {control}", Decimal(repr(expected)).quantize(places)),
                ("Diferencia", Decimal(repr(observed - expected)).quantize(places)),
            ],
        )
        for group, n, observed, expected in rows
    ]
    counted = [r for r in rows if r[1] >= MIN_TESTED]
    if len(counted) < 2:
        return (
            f"Menos de dos grupos de {factor} tienen al menos {MIN_TESTED} registros: no se puede "
            "comprobar la diferencia."
        )
    raw_gap = max(r[2] for r in counted) - min(r[2] for r in counted)
    residuals = [r[2] - r[3] for r in counted]
    residual_gap = max(residuals) - min(residuals)
    share = residual_gap / raw_gap if raw_gap else 0.0
    unit = " puntos" if category is not None else ""
    raw_text = format(raw_gap, ".2f").replace(".", ",")
    residual_text = format(residual_gap, ".2f").replace(".", ",")
    if share >= 2 / 3:
        verdict, said = "holds", f"La diferencia se mantiene al tener en cuenta {control}"
    elif share >= 1 / 3:
        verdict, said = "attenuated", f"La diferencia se atenúa al tener en cuenta {control}"
    else:
        verdict, said = "explained", f"La diferencia se explica en buena parte por {control}"
    check = ControlCheck(
        control=control,
        raw_gap=number_text(raw_gap, "0.01"),
        residual_gap=number_text(residual_gap, "0.01"),
        verdict=verdict,
        text=f"{said}: de {raw_text}{unit} entre grupos de {factor} a {residual_text}{unit} "
        f"descontando lo que explica la composición por {control}.",
    )
    what = (
        f"la tasa de «{category}» en {query.target}"
        if category
        else f"el promedio de {query.measure}"
    )
    result = build(
        query,
        execution,
        f"Para cada {factor}, {what} observada y la esperada sólo por su composición en "
        f"{control} (estandarización indirecta); sólo cuentan los grupos con al menos "
        f"{MIN_TESTED} registros.",
        figures,
        ordered=False,
    )
    return result.model_copy(
        update={
            "control": check,
            "title": title(query.model_copy(update={"target_value": category})),
        }
    )
