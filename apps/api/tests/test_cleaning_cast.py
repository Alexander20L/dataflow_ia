"""Fase 6 · A3: cleaning.cast@1 (gramáticas exactas del contrato de ejecución §3)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError

from dataflow.modules.cleaning.contracts import CastParameters
from dataflow.modules.cleaning.conversion import Converted, Failed, convert
from dataflow.modules.cleaning.engine import IsolatedCleaner
from dataflow.modules.cleaning.infrastructure import (
    SOURCE_ROW,
    attach_lineage,
    cast_column,
    filter_rows,
)
from dataflow.modules.executions.public import ProcessingConfig
from dataflow.platform.errors import ApplicationError

INT64_MAX = "9223372036854775807"


def outcome(text: str, type: Any, scale: int | None = None) -> Any:
    result = convert(text, type, scale)
    return result.reason if isinstance(result, Failed) else result.value


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("+0", 0),
        ("-0", 0),  # Salida canónica sin signo: 0.
        ("12", 12),
        ("-12", -12),
        (INT64_MAX, 2**63 - 1),
        ("-9223372036854775808", -(2**63)),
        ("9223372036854775808", "out_of_range"),
        ("-9223372036854775809", "out_of_range"),
        ("007", "leading_zero"),
        ("-007", "leading_zero"),
        ("00", "leading_zero"),
        ("1e5", "exponent"),
        ("1E+05", "exponent"),
        ("1.0", "invalid_format"),
        ("1,000", "invalid_format"),
        ("", "invalid_format"),
        ("+", "invalid_format"),
        (" 12", "whitespace"),
        ("12\t", "whitespace"),
        ("12 ", "whitespace"),  # NBSP: no se recorta; requiere un paso explícito.
        ("1 000", "invalid_format"),
        ("١٢", "invalid_format"),  # dígitos no ASCII
        ("１２", "invalid_format"),  # dígitos de ancho completo
    ],
)
def test_integer_ascii(text: str, expected: Any) -> None:
    assert outcome(text, "integer") == expected


def test_leading_zeros_never_become_integers_even_without_semantics() -> None:
    """Segunda línea de defensa para identificadores: aunque el plan no fije una revisión
    semántica (y por tanto la salvaguarda IDENTIFIER_CONVERSION_UNCONFIRMED no actúe), un código
    con ceros a la izquierda como «007» no cumple la gramática integer_ascii. Convertirlo
    perdería información («007» y «7» serían el mismo número), así que la conversión falla y
    el plan no publica nada."""
    frame = attach_lineage(pl.DataFrame({"codigo": ["7", "007", "12"]}))
    with pytest.raises(ApplicationError) as error:
        cast_column(frame, "codigo", "c-1", "integer", None)
    assert error.value.code == "CONVERSION_FAILED"
    assert error.value.details == {
        "total": 1,
        "samples": [
            {
                "column_id": "c-1",
                "column": "codigo",
                "source_row": 2,
                "value": "007",
                "reason": "leading_zero",
                "message": "Tiene ceros a la izquierda; puede ser un código y no un número.",
            }
        ],
    }
    assert outcome("007", "decimal", 0) == "leading_zero"


@pytest.mark.parametrize(
    ("text", "scale", "value", "rounded"),
    [
        ("1.5", 2, Decimal("1.50"), False),
        ("+1.50", 2, Decimal("1.50"), False),
        ("1.235", 2, Decimal("1.24"), True),  # HALF_EVEN: empate, 3 impar → 4
        ("1.245", 2, Decimal("1.24"), True),  # HALF_EVEN: empate, 4 par → se queda
        ("1.2451", 2, Decimal("1.25"), True),
        ("-0.001", 2, Decimal("0.00"), True),  # sin cero negativo
        ("-0", 2, Decimal("0.00"), False),
        ("99.995", 2, Decimal("100.00"), True),
        ("12", 0, Decimal("12"), False),
        ("0.5", 0, Decimal("0"), True),
        ("1.5", 0, Decimal("2"), True),
        ("9" * 38, 0, Decimal("9" * 38), False),
        ("0." + "1" * 50, 12, Decimal("0.111111111111"), True),
    ],
)
def test_decimal_dot_quantizes_half_even(
    text: str, scale: int, value: Decimal, rounded: bool
) -> None:
    result = convert(text, "decimal", scale)
    assert isinstance(result, Converted)
    assert (result.value, result.rounded) == (value, rounded)
    assert str(result.value) == str(value)  # misma escala y sin signo negativo en cero


@pytest.mark.parametrize(
    ("text", "scale", "reason"),
    [
        ("9" * 39, 0, "precision_exceeded"),
        ("9" * 37, 2, "precision_exceeded"),
        ("9" * 36 + ".995", 2, "precision_exceeded"),  # el redondeo añade un dígito entero
        ("1e5", 2, "exponent"),
        ("1.5e2", 2, "exponent"),
        (".5", 2, "invalid_format"),
        ("5.", 2, "invalid_format"),
        ("1,5", 2, "invalid_format"),
        ("007.5", 2, "leading_zero"),
        (" 1.5", 2, "whitespace"),
        ("NaN", 2, "invalid_format"),
        ("Infinity", 2, "invalid_format"),
    ],
)
def test_decimal_dot_rejections(text: str, scale: int, reason: str) -> None:
    assert outcome(text, "decimal", scale) == reason


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-02-28", date(2026, 2, 28)),
        ("2024-02-29", date(2024, 2, 29)),
        ("0001-01-01", date(1, 1, 1)),
        ("9999-12-31", date(9999, 12, 31)),
        ("2026-02-30", "invalid_date"),
        ("2023-02-29", "invalid_date"),
        ("2026-13-01", "invalid_date"),
        ("0000-01-01", "invalid_date"),
        ("2026-2-28", "invalid_format"),
        ("28/02/2026", "invalid_format"),
        ("2026-02-28T00:00", "invalid_format"),
        ("20260228", "invalid_format"),
        (" 2026-02-28", "whitespace"),
        ("２０２６-02-28", "invalid_format"),
    ],
)
def test_iso_date(text: str, expected: Any) -> None:
    assert outcome(text, "date") == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("true", True),
        ("false", False),
        ("TRUE", "invalid_boolean"),
        ("True", "invalid_boolean"),
        ("1", "invalid_boolean"),
        ("yes", "invalid_boolean"),
        (" true", "whitespace"),
    ],
)
def test_boolean_lowercase(text: str, expected: Any) -> None:
    assert outcome(text, "boolean") == expected


def test_cast_column_types_nulls_and_lineage() -> None:
    frame = attach_lineage(
        pl.DataFrame(
            {
                "importe": ["10.5", None, "-0.004"],
                "fecha": ["2026-02-28", "2024-02-29", None],
                "otra": ["a", "b", "c"],
            }
        )
    )
    result = cast_column(frame, "importe", "i", "decimal", 2)
    result = cast_column(result, "fecha", "f", "date", None)
    assert result.schema["importe"] == pl.Decimal(38, 2)
    assert result.schema["fecha"] == pl.Date and result.schema["otra"] == pl.String
    assert result.get_column("importe").to_list() == [Decimal("10.50"), None, Decimal("0.00")]
    assert result.get_column("fecha").to_list() == [date(2026, 2, 28), date(2024, 2, 29), None]
    assert result.get_column(SOURCE_ROW).to_list() == [1, 2, 3]
    assert result.columns == frame.columns


def test_failures_report_every_count_and_at_most_50_samples_with_source_rows() -> None:
    values = ["1"] + [f"x{index}" for index in range(120)] + ["TRUE"]
    frame = attach_lineage(pl.DataFrame({"^n$": [None, *values]}))
    # Un filtro previo excluye el registro 1: las filas del detalle son las de la tabla fijada.
    filtered = filter_rows(frame, ["^n$"], "is_null", "any")
    with pytest.raises(ApplicationError) as error:
        cast_column(filtered, "^n$", "n", "integer", None)
    details = error.value.details
    assert details is not None and details["total"] == 121
    samples = details["samples"]
    assert len(samples) == 50
    assert [sample["source_row"] for sample in samples] == list(range(3, 53))
    assert samples[0]["value"] == "x0" and samples[0]["reason"] == "invalid_format"


def test_long_values_are_truncated_in_the_detail() -> None:
    frame = attach_lineage(pl.DataFrame({"n": ["9" * 500]}))
    with pytest.raises(ApplicationError) as error:
        cast_column(frame, "n", "n", "integer", None)
    assert error.value.details is not None
    assert error.value.details["samples"][0]["value"] == "9" * 200
    assert error.value.details["samples"][0]["reason"] == "out_of_range"


def test_cast_requires_text_input() -> None:
    frame = attach_lineage(pl.DataFrame({"n": pl.Series([1, 2], dtype=pl.Int64)}))
    with pytest.raises(ApplicationError) as error:
        cast_column(frame, "n", "n", "integer", None)
    assert error.value.code == "COLUMN_TYPE_MISMATCH"


COLUMN = "6f0e7f43-1f0d-4f5e-8b5d-0b5b8d6b7c11"


@pytest.mark.parametrize(
    "parameters",
    [
        {"type": "integer", "format": "decimal_dot"},
        {"type": "date", "format": "iso_date", "scale": 0},
        {"type": "decimal", "format": "decimal_dot"},
        {"type": "decimal", "format": "decimal_dot", "scale": 13},
        {"type": "decimal", "format": "decimal_dot", "scale": -1},
        {"type": "float", "format": "decimal_dot"},
        {"type": "boolean", "format": "boolean_lowercase", "extra": True},
    ],
)
def test_incompatible_parameters_are_rejected(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CastParameters.model_validate({"column_id": COLUMN, **parameters})


def test_valid_parameters_keep_defaults_explicit() -> None:
    parsed = CastParameters.model_validate(
        {"column_id": COLUMN, "type": "decimal", "format": "decimal_dot", "scale": 2}
    )
    assert parsed.model_dump(mode="json") == {
        "column_id": COLUMN,
        "type": "decimal",
        "format": "decimal_dot",
        "scale": 2,
        "confirm_identifier_conversion": False,
    }


def test_isolated_cast_returns_structured_failures(tmp_path: Path) -> None:
    """El subproceso devuelve el detalle de los valores que no convierten."""
    frame = pl.DataFrame({"importe": ["1.5", "1,5", None]})
    source = tmp_path / "in.parquet"
    frame.write_parquet(source)
    cleaner = IsolatedCleaner(tmp_path)
    config = ProcessingConfig(max_rows=1000, max_columns=10, timeout_seconds=45)
    with pytest.raises(ApplicationError) as error:
        cleaner.cast(source.read_bytes(), "importe", "i", "decimal", 2, False, config, 45)
    assert error.value.code == "CONVERSION_FAILED"
    assert error.value.details == {
        "total": 1,
        "samples": [
            {
                "column_id": "i",
                "column": "importe",
                "source_row": 2,
                "value": "1,5",
                "reason": "invalid_format",
                "message": "No cumple el formato elegido.",
            }
        ],
    }
    ok = pl.DataFrame({"importe": ["1.5", None]})
    ok.write_parquet(source)
    converted = cleaner.cast(source.read_bytes(), "importe", "i", "decimal", 2, False, config, 45)
    result = pl.read_parquet(converted)
    assert result.schema["importe"] == pl.Decimal(38, 2)
    assert result.get_column(SOURCE_ROW).to_list() == [1, 2]
