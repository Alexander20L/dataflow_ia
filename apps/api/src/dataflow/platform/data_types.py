"""Tipos de columna del catálogo (sin dependencias: lo usan dominios puros como planning)."""

from typing import Literal

DataType = Literal["string", "integer", "decimal", "date", "boolean"]
ALL_TYPES: frozenset[DataType] = frozenset({"string", "integer", "decimal", "date", "boolean"})
TEXT: frozenset[DataType] = frozenset({"string"})
NUMERIC: frozenset[DataType] = frozenset({"integer", "decimal"})
MAX_DECIMAL_PRECISION = 38
MAX_DECIMAL_SCALE = 12
