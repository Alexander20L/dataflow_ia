"""Proceso aislado de analytics.query@1, @2 y @3: no importa ni utiliza conexiones de base de
datos."""

import argparse
import json
from pathlib import Path

import polars as pl

from dataflow.modules.analytics.contracts import (
    AnyAnalysisResult,
    EvidenceScope,
    MetricContent,
    MetricReference,
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
)
from dataflow.modules.analytics.engine import Metric, run_query, run_query_v2, run_query_v3
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import frame_types


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["query"], required=True)
    parser.add_argument("--operation-version", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns-json", required=True)
    parser.add_argument("--metrics-json", required=True)
    parser.add_argument("--parameters-json", required=True)
    parser.add_argument("--scope-json", required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--max-columns", type=int, required=True)
    args = parser.parse_args()
    try:
        frame = pl.read_parquet(args.input)
        if frame.height > args.max_rows or frame.width > args.max_columns:
            raise ApplicationError(
                "TABLE_LIMIT", "La tabla supera los límites fijados en el plan.", 422
            )
        frame_types(frame)  # rechaza tipos físicos fuera del catálogo
        metrics = [
            Metric(
                MetricReference.model_validate(item["reference"]),
                int(item["revision"]),
                MetricContent.model_validate(item["content"]),
                item.get("unit"),
                item.get("currency"),
            )
            for item in json.loads(args.metrics_json)
        ]
        rows = [list(row) for row in frame.iter_rows()]
        columns = json.loads(args.columns_json)
        scope = EvidenceScope.model_validate_json(args.scope_json)
        result: AnyAnalysisResult = (
            run_query_v3(
                frame.columns,
                rows,
                columns,
                metrics,
                QueryParametersV3.model_validate_json(args.parameters_json),
                scope,
            )
            if args.operation_version == 3
            else run_query_v2(
                frame.columns,
                rows,
                columns,
                metrics,
                QueryParametersV2.model_validate_json(args.parameters_json),
                scope,
            )
            if args.operation_version == 2
            else run_query(
                frame.columns,
                rows,
                columns,
                metrics,
                QueryParameters.model_validate_json(args.parameters_json),
                scope,
            )
        )
        (args.output / "analysis.json").write_text(result.model_dump_json(), encoding="utf-8")
    except ApplicationError as exc:
        (args.output / "error.json").write_text(
            json.dumps(
                {"code": exc.code, "message": exc.message, "details": exc.details},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise SystemExit(2) from None
    except Exception:
        (args.output / "error.json").write_text(
            json.dumps({"code": "PROCESSING_ERROR", "message": "No se pudo calcular el análisis."}),
            encoding="utf-8",
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
