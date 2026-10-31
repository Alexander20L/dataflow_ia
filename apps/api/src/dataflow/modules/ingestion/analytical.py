import io
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.application import AnalysisOutput
from dataflow.modules.ingestion.contracts import PreviewPage, PreviewRow
from dataflow.modules.quality.contracts import WHITESPACE_CHARS, QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.errors import ApplicationError


class IsolatedAnalyzer:
    def __init__(self, root: Path, timeout: int, max_rows: int, max_columns: int) -> None:
        self.root, self.timeout, self.max_rows, self.max_columns = (
            root,
            timeout,
            max_rows,
            max_columns,
        )

    def analyze(
        self,
        content: bytes,
        separator: str,
        config: ProcessingConfig | None = None,
        table_source_sha256: str | None = None,
        quality_only: bool = False,
    ) -> AnalysisOutput:
        config = config or ProcessingConfig(
            max_rows=self.max_rows, max_columns=self.max_columns, timeout_seconds=self.timeout
        )
        scratch = self.root / ".work"
        scratch.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=scratch) as temporary:
            directory = Path(temporary)
            source = directory / "original.csv"
            source.write_bytes(content)
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "dataflow.modules.ingestion.processor",
                        "--input",
                        str(source),
                        "--output",
                        str(directory),
                        "--separator",
                        separator,
                        "--max-rows",
                        str(config.max_rows),
                        "--max-columns",
                        str(config.max_columns),
                    ]
                    + (
                        ["--table-source-sha256", table_source_sha256]
                        if table_source_sha256
                        else []
                    )
                    + (["--quality-only"] if quality_only else []),
                    timeout=config.timeout_seconds,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "POLARS_MAX_THREADS": "2"},
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ApplicationError(
                    "PROCESSING_TIMEOUT", "El procesamiento excedió el tiempo permitido.", 422
                ) from exc
            if result.returncode:
                error_path = directory / "error.json"
                if error_path.exists():
                    error = json.loads(error_path.read_text(encoding="utf-8"))
                    raise ApplicationError(str(error["code"]), str(error["message"]), 422)
                raise ApplicationError(
                    "PROCESSING_ERROR", "El proceso analítico terminó sin resultado.", 422
                )
            profile_path = directory / "profile.json"
            parquet_path = directory / "data.parquet"
            return AnalysisOutput(
                DatasetProfile.model_validate_json(profile_path.read_bytes())
                if profile_path.exists()
                else None,
                QualityReport.model_validate_json((directory / "quality.json").read_bytes()),
                parquet_path.read_bytes() if parquet_path.exists() else b"",
            )


class PolarsPreview:
    def read(
        self,
        content: bytes,
        limit: int,
        offset: int,
        rule: str | None = None,
        column: str | None = None,
    ) -> PreviewPage:
        frame = pl.read_parquet(io.BytesIO(content))
        columns = frame.columns
        index_name = "__dataflow_row__"
        while index_name in columns:
            index_name = "_" + index_name
        frame = frame.with_row_index(index_name, offset=1)
        if rule == "Q-001" and column:
            frame = frame.filter(pl.col(column).is_null())
        elif rule == "Q-003" and column:
            frame = frame.filter(
                pl.col(column).is_not_null()
                & (pl.col(column).str.strip_chars(WHITESPACE_CHARS) == "")
            )
        elif rule == "Q-002":
            frame = frame.filter(~pl.struct(columns).is_first_distinct())
        rows = [
            PreviewRow(row_number=row[index_name], values={name: row[name] for name in columns})
            for row in frame.slice(offset, limit).iter_rows(named=True)
        ]
        return PreviewPage(
            columns=columns, rows=rows, total=frame.height, limit=limit, offset=offset
        )
