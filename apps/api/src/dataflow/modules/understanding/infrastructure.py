import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, cast

import polars as pl

from dataflow.modules.understanding.contracts import ColumnProfile, NumericSummary
from dataflow.platform.data_types import DataType
from dataflow.platform.tabular import Cell, display_cell

NUMBER = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d{1,2})?\Z")


def numeric_summary(numbers: list[Decimal]) -> NumericSummary:
    """Suma, media, mínimo y máximo con precisión de 50 dígitos (mismo cálculo para texto
    numérico y para columnas tipadas)."""
    with localcontext() as context:
        context.prec = 50
        total = sum(numbers, Decimal(0))
        return NumericSummary(
            count=len(numbers),
            total=str(total),
            mean=str(total / len(numbers)),
            minimum=str(min(numbers)),
            maximum=str(max(numbers)),
        )


def typed_profile(
    name: str, values: list[Cell], data_type: DataType, parameters: dict[str, Any]
) -> ColumnProfile:
    """Columna tipada: el tipo sugerido es el tipo técnico y no se infiere nada del texto."""
    present = [value for value in values if value is not None]
    shown = [display_cell(value, data_type, parameters) or "" for value in present]
    numeric = None
    if present and data_type in {"integer", "decimal"}:
        numeric = numeric_summary([Decimal(cast(int | Decimal, value)) for value in present])
    return ColumnProfile(
        name=name,
        technical_type=data_type,
        suggested_type=data_type,
        null_count=len(values) - len(present),
        unique_count=len(set(present)),
        examples=[value[:120] for value in dict.fromkeys(shown)][:3],
        numeric=numeric,
    )


def profile_rows(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    types: Sequence[tuple[DataType, dict[str, Any]]] | None = None,
) -> list[ColumnProfile]:
    if types is not None and any(data_type != "string" for data_type, _ in types):
        return [
            profile_rows([name], [[row[index]] for row in rows])[0]
            if types[index][0] == "string"
            else typed_profile(name, [row[index] for row in rows], *types[index])
            for index, name in enumerate(headers)
        ]
    frame = pl.DataFrame(rows, schema={h: pl.String for h in headers}, orient="row")
    result: list[ColumnProfile] = []
    for name in headers:
        series = frame[name]
        values = series.drop_nulls().to_list()
        suggested = "string"
        numeric = None
        if values and all(len(v) <= 38 and NUMBER.fullmatch(v) for v in values):
            numbers = [Decimal(v) for v in values]
            if all(abs(n.adjusted()) <= 12 for n in numbers):
                suggested = (
                    "integer"
                    if all(re.fullmatch(r"[-+]?(?:0|[1-9]\d*)", v) for v in values)
                    else "decimal"
                )
                numeric = numeric_summary(numbers)
        elif values and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in values):
            try:
                for value in values:
                    date.fromisoformat(value)
                suggested = "date"
            except ValueError:
                pass
        elif values and all(v.lower() in {"true", "false"} for v in values):
            suggested = "boolean"
        result.append(
            ColumnProfile(
                name=name,
                suggested_type=suggested,
                null_count=series.null_count(),
                unique_count=series.drop_nulls().n_unique(),
                examples=[v[:120] for v in dict.fromkeys(values)][:3],
                numeric=numeric,
            )
        )
    return result
