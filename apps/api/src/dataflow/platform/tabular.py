"""Tipos de columna admitidos y representación canónica de celdas (contrato de ejecución §6).

Único lugar que define cómo se escribe una celda tipada en el hash lógico `table` y en las
vistas: enteros y decimales como cadenas canónicas, fechas ISO, booleanos JSON. Las celdas de
texto se conservan literalmente, de modo que el hash de las tablas de texto no cambia.
"""

from datetime import date
from decimal import Decimal
from typing import Any, cast

import polars as pl

from dataflow.platform.canonical import digest
from dataflow.platform.data_types import MAX_DECIMAL_PRECISION, MAX_DECIMAL_SCALE, DataType
from dataflow.platform.decimal_context import exact_context
from dataflow.platform.errors import ApplicationError

Cell = str | int | Decimal | date | bool | None


def column_type(dtype: pl.DataType) -> tuple[DataType, dict[str, Any]]:
    """Tipo de catálogo de una columna Parquet; cualquier otro tipo físico se rechaza."""
    if dtype == pl.String:
        return "string", {}
    if dtype == pl.Int64:
        return "integer", {}
    if isinstance(dtype, pl.Decimal):
        if dtype.precision == MAX_DECIMAL_PRECISION and 0 <= dtype.scale <= MAX_DECIMAL_SCALE:
            return "decimal", {"scale": dtype.scale}
    elif dtype == pl.Date:
        return "date", {}
    elif dtype == pl.Boolean:
        return "boolean", {}
    raise ApplicationError(
        "UNSUPPORTED_COLUMN_TYPE",
        "La tabla contiene un tipo de columna que este motor no admite.",
        422,
    )


def frame_types(frame: pl.DataFrame) -> list[tuple[DataType, dict[str, Any]]]:
    return [column_type(dtype) for dtype in frame.dtypes]


def canonical_decimal(value: Decimal, scale: int) -> str:
    # Contexto amplio: el de Python (28 dígitos) no basta para Decimal(38, s).
    with exact_context():
        quantized = value.quantize(Decimal(1).scaleb(-scale), rounding="ROUND_HALF_EVEN")
    if quantized.is_zero():
        quantized = abs(quantized)  # Sin cero negativo.
    return format(quantized, "f")


def canonical_cell(value: Cell, data_type: DataType, parameters: dict[str, Any]) -> Any:
    """Valor de la celda en el payload canónico del hash `table`."""
    if value is None or data_type == "string":
        return value
    if data_type == "boolean":
        return bool(value)
    return display_cell(value, data_type, parameters)


def display_cell(value: Cell, data_type: DataType, parameters: dict[str, Any]) -> str | None:
    """Cadena canónica de una celda para vistas, ejemplos y comparaciones."""
    if value is None:
        return None
    if data_type == "string":
        return cast(str, value)
    if data_type == "integer":
        return str(int(cast(int, value)))
    if data_type == "decimal":
        return canonical_decimal(cast(Decimal, value), int(parameters["scale"]))
    if data_type == "date":
        return cast(date, value).isoformat()
    return "true" if value else "false"


def table_logical_sha256(columns: list[dict[str, Any]], frame: pl.DataFrame) -> str:
    """Hash lógico `table` (§6): esquema de columnas y filas en orden, celdas canónicas."""
    types = [
        (cast(DataType, column.get("technical_type", "string")), column.get("type_parameters", {}))
        for column in columns
    ]
    if [str(column["name"]) for column in columns] != frame.columns or types != frame_types(frame):
        raise ApplicationError(
            "SCHEMA_MISMATCH", "El esquema declarado no coincide con la tabla.", 409
        )
    if all(data_type == "string" for data_type, _ in types):
        rows: list[list[Any]] = [list(row) for row in frame.iter_rows()]
    else:
        rows = [
            [
                canonical_cell(cell, data_type, parameters)
                for cell, (data_type, parameters) in zip(row, types, strict=True)
            ]
            for row in frame.iter_rows()
        ]
    return digest("table", {"columns": columns, "rows": rows})
