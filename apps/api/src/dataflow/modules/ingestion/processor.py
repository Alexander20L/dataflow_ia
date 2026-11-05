"""Proceso aislado y acotado; no importa ni utiliza conexiones de base de datos."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import polars as pl

from dataflow.modules.ingestion.domain import ENGINE_VERSION
from dataflow.modules.quality.public import evaluate_quality
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import profile_rows
from dataflow.platform.data_types import DataType
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import Cell, frame_types


def parse_csv(
    content: bytes, separator: str, max_rows: int, max_columns: int
) -> tuple[list[str], list[list[str | None]], str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApplicationError(
            "CSV_ENCODING", "Guarda el CSV en UTF-8 antes de volver a subirlo.", 422
        ) from exc
    if "\x00" in text:
        raise ApplicationError(
            "CSV_BINARY", "El archivo contiene bytes nulos y no es un CSV admitido.", 422
        )
    if separator == "auto":
        try:
            separator = csv.Sniffer().sniff(text[:65536], delimiters=",;\t").delimiter
        except csv.Error:
            separator = ","
    elif separator == "tab":
        separator = "\t"
    if separator not in {",", ";", "\t"}:
        raise ApplicationError("CSV_SEPARATOR", "Separador no admitido.", 422)
    csv.field_size_limit(10000)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=separator, strict=True)
    try:
        headers = next(reader, [])
        if (
            not headers
            or len(headers) > max_columns
            or any(not h.strip() or len(h) > 200 for h in headers)
        ):
            raise ApplicationError(
                "CSV_HEADERS",
                "La cabecera debe tener entre 1 y 128 nombres no vacíos de hasta 200 caracteres.",
                422,
            )
        if len(set(headers)) != len(headers):
            raise ApplicationError(
                "CSV_DUPLICATE_HEADERS", "La cabecera contiene nombres de columna repetidos.", 422
            )
        rows: list[list[str | None]] = []
        for record in reader:
            if not record:
                continue
            if len(record) != len(headers):
                raise ApplicationError(
                    "CSV_SHAPE",
                    f"El registro {len(rows) + 1} no tiene el número de columnas de la cabecera.",
                    422,
                )
            if len(rows) >= max_rows:
                raise ApplicationError(
                    "CSV_ROW_LIMIT",
                    "El archivo supera el límite de registros de este incremento.",
                    422,
                )
            rows.append([value if value != "" else None for value in record])
    except csv.Error as exc:
        raise ApplicationError(
            "CSV_MALFORMED",
            "CSV mal formado o campo de más de 10.000 caracteres. Revisa comillas y separadores.",
            422,
        ) from exc
    if not rows:
        raise ApplicationError(
            "CSV_NO_ROWS", "El CSV no contiene registros después de la cabecera.", 422
        )
    return headers, rows, separator


def load_table(
    source: Path, max_rows: int, max_columns: int
) -> tuple[list[str], list[list[Cell]], list[tuple[DataType, dict[str, Any]]]]:
    """Tabla publicada: texto nullable o columnas tipadas del catálogo (Fase 6). Un tipo físico
    fuera del catálogo se rechaza con UNSUPPORTED_COLUMN_TYPE."""
    frame = pl.read_parquet(source)
    if frame.height > max_rows or frame.width > max_columns:
        raise ApplicationError(
            "TABLE_LIMIT", "La tabla supera los límites fijados en el plan.", 422
        )
    types = frame_types(frame)
    return frame.columns, [list(row) for row in frame.iter_rows()], types


def read(source: Path, output: Path, separator: str, max_rows: int, max_columns: int) -> None:
    """ingestion.read_csv@1: CSV original → Parquet de texto nullable."""
    content = source.read_bytes()
    headers, rows, actual_separator = parse_csv(content, separator, max_rows, max_columns)
    frame = pl.DataFrame(rows, schema={name: pl.String for name in headers}, orient="row")
    frame.write_parquet(output / "data.parquet", compression="zstd", statistics=True)
    (output / "read.json").write_text(
        json.dumps(
            {
                "separator": actual_separator,
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "row_count": len(rows),
                "column_count": len(headers),
            }
        ),
        encoding="utf-8",
    )


def profile(
    source: Path,
    output: Path,
    separator: str,
    source_sha256: str,
    max_rows: int,
    max_columns: int,
) -> None:
    """understanding.profile@1 sobre una tabla; separador y hash son procedencia del original."""
    headers, rows, types = load_table(source, max_rows, max_columns)
    result = DatasetProfile(
        engine_version=ENGINE_VERSION,
        polars_version=pl.__version__,
        source_sha256=source_sha256,
        separator=separator,
        row_count=len(rows),
        column_count=len(headers),
        columns=profile_rows(headers, rows, types),
    )
    (output / "profile.json").write_text(result.model_dump_json(), encoding="utf-8")


def quality(source: Path, output: Path, max_rows: int, max_columns: int) -> None:
    """quality.evaluate@1 sobre una tabla."""
    headers, rows, types = load_table(source, max_rows, max_columns)
    report = evaluate_quality(headers, rows, [data_type for data_type, _ in types])
    (output / "quality.json").write_text(report.model_dump_json(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["read", "profile", "quality"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--max-columns", type=int, required=True)
    parser.add_argument("--separator", default=",")
    parser.add_argument("--source-sha256")
    args = parser.parse_args()
    try:
        if args.mode == "read":
            read(args.input, args.output, args.separator, args.max_rows, args.max_columns)
        elif args.mode == "profile":
            if not args.source_sha256:
                raise ApplicationError("PROCESSING_ERROR", "Falta el hash de procedencia.", 422)
            profile(
                args.input,
                args.output,
                args.separator,
                args.source_sha256,
                args.max_rows,
                args.max_columns,
            )
        else:
            quality(args.input, args.output, args.max_rows, args.max_columns)
    except ApplicationError as exc:
        (args.output / "error.json").write_text(
            json.dumps({"code": exc.code, "message": exc.message}), encoding="utf-8"
        )
        raise SystemExit(2) from None
    except Exception:
        (args.output / "error.json").write_text(
            json.dumps(
                {"code": "PROCESSING_ERROR", "message": "No se pudo completar el procesamiento."}
            ),
            encoding="utf-8",
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
