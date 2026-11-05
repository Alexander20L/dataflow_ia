"""Conversión de texto a tipos del catálogo (cleaning.cast@1). Puro: sin Polars ni SQL.

Gramáticas exactas del contrato de ejecución §3. No se recortan espacios ni se aceptan
variantes regionales: un valor que no cumple la gramática es un error de conversión con motivo.
La política de errores es estricta: quien llama decide que un solo error hace fallar el plan.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from dataflow.platform.data_types import MAX_DECIMAL_PRECISION, MAX_DECIMAL_SCALE

CastType = Literal["integer", "decimal", "date", "boolean"]
CastFormat = Literal["integer_ascii", "decimal_dot", "iso_date", "boolean_lowercase"]
FORMATS: dict[CastType, CastFormat] = {
    "integer": "integer_ascii",
    "decimal": "decimal_dot",
    "date": "iso_date",
    "boolean": "boolean_lowercase",
}
Reason = Literal[
    "whitespace",
    "exponent",
    "leading_zero",
    "invalid_format",
    "out_of_range",
    "precision_exceeded",
    "invalid_date",
    "invalid_boolean",
]
REASONS: dict[Reason, str] = {
    "whitespace": "Tiene espacios en los bordes; añade un paso «Recortar espacios» antes.",
    "exponent": "Usa notación exponencial, que este formato no admite.",
    "leading_zero": "Tiene ceros a la izquierda; puede ser un código y no un número.",
    "invalid_format": "No cumple el formato elegido.",
    "out_of_range": "Está fuera del rango de enteros de 64 bits.",
    "precision_exceeded": "Supera 38 dígitos de precisión con la escala elegida.",
    "invalid_date": "No es una fecha válida del calendario (años 0001 a 9999).",
    "invalid_boolean": "Sólo se admiten «true» y «false» en minúsculas.",
}

INTEGER = re.compile(r"[+-]?(0|[1-9][0-9]*)", re.ASCII)
DECIMAL = re.compile(r"[+-]?(0|[1-9][0-9]*)(\.[0-9]+)?", re.ASCII)
LEADING_ZERO = re.compile(r"[+-]?0[0-9]+(\.[0-9]+)?", re.ASCII)
EXPONENT = re.compile(r"[+-]?[0-9]+(\.[0-9]+)?[eE][+-]?[0-9]+", re.ASCII)
ISO_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", re.ASCII)
INT64 = (-(2**63), 2**63 - 1)


@dataclass(frozen=True)
class Converted:
    value: int | Decimal | date | bool
    rounded: bool = False


@dataclass(frozen=True)
class Failed:
    reason: Reason


def number_reason(text: str) -> Reason:
    if text != text.strip():
        return "whitespace"
    if EXPONENT.fullmatch(text):
        return "exponent"
    if LEADING_ZERO.fullmatch(text):
        return "leading_zero"
    return "invalid_format"


def to_integer(text: str) -> Converted | Failed:
    if not INTEGER.fullmatch(text):
        return Failed(number_reason(text))
    value = int(text)
    if not INT64[0] <= value <= INT64[1]:
        return Failed("out_of_range")
    return Converted(value)


def to_decimal(text: str, scale: int) -> Converted | Failed:
    if not 0 <= scale <= MAX_DECIMAL_SCALE:
        raise ValueError("Escala fuera de 0..12")
    if not DECIMAL.fullmatch(text):
        return Failed(number_reason(text))
    original = Decimal(text)  # Construcción exacta, sin contexto.
    exponent = original.as_tuple().exponent
    assert isinstance(exponent, int)
    integer_digits = max(len(original.as_tuple().digits) + exponent, 0)
    if integer_digits + scale > MAX_DECIMAL_PRECISION:
        return Failed("precision_exceeded")
    with localcontext() as context:
        context.prec = 2 * MAX_DECIMAL_PRECISION
        quantized = original.quantize(Decimal(1).scaleb(-scale), rounding="ROUND_HALF_EVEN")
    if len(quantized.as_tuple().digits) > MAX_DECIMAL_PRECISION:
        return Failed("precision_exceeded")
    if quantized.is_zero():
        quantized = abs(quantized)  # Sin cero negativo.
    return Converted(quantized, rounded=quantized != original)


def to_date(text: str) -> Converted | Failed:
    match = ISO_DATE.fullmatch(text)
    if not match:
        return Failed("whitespace" if text != text.strip() else "invalid_format")
    year, month, day = (int(part) for part in match.groups())
    try:
        if year < 1:
            raise ValueError
        return Converted(date(year, month, day))
    except ValueError:
        return Failed("invalid_date")


def to_boolean(text: str) -> Converted | Failed:
    if text == "true":
        return Converted(True)
    if text == "false":
        return Converted(False)
    return Failed("whitespace" if text != text.strip() else "invalid_boolean")


def convert(text: str, type: CastType, scale: int | None = None) -> Converted | Failed:
    if type == "integer":
        return to_integer(text)
    if type == "decimal":
        if scale is None:
            raise ValueError("La conversión decimal requiere escala")
        return to_decimal(text, scale)
    if type == "date":
        return to_date(text)
    return to_boolean(text)
