from uuid import uuid4

import polars as pl
import pytest
from pydantic import ValidationError

from dataflow.modules.cleaning.contracts import (
    EffectCounts,
    EffectManifest,
    FilterRowsParameters,
    TrimWhitespaceParameters,
)
from dataflow.modules.cleaning.domain import check_counts, effect_sha256, require_same_effect
from dataflow.modules.cleaning.infrastructure import (
    SOURCE_ROW,
    attach_lineage,
    effect,
    filter_rows,
    table_digest,
    trim_whitespace,
)
from dataflow.modules.planning.public import COLUMN_REF
from dataflow.platform.errors import ApplicationError

COLUMNS = [
    {"id": "c-id", "name": "id", "ordinal": 0},
    {"id": "c-nombre", "name": "nombre", "ordinal": 1},
    {"id": "c-importe", "name": "importe", "ordinal": 2},
]


def table() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id": ["001", "002", "003", "004", "005", "006"],
            "nombre": ["  Ana ", None, " \t\r\n", " Bea ", "ñandú\t", "Luis"],
            "importe": ["10", None, " ", "007", None, "  "],
        },
        schema={"id": pl.String, "nombre": pl.String, "importe": pl.String},
    )


def test_trim_strips_only_sp_tab_cr_lf_keeps_nulls_and_creates_explicit_nulls() -> None:
    result = trim_whitespace(attach_lineage(table()), ["nombre", "importe"])
    assert result.get_column("nombre").to_list() == [
        "Ana",
        None,  # nulo original: sigue nulo
        None,  # sólo espacios/TAB/CR/LF → nulo creado
        " Bea ",  # NBSP no es parte de SP/TAB/CR/LF: se conserva (Unicode)
        "ñandú",
        "Luis",
    ]
    assert result.get_column("importe").to_list() == ["10", None, None, "007", None, None]
    assert result.get_column("id").to_list() == table().get_column("id").to_list()
    assert result.get_column(SOURCE_ROW).to_list() == [1, 2, 3, 4, 5, 6]


def test_trim_preserves_leading_zeros_and_types() -> None:
    frame = pl.DataFrame({"codigo": [" 0007 ", "00", "0 0"]})
    result = trim_whitespace(attach_lineage(frame), ["codigo"])
    assert result.get_column("codigo").to_list() == ["0007", "00", "0 0"]
    assert result.schema["codigo"] == pl.String


@pytest.mark.parametrize(
    ("predicate", "match", "kept"),
    [
        ("is_null", "any", ["001", "003", "004", "006"]),
        ("is_null", "all", ["001", "003", "004", "005", "006"]),
        ("is_whitespace_only", "any", ["001", "002", "004", "005"]),
        ("is_whitespace_only", "all", ["001", "002", "004", "005", "006"]),
    ],
)
def test_filter_rows_excludes_matches_and_preserves_order(
    predicate: str, match: str, kept: list[str]
) -> None:
    result = filter_rows(attach_lineage(table()), ["nombre", "importe"], predicate, match)  # type: ignore[arg-type]
    assert result.get_column("id").to_list() == kept
    assert result.get_column(SOURCE_ROW).to_list() == [int(value) for value in kept]


def test_effect_counts_samples_and_lineage_for_a_chain() -> None:
    source = table()
    result = filter_rows(
        trim_whitespace(attach_lineage(source), ["nombre", "importe"]),
        ["nombre"],
        "is_null",
        "any",
    )
    counts, samples, lineage, lineage_hash = effect(source, result, COLUMNS)
    # Filas 2 (nombre nulo original) y 3 (nombre sólo espacios → nulo) se excluyen.
    assert counts == EffectCounts(
        input_rows=6,
        output_rows=4,
        excluded_rows=2,
        modified_rows=3,  # filas 1 (nombre), 5 (nombre) y 6 (importe)
        modified_cells=3,
        created_nulls=1,  # importe de la fila 6 ("  " → nulo); la 3 se excluye
    )
    check_counts(counts)
    assert [(s.source_row, s.change) for s in samples] == [
        (1, "modified"),
        (2, "excluded"),
        (3, "excluded"),
        (5, "modified"),
        (6, "modified"),
    ]
    assert samples[0].before == {"c-nombre": "  Ana "} and samples[0].after == {"c-nombre": "Ana"}
    assert samples[-1].before == {"c-importe": "  "} and samples[-1].after == {"c-importe": None}
    assert samples[1].after is None and samples[1].before["c-id"] == "002"
    assert lineage.get_column("source_row").to_list() == [1, 4, 5, 6]
    assert lineage.get_column("output_row").to_list() == [1, 2, 3, 4]
    assert effect(source, result, COLUMNS)[3] == lineage_hash  # determinista


def test_unchanged_table_has_empty_effect() -> None:
    source = pl.DataFrame({"id": ["1", "2"], "nombre": ["a", None], "importe": ["x", "y"]})
    counts, samples, _, _ = effect(
        source, trim_whitespace(attach_lineage(source), ["nombre"]), COLUMNS
    )
    assert counts.modified_cells == counts.excluded_rows == counts.created_nulls == 0
    assert samples == []


def test_samples_are_capped_but_counts_use_the_full_dataset() -> None:
    source = pl.DataFrame({"id": [str(i) for i in range(120)], "nombre": [" x"] * 120})
    columns = COLUMNS[:2]
    counts, samples, _, _ = effect(
        source, trim_whitespace(attach_lineage(source), ["nombre"]), columns
    )
    assert counts.modified_rows == counts.modified_cells == 120
    assert len(samples) == 50 and samples[-1].source_row == 50


def test_column_names_are_never_interpreted_as_expressions() -> None:
    frame = pl.DataFrame({"^id$": [" a "], "*": [" b "]})
    result = trim_whitespace(attach_lineage(frame), ["^id$", "*"])
    assert result.row(0)[:2] == ("a", "b")


def test_reserved_lineage_column_and_unknown_columns_are_rejected() -> None:
    with pytest.raises(ApplicationError, match="reservada"):
        attach_lineage(pl.DataFrame({SOURCE_ROW: ["1"]}))
    with pytest.raises(ApplicationError) as error:
        trim_whitespace(attach_lineage(table()), ["missing"])
    assert error.value.code == "UNKNOWN_COLUMN"


def test_parameters_reference_columns_by_id_and_reject_duplicates() -> None:
    column = uuid4()
    assert TrimWhitespaceParameters(column_ids=[column]).column_ids == [column]
    schema = FilterRowsParameters.model_json_schema()["properties"]
    assert schema["column_ids"][COLUMN_REF] is True
    assert TrimWhitespaceParameters.model_json_schema()["properties"]["column_ids"][COLUMN_REF]
    with pytest.raises(ValidationError):
        TrimWhitespaceParameters(column_ids=[column, column])
    with pytest.raises(ValidationError):
        TrimWhitespaceParameters(column_ids=[])
    with pytest.raises(ValidationError):
        FilterRowsParameters.model_validate({"column_ids": [str(column)], "predicate": "is_zero"})
    assert FilterRowsParameters(column_ids=[column], predicate="is_null").match == "any"


def manifest(**changes: object) -> EffectManifest:
    values: dict[str, object] = {
        "plan": {"revision_id": "r", "content_sha256": "a" * 64},
        "input": {"artifact_id": "t", "artifact_sha256": "b" * 64},
        "semantic_ref": None,
        "config_sha256": "c" * 64,
        "environment_sha256": "d" * 64,
        "output": {"columns": COLUMNS, "logical_content_sha256": "e" * 64},
        "row_lineage_sha256": "f" * 64,
        "counts": EffectCounts(
            input_rows=2,
            output_rows=2,
            excluded_rows=0,
            modified_rows=1,
            modified_cells=1,
            created_nulls=0,
        ),
    }
    return EffectManifest.model_validate({**values, **changes})


def test_effect_hash_is_canonical_and_sensitive_to_every_field() -> None:
    base = effect_sha256(manifest())
    assert base == effect_sha256(manifest())
    assert base != effect_sha256(manifest(environment_sha256="0" * 64))
    assert base != effect_sha256(manifest(semantic_ref={"id": "s", "revision": 1}))
    require_same_effect(base, base)
    with pytest.raises(ApplicationError) as error:
        require_same_effect(base, effect_sha256(manifest(config_sha256="1" * 64)))
    assert error.value.code == "PREVIEW_EFFECT_MISMATCH"
    assert "vista previa nueva" in error.value.message


def test_table_digest_depends_on_values_and_order() -> None:
    frame = table()
    assert table_digest(COLUMNS, frame) == table_digest(COLUMNS, frame.clone())
    assert table_digest(COLUMNS, frame) != table_digest(COLUMNS, frame.reverse())


def test_incoherent_counts_are_rejected() -> None:
    with pytest.raises(ApplicationError):
        check_counts(
            EffectCounts(
                input_rows=3,
                output_rows=3,
                excluded_rows=1,
                modified_rows=0,
                modified_cells=0,
                created_nulls=0,
            )
        )
