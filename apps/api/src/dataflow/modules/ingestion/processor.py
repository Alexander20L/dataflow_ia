"""Proceso aislado y acotado; no importa ni utiliza conexiones de base de datos."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import polars as pl

from dataflow.modules.ingestion.contracts import Diagnostic
from dataflow.modules.ingestion.domain import ENGINE_VERSION
from dataflow.modules.quality.public import evaluate_quality
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import profile_rows
from dataflow.platform.errors import ApplicationError


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


def process(
    source: Path,
    output: Path,
    separator: str,
    max_rows: int,
    max_columns: int,
    table_source_sha256: str | None = None,
    quality_only: bool = False,
) -> None:
    content = source.read_bytes()
    if table_source_sha256 is None:
        headers, rows, actual_separator = parse_csv(content, separator, max_rows, max_columns)
        frame = pl.DataFrame(rows, schema={name: pl.String for name in headers}, orient="row")
        frame.write_parquet(output / "data.parquet", compression="zstd", statistics=True)
    else:
        frame = pl.read_parquet(source)
        if frame.height > max_rows or frame.width > max_columns:
            raise ApplicationError(
                "TABLE_LIMIT", "La tabla supera los límites fijados en el plan.", 422
            )
        if any(dtype != pl.String for dtype in frame.dtypes):
            raise ApplicationError(
                "UNSUPPORTED_TABLE_TYPE", "Esta versión del motor sólo perfila texto nullable.", 422
            )
        headers, rows, actual_separator = (
            frame.columns,
            [list(row) for row in frame.iter_rows()],
            separator,
        )
    quality = evaluate_quality(headers, rows)
    (output / "quality.json").write_text(quality.model_dump_json(), encoding="utf-8")
    if quality_only:
        return
    result = Diagnostic(
        profile=DatasetProfile(
            engine_version=ENGINE_VERSION,
            polars_version=pl.__version__,
            source_sha256=table_source_sha256 or hashlib.sha256(content).hexdigest(),
            separator=actual_separator,
            row_count=len(rows),
            column_count=len(headers),
            columns=profile_rows(headers, rows),
        ),
        quality=quality,
    )
    (output / "profile.json").write_text(result.profile.model_dump_json(), encoding="utf-8")
    (output / "diagnostic.json").write_text(result.model_dump_json(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--separator", required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--max-columns", type=int, required=True)
    parser.add_argument("--table-source-sha256")
    parser.add_argument("--quality-only", action="store_true")
    args = parser.parse_args()
    try:
        process(
            args.input,
            args.output,
            args.separator,
            args.max_rows,
            args.max_columns,
            args.table_source_sha256,
            args.quality_only,
        )
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
