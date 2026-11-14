"""Medidas de asociación sobre todas las filas de la tabla publicada (Fase 19, ADR-036).

- número–número: Pearson y Spearman (rangos promedio);
- categoría–categoría: V de Cramér (sin corrección de sesgo);
- número–categoría: razón de correlación eta;
- dependencia funcional A → B: proporción de valores de A con un único B.

Sólo filas con ambos valores; un par con menos de `MIN_ROWS` filas o sin variación no se mide.
Las columnas se toman por posición con alias neutros (nunca `pl.col(nombre)` con texto ajeno).
Los valores se redondean a 4 decimales y el método lo declara.
"""

import io
import math
from collections.abc import Sequence
from decimal import Decimal

import polars as pl

from dataflow.modules.comprehension.contracts import Association, Formula, Measure
from dataflow.modules.comprehension.domain import strength

MIN_ROWS = 10
MAX_CATEGORIES = 50
MAX_MEASURES = 10
MAX_DIMENSIONS = 10
ROUNDING = "Redondeado a 4 decimales."


def frame(content: bytes, names: Sequence[str]) -> tuple[pl.DataFrame, dict[str, str]]:
    table = pl.read_parquet(io.BytesIO(content))
    aliases = {name: f"c{index}" for index, name in enumerate(names)}
    return (
        pl.DataFrame([table.get_column(name).alias(aliases[name]) for name in names]),
        aliases,
    )


def number(series: pl.Series) -> pl.Series:
    if series.dtype == pl.String:
        return series.cast(pl.Float64, strict=False)
    return series.cast(pl.Float64, strict=False)


def canonical(value: float) -> str:
    return format(Decimal(repr(round(value, 4))).quantize(Decimal("0.0001")), "f")


def association(
    a: str, b: str, measure: Measure, value: float, rows: int, method: str
) -> Association | None:
    if math.isnan(value) or math.isinf(value):
        return None
    text = canonical(value)
    return Association(
        columns=(a, b),
        measure=measure,
        value=text,
        strength=strength(Decimal(text)),
        rows=rows,
        method=f"{method} {ROUNDING}",
    )


def numeric_pair(data: pl.DataFrame, x: str, y: str, a: str, b: str) -> list[Association]:
    pair = pl.DataFrame({"x": number(data.get_column(x)), "y": number(data.get_column(y))})
    pair = pair.drop_nulls()
    if pair.height < MIN_ROWS or pair["x"].n_unique() < 2 or pair["y"].n_unique() < 2:
        return []
    pearson = pair.select(pl.corr("x", "y", method="pearson")).item()
    spearman = pair.select(pl.corr("x", "y", method="spearman")).item()
    found = [
        association(a, b, "pearson", float(pearson), pair.height, "Pearson sobre pares completos."),
        association(a, b, "spearman", float(spearman), pair.height, "Spearman (rangos promedio)."),
    ]
    return [item for item in found if item is not None]


def cramers_v(data: pl.DataFrame, x: str, y: str, a: str, b: str) -> Association | None:
    pair = data.select(pl.col(x).alias("x"), pl.col(y).alias("y")).drop_nulls()
    n = pair.height
    if n < MIN_ROWS:
        return None
    rows, columns = pair["x"].n_unique(), pair["y"].n_unique()
    if min(rows, columns) < 2 or max(rows, columns) > MAX_CATEGORIES:
        return None
    cells = pair.group_by("x", "y").len()
    row_totals = dict(pair.group_by("x").len().iter_rows())
    column_totals = dict(pair.group_by("y").len().iter_rows())
    chi2 = n * (
        sum(
            count * count / (row_totals[left] * column_totals[right])
            for left, right, count in cells.iter_rows()
        )
        - 1
    )
    value = math.sqrt(max(chi2, 0.0) / (n * (min(rows, columns) - 1)))
    return association(
        a, b, "cramers_v", value, n, "V de Cramér sobre la tabla de contingencia (sin corrección)."
    )


def eta(data: pl.DataFrame, measure: str, category: str, a: str, b: str) -> Association | None:
    pair = pl.DataFrame(
        {"y": number(data.get_column(measure)), "g": data.get_column(category)}
    ).drop_nulls()
    n = pair.height
    if n < MIN_ROWS or pair["g"].n_unique() < 2 or pair["g"].n_unique() > MAX_CATEGORIES:
        return None
    mean = pair["y"].mean()
    total = float(((pair["y"] - mean) ** 2).sum())
    if total == 0:
        return None
    groups = pair.group_by("g").agg(pl.col("y").mean().alias("m"), pl.len().alias("n"))
    between = float(
        sum(
            size * (group_mean - mean) ** 2
            for group_mean, size in groups.select("m", "n").iter_rows()
        )
    )
    return association(
        a, b, "eta", math.sqrt(between / total), n, "Razón de correlación eta (medida por grupos)."
    )


def associations(
    content: bytes, measures: Sequence[str], dimensions: Sequence[str]
) -> tuple[list[Association], list[str]]:
    """Asociaciones entre las columnas elegidas (columnas de la matriz, en orden)."""
    chosen_measures = list(measures)[:MAX_MEASURES]
    chosen_dimensions = list(dimensions)[:MAX_DIMENSIONS]
    names = chosen_measures + chosen_dimensions
    if len(names) < 2:
        return [], names
    data, alias = frame(content, names)
    result: list[Association] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            x, y = alias[a], alias[b]
            if a in chosen_measures and b in chosen_measures:
                result.extend(numeric_pair(data, x, y, a, b))
            elif a in chosen_dimensions and b in chosen_dimensions:
                item = cramers_v(data, x, y, a, b)
                if item:
                    result.append(item)
            else:
                measure, category = (a, b) if a in chosen_measures else (b, a)
                item = eta(data, alias[measure], alias[category], a, b)
                if item:
                    result.append(item)
    return result, names


def dependencies(
    content: bytes, pairs: Sequence[tuple[str, str]]
) -> dict[tuple[str, str], Association]:
    """Para cada (A, B): proporción de valores de A con un único valor de B."""
    names = sorted({name for pair in pairs for name in pair})
    if not names:
        return {}
    data, alias = frame(content, names)
    found: dict[tuple[str, str], Association] = {}
    for a, b in pairs:
        pair = data.select(pl.col(alias[a]).alias("a"), pl.col(alias[b]).alias("b")).drop_nulls()
        if pair.height < MIN_ROWS:
            continue
        per_value = pair.group_by("a").agg(pl.col("b").n_unique().alias("k"))
        total = per_value.height
        if total == 0:
            continue
        single = per_value.filter(pl.col("k") == 1).height
        share = Decimal(single) / Decimal(total)
        found[(a, b)] = Association(
            columns=(a, b),
            measure="dependency",
            value=format(share.quantize(Decimal("0.0001")), "f"),
            strength=strength(share),
            rows=total,
            method=f"Valores de {a} con un único {b} sobre {total} valores distintos. {ROUNDING}",
        )
    return found


def distinct_values(content: bytes, dimensions: Sequence[str]) -> dict[str, list[str]]:
    """Valores distintos de cada dimensión (sólo si son pocos), del más al menos frecuente."""
    if not dimensions:
        return {}
    data, alias = frame(content, dimensions)
    result: dict[str, list[str]] = {}
    for name in dimensions:
        series = data.get_column(alias[name]).drop_nulls().cast(pl.String)
        if series.n_unique() > MAX_CATEGORIES:
            continue
        counts = (
            pl.DataFrame({"v": series})
            .group_by("v")
            .len()
            .sort(["len", "v"], descending=[True, False])
        )
        result[name] = [str(value) for value in counts.get_column("v").to_list()]
    return result


# --- Fase 24: columnas calculadas y misma entidad ----------------------------------------------

MAX_SOURCES = 6  # fuentes por fórmula (ADR-041)
WEIGHT_STEP = Decimal("0.05")  # los pesos se aceptan en múltiplos de 0,05


def decimals(series: pl.Series) -> int:
    """Decimales escritos en los valores de una columna leída (texto canónico), como mucho 6."""
    text = series.drop_nulls().cast(pl.String)
    if text.len() == 0:
        return 0
    fraction = text.str.extract(r"\.(\d+)$", 1).str.len_chars().fill_null(0)
    longest = fraction.max()
    return min(int(longest) if isinstance(longest, int) else 0, 6)


def solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Sistema lineal pequeño por eliminación gaussiana con pivote parcial (None si es
    singular). Sin dependencias nuevas: el proyecto no usa numpy."""
    n = len(vector)
    rows = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-9:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def step(weight: float) -> Decimal:
    return (Decimal(repr(weight)) / WEIGHT_STEP).quantize(Decimal(1)) * WEIGHT_STEP


def weighted_sums(content: bytes, measures: Sequence[str]) -> list[Formula]:
    """Medidas que son, fila a fila, una suma ponderada de otras: pesos positivos en múltiplos de
    0,05 (de 0,05 a 1) y error máximo de medio dígito del último decimal escrito. Se ajusta por
    mínimos cuadrados sin término constante y se comprueba con los pesos redondeados en TODAS las
    filas con valor en la medida y en sus fuentes."""
    names = list(measures)[:MAX_MEASURES]
    if len(names) < 3:
        return []
    data, alias = frame(content, names)
    numbers = pl.DataFrame([number(data.get_column(alias[n])).alias(alias[n]) for n in names])
    found: list[Formula] = []
    for target in names:
        sources = [n for n in names if n != target][: MAX_SOURCES + 3]
        cols = [alias[n] for n in [target, *sources]]
        complete = numbers.select(cols).drop_nulls()
        if complete.height < max(MIN_ROWS, len(sources) + 2):
            continue
        y = complete.get_column(alias[target])
        if y.n_unique() < 2:
            continue
        xs = [complete.get_column(alias[s]) for s in sources]
        gram = [[float((a * b).sum()) for b in xs] for a in xs]
        right = [float((a * y).sum()) for a in xs]
        weights = solve(gram, right)
        if weights is None:
            continue
        kept = [(s, step(w)) for s, w in zip(sources, weights, strict=True) if step(w) != 0]
        if not 2 <= len(kept) <= MAX_SOURCES or any(not 0 < w <= 1 for _, w in kept):
            continue
        tolerance = Decimal(5) / Decimal(10) ** (decimals(data.get_column(alias[target])) + 1)
        estimate = complete.get_column(alias[kept[0][0]]) * float(kept[0][1])
        for source, weight in kept[1:]:
            estimate = estimate + complete.get_column(alias[source]) * float(weight)
        error = (y - estimate).abs()
        matching = int((error <= float(tolerance) + 1e-9).sum())
        if matching != complete.height:
            continue
        terms = " + ".join(f"{format(w.normalize(), 'f').replace('.', ',')}·{s}" for s, w in kept)
        found.append(
            Formula(
                column=target,
                kind="weighted_sum",
                sources=[s for s, _ in kept],
                weights=[format(w.normalize(), "f") for _, w in kept],
                expression=f"{target} = {terms}",
                rows=complete.height,
                matching_rows=matching,
                tolerance=format(tolerance, "f"),
                method="Mínimos cuadrados sin constante; pesos redondeados a múltiplos de 0,05 y "
                "comprobados fila a fila con la tolerancia del último decimal escrito.",
            )
        )
    return found


def canonical_number(value: float) -> str:
    """Número sin ceros de más ni notación científica (10.5 → «10.5», 11.0 → «11»)."""
    text = format(Decimal(repr(value)).normalize(), "f")
    return text[:-2] if text.endswith(".0") else text


def thresholds(
    content: bytes, measures: Sequence[str], dichotomous: Sequence[str]
) -> list[Formula]:
    """Columnas de dos valores que se deciden por un umbral de una medida: todos los valores de
    una categoría quedan por debajo de todos los de la otra. El umbral es el menor valor
    observado de la categoría alta (nunca uno inventado)."""
    chosen = list(measures)[:MAX_MEASURES]
    if not chosen or not dichotomous:
        return []
    names = list(dict.fromkeys([*chosen, *dichotomous]))
    data, alias = frame(content, names)
    found: list[Formula] = []
    for category in dichotomous:
        for measure in chosen:
            if measure == category:
                continue
            pair = pl.DataFrame(
                {
                    "y": number(data.get_column(alias[measure])),
                    "g": data.get_column(alias[category]).cast(pl.String),
                }
            ).drop_nulls()
            if pair.height < MIN_ROWS or pair["g"].n_unique() != 2:
                continue
            ranges = sorted(
                pair.group_by("g")
                .agg(pl.col("y").min().alias("lo"), pl.col("y").max().alias("hi"))
                .iter_rows(),
                key=lambda r: (r[1], r[2]),
            )
            (low_name, _, low_max), (high_name, high_min, _) = ranges
            if not low_max < high_min:
                continue
            cut = canonical_number(float(high_min))
            found.append(
                Formula(
                    column=category,
                    kind="threshold",
                    sources=[measure],
                    threshold=cut,
                    category=str(high_name),
                    expression=f"{category} = «{high_name}» cuando {measure} ≥ "
                    f"{cut.replace('.', ',')}; si no, «{low_name}»",
                    rows=pair.height,
                    matching_rows=pair.height,
                    tolerance="0",
                    method="Los rangos de la medida en las dos categorías no se solapan en ninguna "
                    "fila; el umbral es el menor valor observado de la categoría alta.",
                )
            )
    return found


def same_entities(content: bytes, candidates: Sequence[str]) -> list[tuple[str, str, int]]:
    """Pares de columnas que nombran lo mismo (1:1): ambas se repiten y cada valor de una tiene un
    único valor de la otra, en los dos sentidos. Una columna única por fila no cuenta (sería
    trivial). Devuelve (A, B, valores distintos)."""
    names = list(candidates)[:12]
    if len(names) < 2:
        return []
    data, alias = frame(content, names)
    found: list[tuple[str, str, int]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pair = data.select(
                pl.col(alias[a]).alias("a"), pl.col(alias[b]).alias("b")
            ).drop_nulls()
            if pair.height < MIN_ROWS:
                continue
            distinct = pair["a"].n_unique()
            if distinct < 2 or distinct == pair.height or pair["b"].n_unique() != distinct:
                continue
            if pair.unique().height == distinct:
                found.append((a, b, distinct))
    return found


def distinct_counts(content: bytes, names: Sequence[str]) -> dict[str, int]:
    """Valores distintos (no nulos) de cada columna."""
    if not names:
        return {}
    data, alias = frame(content, names)
    return {name: int(data.get_column(alias[name]).drop_nulls().n_unique()) for name in names}


def month_counts(content: bytes, kind: str, names: Sequence[str]) -> dict[str, int]:
    """Fase 28: registros de cada mes «AAAA-MM» con al menos uno, de una fecha (`date`) o de un
    año y un mes (`year_month`, sólo meses numéricos o con nombre ya reconocidos como 1 a 12)."""
    if not names:
        return {}
    data, alias = frame(content, names)
    if kind == "date":
        months = data.get_column(alias[names[0]]).cast(pl.String).str.slice(0, 7)
    else:
        year = data.get_column(alias[names[0]]).cast(pl.String)
        month = data.get_column(alias[names[1]]).cast(pl.String).cast(pl.Int64, strict=False)
        months = (
            pl.DataFrame({"y": year, "m": month})
            .select(
                pl.when(pl.col("m").is_between(1, 12))
                .then(pl.col("y") + "-" + pl.col("m").cast(pl.String).str.zfill(2))
                .alias("p")
            )
            .to_series()
        )
    counts = months.drop_nulls().value_counts(sort=False, name="n")
    return {str(month): int(n) for month, n in counts.iter_rows()}


def per_year(months: dict[str, int]) -> list[tuple[str, int]]:
    """Registros por año a partir de los registros por mes, en orden."""
    years: dict[str, int] = {}
    for month, count in months.items():
        years[month[:4]] = years.get(month[:4], 0) + count
    return sorted(years.items())
