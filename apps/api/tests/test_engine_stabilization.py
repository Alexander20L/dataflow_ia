"""Fase 11.0: regresiones del motor antes de habilitar aprobaciones automáticas.

1. cleaning.filter_rows@1 con `is_null` se valida para cualquier tipo, pero la ejecución sólo
   aceptaba columnas de texto (COLUMN_TYPE_MISMATCH sobre columnas tipadas).
2. Las sumas y restas de decimales del motor de analytics usaban el contexto por defecto de
   Python (28 dígitos) y redondeaban sin aviso valores Decimal(38, s) de 29 a 38 dígitos.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from test_analytics_comparisons import SUM, query2
from test_analytics_engine import metric, query, table
from test_analytics_query_v1_golden import IDS as GOLDEN_IDS

from dataflow.modules.analytics.engine import change_of
from dataflow.modules.cleaning.infrastructure import SOURCE_ROW, attach_lineage, filter_rows
from dataflow.platform.decimal_context import EXACT_PRECISION, exact_context
from dataflow.platform.errors import ApplicationError

D = Decimal

# 30 dígitos: cabe en Decimal(38, 2) pero no en el contexto por defecto de Python.
WIDE = "1234567890123456789012345678.94"


def typed_table() -> pl.DataFrame:
    return pl.DataFrame(
        [
            pl.Series("texto", ["a", None, "c", "d"], dtype=pl.String),
            pl.Series("entero", [1, 2, None, 4], dtype=pl.Int64),
            pl.Series("decimal", [D("1.50"), D("2.00"), D("3.25"), None], dtype=pl.Decimal(38, 2)),
            pl.Series("fecha", [None, date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)]),
            pl.Series("booleano", [True, False, True, True], dtype=pl.Boolean),
        ]
    )


@pytest.mark.parametrize(
    ("column", "kept"),
    [
        ("texto", [1, 3, 4]),
        ("entero", [1, 2, 4]),
        ("decimal", [1, 2, 3]),
        ("fecha", [2, 3, 4]),
        ("booleano", [1, 2, 3, 4]),
    ],
)
def test_filter_null_rows_works_on_every_column_type(column: str, kept: list[int]) -> None:
    frame = attach_lineage(typed_table())
    result = filter_rows(frame, [column], "is_null", "any")
    assert result.get_column(SOURCE_ROW).to_list() == kept
    assert result.schema == frame.schema  # los tipos no cambian


def test_filter_null_rows_combines_typed_columns() -> None:
    frame = attach_lineage(typed_table())
    any_null = filter_rows(frame, ["entero", "decimal", "fecha"], "is_null", "any")
    assert any_null.get_column(SOURCE_ROW).to_list() == [2]
    all_null = filter_rows(frame, ["entero", "fecha"], "is_null", "all")
    assert all_null.get_column(SOURCE_ROW).to_list() == [1, 2, 3, 4]


def test_whitespace_filter_still_requires_text() -> None:
    frame = attach_lineage(typed_table())
    with pytest.raises(ApplicationError) as error:
        filter_rows(frame, ["entero"], "is_whitespace_only", "any")
    assert error.value.code == "COLUMN_TYPE_MISMATCH"


def test_filter_null_rows_rejects_unknown_and_lineage_columns() -> None:
    frame = attach_lineage(typed_table())
    for name in ["no_existe", SOURCE_ROW]:
        with pytest.raises(ApplicationError) as error:
            filter_rows(frame, [name], "is_null", "any")
        assert error.value.code == "UNKNOWN_COLUMN"


def test_exact_context_is_wide_and_local() -> None:
    with exact_context() as context:
        assert context.prec == EXACT_PRECISION
        assert D(WIDE) + D("0.03") == D("1234567890123456789012345678.97")
    # Fuera del contexto exacto, Python vuelve a sus 28 dígitos: por eso el motor no lo usa.
    assert D(WIDE) + D("0.03") != D("1234567890123456789012345678.97")


def wide_rows(*amounts: str) -> list[list[Any]]:
    return [["Norte", date(2026, 1, 1), D(a), 1, "a"] for a in amounts]


def test_sum_of_wide_decimals_is_exact() -> None:
    assert table(query([metric("sum")], wide_rows(WIDE, "0.03"))) == [
        ("1234567890123456789012345678.97",)
    ]


def test_avg_of_wide_decimals_is_exact() -> None:
    rows = wide_rows(WIDE, "0.04")
    # (…678.94 + 0.04) / 2 = …339.49 exacto a escala 4.
    assert table(query([metric("avg")], rows)) == [("617283945061728394506172839.4900",)]


def test_sum_over_38_digits_is_an_explicit_error_not_a_rounding() -> None:
    largest = "9" * 36 + ".99"  # 38 dígitos
    with pytest.raises(ApplicationError) as error:
        query([metric("sum")], wide_rows(largest, largest))
    assert error.value.code == "RESULT_PRECISION_EXCEEDED"


def test_change_of_wide_decimals_is_exact() -> None:
    change, change_pct, status = change_of(WIDE, "0.03", 2, 2, "Ventas")
    assert status == "available"
    assert change == "1234567890123456789012345678.91"
    # …678.91 / 0.03 × 100 = 4115226300411522630041152263033.333… → HALF_EVEN a 2 decimales.
    assert change_pct == "4115226300411522630041152263033.33"


def test_share_total_of_wide_decimals_is_exact() -> None:
    rows = [
        ["Norte", date(2026, 1, 10), D(WIDE), 1, "a"],
        ["Sur", date(2026, 1, 10), D("0.03"), 1, "b"],
    ]
    result = query2(
        [SUM],
        rows,
        share_of_total=[str(SUM.reference.revision_id)],
        dimensions=[GOLDEN_IDS["region"]],
    )
    assert [r.values["m0"] for r in result.rows] == [WIDE, "0.03"]
    assert result.shares[0].total == "1234567890123456789012345678.97"
    assert [r.share["m0"].value for r in result.rows] == ["100.00", "0.00"]
