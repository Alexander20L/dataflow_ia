"""Lectura de valores regionales (Fase 18, regla `regional-values-v1`). Puro: sin Polars ni SQL.

Al leer un archivo, una columna de texto cuyos valores **todos** cumplen un único formato
regional se reescribe en la celda canónica (número con punto decimal, fecha ISO). Es una lectura
sin pérdida: el original no cambia y el valor es el mismo. Ante la duda no se reescribe nada y la
columna queda como texto, con su motivo.

Números:
- `decimal_comma`: coma decimal y punto de miles opcional (`1.234,56`, `0,5`).
- `decimal_point_grouped`: punto decimal y coma de miles (`1,234.56`).
- Un valor que admite dos lecturas con resultado distinto (`1.234`, `1,234`) se decide por la
  convención del archivo (otras columnas sin ambigüedad), sólo en CSV y sólo si no hay columnas
  con convenciones opuestas. Una columna que ya está en el formato canónico y no tiene otra
  lectura decidida por el archivo no cambia.
- Sin ceros a la izquierda (pueden ser códigos), sin símbolos de moneda, porcentajes ni espacios.

Fechas: `dd/mm/aaaa`, `mm/dd/aaaa` (separadores `/`, `-` o `.`) y `aaaa/mm/dd`. Día y mes se
distinguen sólo si algún valor lo prueba (un número mayor que 12); si ambas lecturas son válidas
y dan fechas distintas, la columna queda como texto.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Literal

RULE = "regional-values-v1"

Convention = Literal["decimal_comma", "decimal_point_grouped"]
DateOrder = Literal["day_month_year", "month_day_year", "year_month_day"]
ValueFormat = Literal[
    "decimal_comma", "decimal_point_grouped", "day_month_year", "month_day_year", "year_month_day"
]

CANONICAL = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?\Z", re.ASCII)
COMMA = re.compile(r"([-+]?)((?:0|[1-9]\d*)|[1-9]\d{0,2}(?:\.\d{3})+)(?:,(\d+))?\Z", re.ASCII)
POINT = re.compile(r"([-+]?)((?:0|[1-9]\d*)|[1-9]\d{0,2}(?:,\d{3})+)(?:\.(\d+))?\Z", re.ASCII)
DAY_FIRST = re.compile(r"(\d{1,2})([/.-])(\d{1,2})\2(\d{4})\Z", re.ASCII)
YEAR_FIRST = re.compile(r"(\d{4})([/.])(\d{1,2})\2(\d{1,2})\Z", re.ASCII)
ISO = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)

LABELS: dict[ValueFormat, str] = {
    "decimal_comma": "coma decimal y punto de miles",
    "decimal_point_grouped": "punto decimal y coma de miles",
    "day_month_year": "día/mes/año",
    "month_day_year": "mes/día/año",
    "year_month_day": "año/mes/día",
}


@dataclass(frozen=True)
class Converted:
    column: int
    kind: Literal["number", "date"]
    format: ValueFormat
    values: int
    by_file_convention: bool = False


@dataclass(frozen=True)
class Kept:
    """Columna que parecía regional pero se deja como texto: motivo en español."""

    column: int
    kind: Literal["number", "date"]
    reason: str


@dataclass(frozen=True)
class Reading:
    rows: list[list[str | None]]
    converted: list[Converted]
    kept: list[Kept]
    convention: Convention | None


def number(value: str, convention: Convention) -> str | None:
    """Valor canónico (punto decimal, sin miles) o None si no cumple la gramática."""
    match = (COMMA if convention == "decimal_comma" else POINT).fullmatch(value)
    if match is None:
        return None
    sign, whole, fraction = match.groups()
    whole = whole.replace("." if convention == "decimal_comma" else ",", "")
    text = f"{'-' if sign == '-' else ''}{whole}{'.' + fraction if fraction else ''}"
    return text if CANONICAL.fullmatch(text) else None


def calendar(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat() if year >= 1 else None
    except ValueError:
        return None


def as_date(value: str, order: DateOrder) -> str | None:
    if order == "year_month_day":
        match = YEAR_FIRST.fullmatch(value)
        if match is None:
            return None
        return calendar(int(match[1]), int(match[3]), int(match[4]))
    match = DAY_FIRST.fullmatch(value)
    if match is None:
        return None
    first, second, year = int(match[1]), int(match[3]), int(match[4])
    if order == "day_month_year":
        return calendar(year, second, first)
    return calendar(year, first, second)


def all_parse(values: list[str], parse: Callable[[str], str | None]) -> list[str] | None:
    result: list[str] = []
    for value in values:
        converted = parse(value)
        if converted is None:
            return None
        result.append(converted)
    return result


def numeric_readings(values: list[str]) -> dict[str, list[str]]:
    """Lecturas completas posibles de una columna: canónica y regionales."""
    readings: dict[str, list[str]] = {}
    if all(CANONICAL.fullmatch(v) for v in values):
        readings["canonical"] = list(values)
    conventions: tuple[Convention, ...] = ("decimal_comma", "decimal_point_grouped")
    for convention in conventions:
        parsed = all_parse(values, partial(number, convention=convention))
        if parsed is not None:
            readings[convention] = parsed
    return readings


def decisive(readings: dict[str, list[str]]) -> Convention | None:
    """Convención que una columna prueba por sí sola: sólo una lectura válida y no canónica."""
    if len(readings) == 1:
        (only,) = readings
        if only != "canonical":
            return only  # type: ignore[return-value]
    return None


def read_values(rows: Sequence[Sequence[str | None]], file_convention: bool) -> Reading:
    """Aplica `regional-values-v1` a una tabla de texto. `file_convention` sólo en CSV: en Excel
    los números nativos ya son canónicos y no deben reinterpretarse."""
    width = len(rows[0]) if rows else 0
    columns = [[row[i] for row in rows] for i in range(width)]
    present = [[v for v in column if v is not None] for column in columns]
    numeric = [numeric_readings(values) if values else {} for values in present]
    found = {decisive(readings) for readings in numeric} - {None}
    convention: Convention | None = (
        next(iter(found)) if file_convention and len(found) == 1 else None
    )
    converted: list[Converted] = []
    kept: list[Kept] = []
    output = [list(row) for row in rows]
    for index, values in enumerate(present):
        if not values:
            continue
        readings = numeric[index]
        mapping: dict[str, str] | None = None
        if readings:
            outcomes = {tuple(result) for result in readings.values()}
            chosen: str | None = None
            by_convention = False
            if len(outcomes) == 1:
                chosen = "canonical" if "canonical" in readings else next(iter(readings))
            elif convention is not None and convention in readings:
                chosen, by_convention = convention, True
            elif "canonical" in readings:
                chosen = "canonical"
            else:
                kept.append(
                    Kept(
                        index,
                        "number",
                        "Admite dos lecturas (coma o punto como separador decimal) que dan "
                        "cifras distintas y el archivo no lo aclara: se deja como texto.",
                    )
                )
                continue
            if chosen != "canonical":
                mapping = dict(zip(values, readings[chosen], strict=True))
                converted.append(
                    Converted(
                        index,
                        "number",
                        chosen,  # type: ignore[arg-type]
                        sum(1 for v in values if mapping[v] != v),
                        by_convention,
                    )
                )
        else:
            mapping = dates(index, values, converted, kept)
        if mapping:
            for row in output:
                cell = row[index]
                if cell is not None:
                    row[index] = mapping[cell]
    return Reading(output, converted, kept, convention)


def dates(
    index: int, values: list[str], converted: list[Converted], kept: list[Kept]
) -> dict[str, str] | None:
    if all(ISO.fullmatch(v) for v in values):
        return None
    options: dict[DateOrder, list[str]] = {}
    orders: tuple[DateOrder, ...] = ("day_month_year", "month_day_year", "year_month_day")
    for order in orders:
        parsed = all_parse(values, partial(as_date, order=order))
        if parsed is not None:
            options[order] = parsed
    if not options:
        return None
    outcomes = {tuple(result) for result in options.values()}
    if len(outcomes) > 1:
        kept.append(
            Kept(
                index,
                "date",
                "Ningún valor tiene un día mayor que 12: puede ser día/mes o mes/día y darían "
                "fechas distintas, así que se deja como texto.",
            )
        )
        return None
    order = next(iter(options))
    mapping = dict(zip(values, options[order], strict=True))
    converted.append(Converted(index, "date", order, sum(1 for v in values if mapping[v] != v)))
    return mapping
