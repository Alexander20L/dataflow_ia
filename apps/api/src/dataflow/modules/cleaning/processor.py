"""Proceso aislado de limpieza: no importa ni utiliza conexiones de base de datos."""

import argparse
import json
from pathlib import Path

import polars as pl

from dataflow.modules.cleaning.infrastructure import (
    SOURCE_ROW,
    attach_lineage,
    effect,
    filter_rows,
    table_digest,
    trim_whitespace,
)
from dataflow.platform.errors import ApplicationError


def load(path: Path, lineage: bool, max_rows: int, max_columns: int) -> pl.DataFrame:
    frame = pl.read_parquet(path)
    data_columns = frame.width - (1 if lineage else 0)
    if frame.height > max_rows or data_columns > max_columns:
        raise ApplicationError(
            "TABLE_LIMIT", "La tabla supera los límites fijados en el plan.", 422
        )
    if lineage != (SOURCE_ROW in frame.columns):
        raise ApplicationError("EFFECT_INVALID", "El linaje de filas no es válido.", 422)
    return frame if lineage else attach_lineage(frame)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["trim", "filter", "effect"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns-json", required=True)
    parser.add_argument("--lineage", choices=["present", "absent"], default="absent")
    parser.add_argument("--predicate", choices=["is_null", "is_whitespace_only"])
    parser.add_argument("--match", choices=["any", "all"], default="any")
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--max-columns", type=int, required=True)
    args = parser.parse_args()
    try:
        columns = json.loads(args.columns_json)
        if args.mode in {"trim", "filter"}:
            frame = load(args.input, args.lineage == "present", args.max_rows, args.max_columns)
            result = (
                trim_whitespace(frame, columns)
                if args.mode == "trim"
                else filter_rows(frame, columns, args.predicate, args.match)
            )
            result.write_parquet(args.output / "data.parquet", compression="zstd", statistics=True)
        else:
            source = pl.read_parquet(args.source)
            result = load(args.input, True, args.max_rows, args.max_columns)
            counts, samples, lineage, lineage_sha256 = effect(source, result, columns)
            table = result.drop(SOURCE_ROW)
            table.write_parquet(args.output / "table.parquet", compression="zstd", statistics=True)
            lineage.write_parquet(args.output / "lineage.parquet", compression="zstd")
            (args.output / "effect.json").write_text(
                json.dumps(
                    {
                        "counts": counts.model_dump(mode="json"),
                        "samples": [sample.model_dump(mode="json") for sample in samples],
                        "logical_content_sha256": table_digest(columns, table),
                        "row_lineage_sha256": lineage_sha256,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
    except ApplicationError as exc:
        (args.output / "error.json").write_text(
            json.dumps({"code": exc.code, "message": exc.message}), encoding="utf-8"
        )
        raise SystemExit(2) from None
    except Exception:
        (args.output / "error.json").write_text(
            json.dumps(
                {"code": "PROCESSING_ERROR", "message": "No se pudo completar la limpieza."}
            ),
            encoding="utf-8",
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
