import re
from datetime import date
from decimal import Decimal, localcontext

import polars as pl

from dataflow.modules.understanding.contracts import ColumnProfile, NumericSummary

NUMBER = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d{1,2})?\Z")


def profile_rows(headers: list[str], rows: list[list[str | None]]) -> list[ColumnProfile]:
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
                with localcontext() as context:
                    context.prec = 50
                    total = sum(numbers, Decimal(0))
                    numeric = NumericSummary(
                        count=len(numbers),
                        total=str(total),
                        mean=str(total / len(numbers)),
                        minimum=str(min(numbers)),
                        maximum=str(max(numbers)),
                    )
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
