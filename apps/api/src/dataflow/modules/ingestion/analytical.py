import io
import json
from pathlib import Path
from typing import Any

import polars as pl

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.application import AnalysisOutput, ReadOutput
from dataflow.modules.ingestion.contracts import (
    PreviewPage,
    PreviewRow,
    ReadXlsxParameters,
    XlsxInspection,
)
from dataflow.modules.quality.contracts import WHITESPACE_CHARS, QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.errors import ApplicationError
from dataflow.platform.isolation import run_isolated
from dataflow.platform.tabular import display_cell, frame_types


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

    def read_xlsx(
        self,
        content: bytes,
        parameters: ReadXlsxParameters,
        config: ProcessingConfig,
        timeout: float,
    ) -> ReadOutput:
        files = self.run(
            "read_xlsx",
            content,
            config,
            timeout,
            ["data.parquet", "read.json"],
            ["--xlsx-json", parameters.model_dump_json()],
        )
        meta = json.loads(files["read.json"])
        return ReadOutput(
            files["data.parquet"],
            str(meta["separator"]),
            str(meta["source_sha256"]),
            int(meta["row_count"]),
            int(meta["column_count"]),
        )

    def inspect_xlsx(
        self,
        content: bytes,
        sheet: str | None,
        table: str | None,
        header_row: int,
        config: ProcessingConfig,
    ) -> XlsxInspection:
        selection = {"sheet": sheet, "table": table, "header_row": header_row}
        files = self.run(
            "inspect_xlsx",
            content,
            config,
            float(config.timeout_seconds),
            ["inspect.json"],
            ["--xlsx-json", json.dumps(selection, ensure_ascii=False)],
        )
        return XlsxInspection.model_validate_json(files["inspect.json"])

    def profile(
        self,
        table: bytes,
        separator: str,
        source_sha256: str,
        config: ProcessingConfig,
        timeout: float,
        include_overview: bool = False,
        include_interpretation: bool = False,
    ) -> DatasetProfile:
        files = self.run(
            "interpreted_profile"
            if include_interpretation
            else ("automatic_profile" if include_overview else "profile"),
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

    def quality_rules(
        self,
        table: bytes,
        columns: list[dict[str, Any]],
        rules: list[dict[str, Any]],
        reference: dict[str, Any],
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        """quality.evaluate@2: informe csv-quality-v2 (JSON) sobre la tabla completa."""
        return self.run(
            "quality_rules",
            table,
            config,
            timeout,
            ["quality_rules.json"],
            [
                "--columns-json",
                json.dumps(columns, ensure_ascii=False),
                "--rules-json",
                json.dumps(rules, ensure_ascii=False),
                "--reference-json",
                json.dumps(reference),
            ],
        )["quality_rules.json"]

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
    """Páginas de la tabla publicada. Las columnas se toman como Series por nombre exacto y se
    operan con alias neutros: un encabezado como «^id$» nunca se interpreta como expresión
    regular ni selector. Las celdas tipadas se muestran con su cadena canónica."""

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
        types = frame_types(frame)
        mask: pl.Series | None = None
        if rule in {"Q-001", "Q-003"} and column:
            if column not in columns:
                raise ApplicationError("UNKNOWN_COLUMN", "La columna no existe en la tabla.", 422)
            value = frame.get_column(column).alias("value")
            if rule == "Q-001":
                mask = value.is_null()
            elif value.dtype == pl.String:
                mask = (
                    value.is_not_null() & (value.str.strip_chars(WHITESPACE_CHARS) == "")
                ).fill_null(False)
            else:
                mask = pl.Series("value", [False] * frame.height)
        elif rule == "Q-002":
            neutral = pl.DataFrame(
                [frame.get_column(name).alias(f"c{index}") for index, name in enumerate(columns)]
            )
            mask = ~neutral.select(pl.struct(pl.all()).is_first_distinct()).to_series()
        numbers = pl.Series("row", range(1, frame.height + 1), dtype=pl.Int64)
        if mask is not None:
            frame, numbers = frame.filter(mask), numbers.filter(mask)
        page = frame.slice(offset, limit)
        rows = [
            PreviewRow(
                row_number=number,
                values={
                    name: display_cell(cell, data_type, parameters)
                    for name, cell, (data_type, parameters) in zip(columns, row, types, strict=True)
                },
            )
            for number, row in zip(
                numbers.slice(offset, limit).to_list(), page.iter_rows(), strict=True
            )
        ]
        return PreviewPage(
            columns=columns, rows=rows, total=frame.height, limit=limit, offset=offset
        )
