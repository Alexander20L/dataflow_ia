"""Proceso aislado de analytics.query@1, @2 y @3: no importa ni utiliza conexiones de base de
datos."""

import argparse
import json
from pathlib import Path
from typing import Any

import polars as pl

from dataflow.modules.analytics.automatic import run_automatic
from dataflow.modules.analytics.contracts import (
    AnyAnalysisResult,
    AutomaticScope,
    EvidenceScope,
    FollowUpQuery,
    MetricContent,
    MetricReference,
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
)
from dataflow.modules.analytics.engine import Metric, run_query, run_query_v2, run_query_v3
from dataflow.modules.analytics.followup import run_followups
from dataflow.modules.planning.public import plan_analyses
from dataflow.modules.understanding.contracts import AnalyticalInterpretation, DatasetProfile
from dataflow.modules.understanding.public import analyze, profile_rows, row_periods
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import display_cell, frame_types


def interpreted(
    frame: pl.DataFrame, types: list[tuple[Any, dict[str, Any]]]
) -> tuple[list[list[str | None]], AnalyticalInterpretation, dict[str, int], list[str | None]]:
    """Celdas de texto, interpretación v2, valores distintos y periodo mensual de cada fila."""
    rows = [list(row) for row in frame.iter_rows()]
    cells = [[display_cell(value, *types[i]) for i, value in enumerate(row)] for row in rows]
    columns = profile_rows(frame.columns, rows, types)
    profile = DatasetProfile(
        engine_version="analytics.automatic@1",
        polars_version=pl.__version__,
        source_sha256="",
        separator="",
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
    )
    interpretation = analyze(profile, cells)
    _, periods = row_periods(interpretation.columns, cells)
    return cells, interpretation, {c.name: c.unique_count for c in columns}, periods


def automatic(
    frame: pl.DataFrame,
    types: list[tuple[Any, dict[str, Any]]],
    scope: AutomaticScope,
    output: Path,
) -> None:
    """analytics.automatic@1: interpretación → plan automático → análisis con evidencia."""
    cells, interpretation, distinct, periods = interpreted(frame, types)
    plan = plan_analyses(interpretation, distinct, len(cells))
    result = run_automatic(cells, periods, interpretation, plan, scope)
    (output / "automatic.json").write_text(result.model_dump_json(), encoding="utf-8")


def followup(
    frame: pl.DataFrame,
    types: list[tuple[Any, dict[str, Any]]],
    scope: AutomaticScope,
    queries: list[FollowUpQuery],
    output: Path,
) -> None:
    """analytics.followup@1: consultas de seguimiento ya validadas de la investigación."""
    cells, interpretation, _, periods = interpreted(frame, types)
    result = run_followups(cells, periods, interpretation, queries, scope)
    (output / "followup.json").write_text(result.model_dump_json(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["query", "automatic", "followup"], required=True)
    parser.add_argument("--operation-version", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns-json", default="[]")
    parser.add_argument("--metrics-json", default="[]")
    parser.add_argument("--parameters-json", default="{}")
    parser.add_argument("--queries-json", default="[]")
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
        types = frame_types(frame)  # rechaza tipos físicos fuera del catálogo
        if args.mode == "automatic":
            automatic(
                frame, types, AutomaticScope.model_validate_json(args.scope_json), args.output
            )
            return
        if args.mode == "followup":
            followup(
                frame,
                types,
                AutomaticScope.model_validate_json(args.scope_json),
                [FollowUpQuery.model_validate(item) for item in json.loads(args.queries_json)],
                args.output,
            )
            return
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
