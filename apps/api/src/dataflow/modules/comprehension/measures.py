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

from dataflow.modules.comprehension.contracts import Association, Measure
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
