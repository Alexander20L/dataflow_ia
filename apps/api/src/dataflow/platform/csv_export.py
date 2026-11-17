"""Serialización CSV fija y documentada (Fase 9).

Dos perfiles; el **estándar** no cambia nunca porque es el que garantiza la ida y vuelta con la
ingesta:

| | estándar | excel_regional |
|---|---|---|
| codificación | UTF-8 sin BOM | UTF-8 con BOM (Excel lo usa para detectar UTF-8) |
| separador / fin de línea | `,` / `\\n` | `;` / `\\r\\n` |
| comillas | `"` sólo si hace falta (RFC 4180; `""` dentro) | igual |
| nulos | campo vacío (la ingesta lee vacío como nulo) | igual |
| decimales | punto (celda canónica de la Fase 6) | coma decimal en columnas decimales |
| fechas / booleanos | ISO 8601 / `true` `false` | igual |
| cabecera | nombres de columna | igual |
| texto que empieza por `= + - @` | sin cambios | prefijo `'` (Excel no lo ejecuta como fórmula) |

Una fila nula de una sola columna se escribe como `""` (el escritor de `csv` lo hace): la
ingesta salta las líneas en blanco.
"""

import csv
import io
from collections.abc import Sequence
from typing import Any, Literal, cast

import polars as pl

from dataflow.platform.data_types import DataType
from dataflow.platform.tabular import display_cell

CsvProfile = Literal["standard", "excel_regional"]
PROFILES: tuple[CsvProfile, ...] = ("standard", "excel_regional")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def write_csv(
    header: Sequence[str],
    rows: Sequence[Sequence[str | None]],
    profile: CsvProfile,
    decimal_columns: frozenset[int] = frozenset(),
    text_columns: frozenset[int] | None = None,
) -> bytes:
    """Cabecera y filas de cadenas canónicas (None = nulo) en el perfil elegido.

    `decimal_columns`: índices con decimales canónicos (coma en Excel regional). `text_columns`:
    índices de texto libre (se neutralizan fórmulas en Excel regional); por defecto, ninguno."""
    regional = profile == "excel_regional"
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=";" if regional else ",",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n" if regional else "\n",
    )
    writer.writerow(header)
    texts = text_columns or frozenset()
    for row in rows:
        out: list[str] = []
        for index, value in enumerate(row):
            if value is None:
                out.append("")
            elif regional and index in decimal_columns:
                out.append(value.replace(".", ","))
            elif regional and index in texts and value.startswith(FORMULA_PREFIXES):
                out.append("'" + value)
            else:
                out.append(value)
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8-sig" if regional else "utf-8")


def table_csv(content: bytes, columns: list[dict[str, Any]], profile: CsvProfile) -> bytes:
    """Tabla publicada (Parquet) como CSV: celdas canónicas de la Fase 6 por tipo."""
    frame = pl.read_parquet(io.BytesIO(content))
    names = [str(c["name"]) for c in columns]
    frame = frame.select(names)
    kinds = [cast(DataType, c.get("technical_type", "string")) for c in columns]
    params = [dict(c.get("type_parameters", {})) for c in columns]
    rows = [
        [
            display_cell(value, kinds[i], params[i]) if value is not None else None
            for i, value in enumerate(row)
        ]
        for row in frame.iter_rows()
    ]
    return write_csv(
        names,
        rows,
        profile,
        decimal_columns=frozenset(i for i, k in enumerate(kinds) if k == "decimal"),
        text_columns=frozenset(i for i, k in enumerate(kinds) if k == "string"),
    )
