"""Periodos de negocio puros (sin Polars ni contratos): inicio, fin, etiqueta y desplazamiento.

Semanas ISO 8601: empiezan en lunes y pertenecen al año ISO (2025-12-29 es 2026-W01). Un
desplazamiento que no tiene equivalente (29 de febrero o semana 53 el año anterior, o antes del
año 1) devuelve None: nunca se sustituye por un periodo vecino.
"""

import calendar
from datetime import date, timedelta
from typing import Literal

TimeGrain = Literal["day", "week", "month", "quarter", "year"]
ComparisonKind = Literal["previous_period", "same_period_last_year"]
GRAIN_NAMES: dict[str, str] = {
    "day": "un día",
    "week": "una semana ISO",
    "month": "un mes",
    "quarter": "un trimestre",
    "year": "un año",
}


def period(value: date, grain: TimeGrain) -> tuple[date, str]:
    """Inicio y etiqueta del periodo de negocio que contiene `value`."""
    if grain == "day":
        return value, value.isoformat()
    if grain == "week":
        year, week, _ = value.isocalendar()
        return value - timedelta(days=value.weekday()), f"{year}-W{week:02d}"
    if grain == "month":
        return value.replace(day=1), f"{value.year}-{value.month:02d}"
    if grain == "quarter":
        quarter = (value.month - 1) // 3 + 1
        return date(value.year, 3 * quarter - 2, 1), f"{value.year}-Q{quarter}"
    return date(value.year, 1, 1), str(value.year)


def period_end(start: date, grain: TimeGrain) -> date:
    """Último día del periodo que empieza en `start` (inicio de periodo válido)."""
    if grain == "day":
        return start
    if grain == "week":
        return start + timedelta(days=6)
    if grain == "year":
        return date(start.year, 12, 31)
    last_month = start.month + (2 if grain == "quarter" else 0)
    return date(start.year, last_month, calendar.monthrange(start.year, last_month)[1])


def starts_period(value: date, grain: TimeGrain) -> bool:
    return period(value, grain)[0] == value


def ends_period(value: date, grain: TimeGrain) -> bool:
    return period_end(period(value, grain)[0], grain) == value


def _months_back(start: date, months: int) -> date:
    index = start.year * 12 + (start.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def shift(start: date, grain: TimeGrain, kind: ComparisonKind) -> date | None:
    """Inicio del periodo base con el que se compara el periodo que empieza en `start`."""
    try:
        if kind == "previous_period":
            if grain == "day":
                return start - timedelta(days=1)
            if grain == "week":
                return start - timedelta(days=7)
            months = {"month": 1, "quarter": 3, "year": 12}[grain]
            return _months_back(start, months)
        if grain == "week":
            year, week, _ = start.isocalendar()
            return date.fromisocalendar(year - 1, week, 1)  # semana 53 sin equivalente: None
        return start.replace(year=start.year - 1)  # 29 de febrero sin equivalente: None
    except (ValueError, OverflowError):
        return None
