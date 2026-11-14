"""Fase 6 · A4: cleaning.normalize_null_tokens@1 y cleaning.deduplicate@1."""

from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError

from dataflow.modules.cleaning.contracts import (
    DeduplicateParameters,
    NormalizeNullTokensParameters,
)
from dataflow.modules.cleaning.infrastructure import (
    SOURCE_ROW,
    attach_lineage,
    deduplicate,
    effect,
    normalize_null_tokens,
    table_digest,
)
from dataflow.platform.errors import ApplicationError

COLUMN = "6f0e7f43-1f0d-4f5e-8b5d-0b5b8d6b7c11"


def text_columns(frame: pl.DataFrame) -> list[dict[str, Any]]:
    return [
        {"id": f"c{index}", "name": name, "technical_type": "string", "type_parameters": {}}
        for index, name in enumerate(frame.columns)
        if name != SOURCE_ROW
    ]


def test_tokens_match_whole_cells_exactly() -> None:
    values = ["NA", "na", " NA", "NA ", "NAN", "N/A", "-", "--", "a-b", None, "x"]
    frame = attach_lineage(pl.DataFrame({"^v$": values, "otra": ["NA"] * len(values)}))
    result = normalize_null_tokens(frame, ["^v$"], ["NA", "-"])
    assert result.get_column("^v$").to_list() == [
        None,
        "na",
        " NA",
        "NA ",
        "NAN",
        "N/A",
        None,
        "--",
        "a-b",
        None,
        "x",
    ]
    assert result.get_column("otra").to_list() == ["NA"] * len(values)  # columna no elegida
    assert result.get_column(SOURCE_ROW).to_list() == list(range(1, len(values) + 1))
    counts, *_ = effect(frame, result, text_columns(frame))
    # Dos celdas pasan a nulo; el nulo previo no cuenta como creado.
    assert (counts.created_nulls, counts.modified_cells, counts.excluded_rows) == (2, 2, 0)


def test_tokens_require_text_columns() -> None:
    frame = attach_lineage(pl.DataFrame({"n": pl.Series([1, None], dtype=pl.Int64)}))
    with pytest.raises(ApplicationError) as error:
        normalize_null_tokens(frame, ["n"], ["1"])
    assert error.value.code == "COLUMN_TYPE_MISMATCH"


@pytest.mark.parametrize(
    "tokens",
    [[], [""], ["NA", "NA"], ["x" * 101], [str(index) for index in range(21)]],
)
def test_token_parameters_are_explicit_and_bounded(tokens: list[str]) -> None:
    with pytest.raises(ValidationError):
        NormalizeNullTokensParameters.model_validate({"column_ids": [COLUMN], "tokens": tokens})


def sales() -> pl.DataFrame:
    return attach_lineage(
        pl.DataFrame(
            {
                "^id$": ["a", "b", "a", None, "b", None, "c"],
                "importe": pl.Series(
                    [Decimal("1.00"), Decimal("2.00"), Decimal("1.00"), None, Decimal("3.00")]
                    + [None, Decimal("1.00")],
                    dtype=pl.Decimal(38, 2),
                ),
            }
        )
    )


def test_deduplicate_keeps_first_appearance_in_table_order() -> None:
    result = deduplicate(sales(), ["^id$", "importe"], ["i", "m"], "group_nulls")
    # (a,1.00) repetido en 3; (None,None) repetido en 6; (b,3.00) distinto de (b,2.00).
    assert result.get_column(SOURCE_ROW).to_list() == [1, 2, 4, 5, 7]
    only_id = deduplicate(sales(), ["^id$"], ["i"], "group_nulls")
    assert only_id.get_column(SOURCE_ROW).to_list() == [1, 2, 4, 7]
    typed = deduplicate(sales(), ["importe"], ["m"], "group_nulls")
    assert typed.get_column(SOURCE_ROW).to_list() == [1, 2, 4, 5]


def test_reject_fails_on_null_keys_and_lists_them() -> None:
    with pytest.raises(ApplicationError) as error:
        deduplicate(sales(), ["^id$", "importe"], ["i", "m"], "reject")
    assert error.value.code == "NULL_KEY_REJECTED"
    assert error.value.details == {
        "total": 2,
        "samples": [
            {
                "column_id": "i",
                "column": "^id$",
                "source_row": row,
                "value": None,
                "reason": "null_key",
                "message": "La clave de deduplicación tiene un valor nulo.",
            }
            for row in (4, 6)
        ],
    }


def test_reject_without_null_keys_equals_group_nulls() -> None:
    frame = sales().filter(pl.col(SOURCE_ROW).is_in([1, 2, 3, 5, 7]))
    rejected = deduplicate(frame, ["^id$"], ["i"], "reject")
    grouped = deduplicate(frame, ["^id$"], ["i"], "group_nulls")
    assert rejected.equals(grouped)
    assert rejected.get_column(SOURCE_ROW).to_list() == [1, 2, 7]


def test_deduplicate_effect_is_exact_and_deterministic() -> None:
    frame = attach_lineage(pl.DataFrame({"k": ["x", "y", "x", "x", "z"], "v": list("abcde")}))
    first = deduplicate(frame, ["k"], ["c0"], "reject")
    second = deduplicate(frame, ["k"], ["c0"], "reject")
    columns = text_columns(frame)
    counts, samples, lineage, lineage_sha = effect(frame, first, columns)
    assert (counts.input_rows, counts.output_rows, counts.excluded_rows) == (5, 3, 2)
    assert counts.modified_cells == 0
    assert [(s.source_row, s.change) for s in samples] == [(3, "excluded"), (4, "excluded")]
    assert lineage.get_column("source_row").to_list() == [1, 2, 5]
    assert effect(frame, second, columns)[3] == lineage_sha
    assert table_digest(columns, first.drop(SOURCE_ROW)) == table_digest(
        columns, second.drop(SOURCE_ROW)
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"column_ids": [COLUMN]},  # null_keys es obligatorio: sin valor implícito
        {"column_ids": [COLUMN], "null_keys": "drop"},
        {"column_ids": [COLUMN], "null_keys": "reject", "keep": "last"},
        {"column_ids": [], "null_keys": "reject"},
        {"column_ids": [COLUMN, COLUMN], "null_keys": "reject"},
    ],
)
def test_deduplicate_parameters(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DeduplicateParameters.model_validate(parameters)
