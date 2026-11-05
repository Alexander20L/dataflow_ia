import io
import json
from pathlib import Path

import polars as pl

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.application import AnalysisOutput, ReadOutput
from dataflow.modules.ingestion.contracts import PreviewPage, PreviewRow
from dataflow.modules.quality.contracts import WHITESPACE_CHARS, QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.isolation import run_isolated


class IsolatedAnalyzer:
    def __init__(self, root: Path, timeout: int, max_rows: int, max_columns: int) -> None:
        self.root, self.timeout, self.max_rows, self.max_columns = (
            root,
            timeout,
            max_rows,
            max_columns,
        )

    def config(self, config: ProcessingConfig | None) -> ProcessingConfig:
        return config or ProcessingConfig(
            max_rows=self.max_rows, max_columns=self.max_columns, timeout_seconds=self.timeout
        )

    def run(
        self,
        mode: str,
        content: bytes,
        config: ProcessingConfig,
        timeout: float,
        outputs: list[str],
        extra: list[str] | None = None,
    ) -> dict[str, bytes]:
        """Un subproceso acotado por paso; `timeout` es lo que queda del plazo del plan."""
        return run_isolated(
            self.root,
            "dataflow.modules.ingestion.processor",
            {"input.bin": content},
            [
                "--mode",
                mode,
                "--input",
                "{dir}/input.bin",
                "--max-rows",
                str(config.max_rows),
                "--max-columns",
                str(config.max_columns),
                *(extra or []),
            ],
            outputs,
            min(timeout, config.timeout_seconds),
        )

    def read(
        self, content: bytes, separator: str, config: ProcessingConfig, timeout: float
    ) -> ReadOutput:
        files = self.run(
            "read",
            content,
            config,
            timeout,
            ["data.parquet", "read.json"],
            ["--separator", separator],
        )
        meta = json.loads(files["read.json"])
        return ReadOutput(
            files["data.parquet"],
            str(meta["separator"]),
            str(meta["source_sha256"]),
            int(meta["row_count"]),
            int(meta["column_count"]),
        )

    def profile(
        self,
        table: bytes,
        separator: str,
        source_sha256: str,
        config: ProcessingConfig,
        timeout: float,
    ) -> DatasetProfile:
        files = self.run(
            "profile",
            table,
            config,
            timeout,
            ["profile.json"],
            ["--separator", separator, "--source-sha256", source_sha256],
        )
        return DatasetProfile.model_validate_json(files["profile.json"])

    def quality(self, table: bytes, config: ProcessingConfig, timeout: float) -> QualityReport:
        files = self.run("quality", table, config, timeout, ["quality.json"])
        return QualityReport.model_validate_json(files["quality.json"])

    def analyze(
        self,
        content: bytes,
        separator: str,
        config: ProcessingConfig | None = None,
    ) -> AnalysisOutput:
        """Composición read → profile → quality de un CSV; sólo para utilidades/legado."""
        effective = self.config(config)
        timeout = float(effective.timeout_seconds)
        table = self.read(content, separator, effective, timeout)
        return AnalysisOutput(
            self.profile(table.parquet, table.separator, table.source_sha256, effective, timeout),
            self.quality(table.parquet, effective, timeout),
            table.parquet,
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
