"""Reglas puras de la exploración (`explore-v1`): qué se puede consultar y qué propuesta es válida.

Sin Polars, SQL ni IA. El catálogo sale de la comprensión (escalas y relaciones) y de la
interpretación (aditividad): sólo se suman medidas aditivas, sólo se agrupa por dimensiones
(nominales u ordinales) y las relaciones marcadas «No relevante» por el usuario no se exploran.
"""

from collections.abc import Mapping, Sequence
from typing import get_args

from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.exploration.contracts import (
    Aggregation,
    ExploreQuery,
    QueryKind,
    RawQuery,
)

MAX_RULE_QUERIES = 8

KINDS: dict[str, str] = {
    "aggregate": "Una medida agregada (sum, mean, median) o un conteo (count) por una o dos "
    "dimensiones. Campos: measure (salvo count), dimensions, aggregation.",
    "crosstab": "Tabla cruzada de dos dimensiones: registros (count) o suma de una medida "
    "aditiva (sum). Campos: dimensions (dos), aggregation y measure si es sum.",
    "ratio": "Cociente entre la suma de dos medidas aditivas (measure / measure_b), en total o "
    "por una dimensión. Campos: measure, measure_b, dimensions (cero o una).",
    "top": "Los primeros grupos de una dimensión por una medida agregada. Campos: measure (salvo "
    "count), dimensions (una), aggregation, limit (hasta 20).",
    "correlation_by_group": "Correlación de Spearman entre dos medidas dentro de cada grupo de "
    "una dimensión. Campos: measure, measure_b, dimensions (una).",
}
AGGREGATIONS = {"sum": "Suma", "mean": "Promedio", "median": "Mediana", "count": "Registros"}


class Catalog:
    def __init__(self, comprehension: Comprehension, additive: set[str]) -> None:
        scales = {s.column: s.scale for s in comprehension.scales}
        self.measures = [c for c, s in scales.items() if s == "ratio"]
        self.dimensions = [c for c, s in scales.items() if s in {"nominal", "ordinal"}]
        self.additive = {c for c in self.measures if c in additive}
        self.excluded = {r.key for r in comprehension.relationships if r.verdict == "not_relevant"}
        self.excluded_pairs = {
            frozenset(r.columns) for r in comprehension.relationships if r.verdict == "not_relevant"
        }

    def describe(self) -> list[dict[str, object]]:
        return [
            {"columna": c, "tipo": "medida", "aditiva": c in self.additive} for c in self.measures
        ] + [{"columna": c, "tipo": "dimension"} for c in self.dimensions]


def title(query: ExploreQuery) -> str:
    dims = " y ".join(query.dimensions)
    suffix = f" ({query.filter_column} = {query.filter_value})" if query.filter_column else ""
    if query.kind == "ratio":
        base = f"{query.measure} / {query.measure_b}" + (f" por {dims}" if dims else " (total)")
    elif query.kind == "correlation_by_group":
        base = f"Correlación entre {query.measure} y {query.measure_b} dentro de cada {dims}"
    elif query.kind == "top":
        what = (
            "registros"
            if query.aggregation == "count"
            else f"{AGGREGATIONS[query.aggregation or 'sum'].lower()} de {query.measure}"
        )
        base = f"Primeros {query.limit} de {dims} por {what}"
    elif query.aggregation == "count":
        base = f"Registros por {dims}"
    else:
        base = f"{AGGREGATIONS[query.aggregation or 'sum']} de {query.measure} por {dims}"
    return base + suffix


def validate(
    raw: RawQuery, catalog: Catalog, done: set[str]
) -> tuple[ExploreQuery | None, str | None]:
    """Convierte una propuesta en consulta válida o explica por qué se rechaza."""
    if raw.kind not in get_args(QueryKind):
        return None, f"«{raw.kind}» no es un tipo de consulta del catálogo."
    dims = list(raw.dimensions)
    if len(set(dims)) != len(dims):
        return None, "Dimensiones repetidas."
    for dim in dims:
        if dim not in catalog.dimensions:
            return None, f"«{dim}» no es una dimensión (nominal u ordinal) de la tabla."
    for name in (raw.measure, raw.measure_b):
        if name is not None and name not in catalog.measures:
            return None, f"«{name}» no es una medida numérica de la tabla."
    aggregation = raw.aggregation
    if aggregation is not None and aggregation not in get_args(Aggregation):
        return None, f"«{aggregation}» no es una agregación admitida."
    kind = raw.kind
    needs: dict[str, tuple[int, int]] = {
        "aggregate": (1, 2),
        "crosstab": (2, 2),
        "ratio": (0, 1),
        "top": (1, 1),
        "correlation_by_group": (1, 1),
    }
    low, high = needs[kind]
    if not low <= len(dims) <= high:
        return None, f"Este tipo necesita entre {low} y {high} dimensiones."
    if kind in {"aggregate", "top", "crosstab"}:
        aggregation = aggregation or ("count" if raw.measure is None else "sum")
        if kind == "crosstab" and aggregation not in {"count", "sum"}:
            return None, "Una tabla cruzada cuenta registros o suma una medida."
        if aggregation != "count" and raw.measure is None:
            return None, "Falta la medida."
        if aggregation == "count" and raw.measure is not None:
            return None, "Un conteo no lleva medida."
        if aggregation == "sum" and raw.measure not in catalog.additive:
            return None, f"{raw.measure} no es aditiva: no se suma (usa mean o median)."
        if raw.measure_b is not None:
            return None, "Este tipo no lleva segunda medida."
    elif kind in {"ratio", "correlation_by_group"}:
        if raw.measure is None or raw.measure_b is None or raw.measure == raw.measure_b:
            return None, "Hacen falta dos medidas distintas."
        if kind == "ratio" and not {raw.measure, raw.measure_b} <= catalog.additive:
            return None, "Un cociente de sumas necesita dos medidas aditivas."
        aggregation = None
    if raw.filter_column is not None:
        if raw.filter_column not in catalog.dimensions or raw.filter_column in dims:
            return None, "El filtro debe ser otra dimensión de la tabla."
        if not raw.filter_value:
            return None, "Falta el valor del filtro."
    elif raw.filter_value is not None:
        return None, "Un valor de filtro necesita su columna."
    columns = {raw.measure, raw.measure_b, *dims} - {None}
    for pair in catalog.excluded_pairs:
        if pair <= columns:
            return None, "El usuario marcó esta relación como «No relevante»."
    query = ExploreQuery(
        kind=kind,
        measure=raw.measure,
        measure_b=raw.measure_b,
        dimensions=dims,
        aggregation=aggregation,
        filter_column=raw.filter_column,
        filter_value=raw.filter_value,
        limit=(raw.limit or 10) if kind == "top" else None,
    )
    if query.key in done:
        return None, "Ya se exploró."
    return query, None


def rule_queries(comprehension: Comprehension, catalog: Catalog) -> list[tuple[RawQuery, str]]:
    """Una consulta por relación confirmada de la comprensión (las valoradas como relevantes
    primero, que ya vienen delante), hasta `MAX_RULE_QUERIES`."""
    found: list[tuple[RawQuery, str]] = []
    first_dimension = catalog.dimensions[0] if catalog.dimensions else None
    for relation in comprehension.relationships:
        if relation.status != "confirmed" or relation.verdict == "not_relevant":
            continue
        if relation.kind not in {"association"}:
            continue
        a, b = relation.columns
        measures = [c for c in (a, b) if c in catalog.measures]
        dims = [c for c in (a, b) if c in catalog.dimensions]
        motive = f"Relación confirmada entre {a} y {b}: ver cómo se reparte."
        if len(measures) == 1 and len(dims) == 1:
            measure = measures[0]
            aggregation = "sum" if measure in catalog.additive else "mean"
            found.append(
                (
                    RawQuery(
                        kind="aggregate",
                        measure=measure,
                        dimensions=dims,
                        aggregation=aggregation,
                    ),
                    motive,
                )
            )
        elif len(dims) == 2:
            found.append((RawQuery(kind="crosstab", dimensions=dims, aggregation="count"), motive))
        elif len(measures) == 2 and first_dimension:
            found.append(
                (
                    RawQuery(
                        kind="correlation_by_group",
                        measure=measures[0],
                        measure_b=measures[1],
                        dimensions=[first_dimension],
                    ),
                    f"Relación confirmada entre {a} y {b}: ¿se mantiene en cada {first_dimension}?",
                )
            )
        if len(found) >= MAX_RULE_QUERIES:
            break
    return found


def clean_reason(text: str, allowed: Sequence[str], limit: int = 300) -> str | None:
    """Motivo de la IA sin cifras propias (las de columnas y grupos del resultado se admiten)."""
    stripped = text.strip()[:limit]
    if not stripped:
        return None
    remainder = stripped
    for name in sorted({a for a in allowed if a}, key=len, reverse=True):
        remainder = remainder.replace(name, " ")
    return None if any(c.isdigit() for c in remainder) else stripped


def additive_columns(columns: Mapping[str, str | None]) -> set[str]:
    return {name for name, additivity in columns.items() if additivity == "additive"}
