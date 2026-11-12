import io
import json
from pathlib import Path
from typing import Any

import polars as pl

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.application import AnalysisOutput, ReadOutput
from dataflow.modules.ingestion.contracts import (
    PdfSelection,
    PreviewPage,
    PreviewRow,
    ReadPdfParameters,
    ReadXlsxParameters,
    RecordsPage,
    SourceFacts,
    SourceReading,
    SqlServerConnection,
    SqlSnapshot,
    XlsxInspection,
)
from dataflow.modules.quality.contracts import WHITESPACE_CHARS, QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.errors import ApplicationError
from dataflow.platform.isolation import run_isolated
from dataflow.platform.parquet_metadata import READING_KEY
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
        self,
        content: bytes,
        separator: str,
        config: ProcessingConfig,
        timeout: float,
        encoding: str | None = None,
    ) -> ReadOutput:
        files = self.run(
            "read",
            content,
            config,
            timeout,
            ["data.parquet", "read.json"],
            ["--separator", separator, *(["--encoding", encoding] if encoding else [])],
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

    def read_pdf(
        self,
        content: bytes,
        parameters: ReadPdfParameters,
        config: ProcessingConfig,
        timeout: float,
    ) -> ReadOutput:
        files = self.run(
            "read_pdf",
            content,
            config,
            timeout,
            ["data.parquet", "read.json"],
            ["--pdf-json", parameters.model_dump_json()],
        )
        meta = json.loads(files["read.json"])
        return ReadOutput(
            files["data.parquet"],
            str(meta["separator"]),
            str(meta["source_sha256"]),
            int(meta["row_count"]),
            int(meta["column_count"]),
        )

    def select_pdf(self, content: bytes, config: ProcessingConfig) -> PdfSelection:
        files = self.run("select_pdf", content, config, config.timeout_seconds, ["selection.json"])
        return PdfSelection.model_validate_json(files["selection.json"])

    def snapshot_sqlserver(
        self, connection: SqlServerConnection, config: ProcessingConfig
    ) -> SqlSnapshot:
        """La contraseña sólo viaja al directorio temporal privado del subproceso, que se borra
        al terminar; nunca a argumentos de línea de órdenes ni a registros."""
        payload = json.dumps(
            {
                "server": connection.server,
                "port": connection.port,
                "database": connection.database,
                "user": connection.user,
                "password": connection.password.get_secret_value(),
                "timeout": config.timeout_seconds,
            }
        ).encode()
        files = self.run(
            "snapshot_sqlserver", payload, config, config.timeout_seconds, ["snapshot.json"]
        )
        return SqlSnapshot.model_validate_json(files["snapshot.json"])

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

    def source_facts(
        self, content: bytes, parameters: dict[str, Any], config: ProcessingConfig, timeout: float
    ) -> SourceFacts:
        """Fase 22: datos del original (rango, hojas, fórmulas, líneas en blanco)."""
        files = self.run(
            "source_facts",
            content,
            config,
            timeout,
            ["facts.json"],
            ["--facts-json", json.dumps(parameters, ensure_ascii=False)],
        )
        return SourceFacts.model_validate_json(files["facts.json"])

    def profile(
        self,
        table: bytes,
        separator: str,
        source_sha256: str,
        config: ProcessingConfig,
        timeout: float,
        include_overview: bool = False,
        include_interpretation: bool = False,
        include_analysis: bool = False,
    ) -> DatasetProfile:
        files = self.run(
            "analytical_profile"
            if include_analysis
            else "interpreted_profile"
            if include_interpretation
            else ("automatic_profile" if include_overview else "profile"),
            table,
            config,
            timeout,
            ["profile.json"],
            ["--separator", separator, "--source-sha256", source_sha256],
        )
        return DatasetProfile.model_validate_json(files["profile.json"])

    def quality(
        self, table: bytes, config: ProcessingConfig, timeout: float, analytical: bool = False
    ) -> QualityReport:
        mode = "analytical_quality" if analytical else "quality"
        files = self.run(mode, table, config, timeout, ["quality.json"])
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

    def source_reading(self, content: bytes) -> SourceReading | None:
        """Decisión de lectura guardada en los metadatos de la tabla (Fase 18); None en tablas
        leídas antes. Sólo lee el pie del Parquet."""
        metadata = pl.read_parquet_metadata(io.BytesIO(content))
        raw = metadata.get(READING_KEY)
        return SourceReading.model_validate_json(raw) if raw else None

    def read(
        self,
        content: bytes,
        limit: int,
        offset: int,
        rule: str | None = None,
        column: str | None = None,
        sort: str | None = None,
        descending: bool = False,
        search: str | None = None,
        column_ids: list[str] | None = None,
    ) -> PreviewPage:
        """Página de filas con su número original. Fase 22: orden por una columna (numérico si
        todos sus valores son números; si no, texto) y búsqueda literal sin distinguir
        mayúsculas en todas las columnas. Sin filtro, orden ni búsqueda sólo se materializa la
        página pedida."""
        if rule is None and sort is None and not search:
            lazy = pl.scan_parquet(io.BytesIO(content))
            columns = lazy.collect_schema().names()
            total = lazy.select(pl.len()).collect().item()
            page = lazy.slice(offset, limit).collect()
            types = frame_types(page)
            plain = PreviewPage(
                columns=columns,
                rows=[
                    PreviewRow(
                        row_number=offset + index + 1,
                        values={
                            name: display_cell(cell, data_type, parameters)
                            for name, cell, (data_type, parameters) in zip(
                                columns, row, types, strict=True
                            )
                        },
                    )
                    for index, row in enumerate(page.iter_rows())
                ],
                total=int(total),
                limit=limit,
                offset=offset,
            )
            if column_ids is None:
                return plain
            return RecordsPage(**plain.__dict__, column_ids=column_ids)
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
        if search:
            needle = search.lower()
            found = pl.Series("found", [False] * frame.height)
            for name in columns:
                text = frame.get_column(name).cast(pl.String).alias("value")
                hit = text.str.to_lowercase().str.contains(needle, literal=True)
                found = found | hit.fill_null(False)
            mask = found if mask is None else mask & found
        numbers = pl.Series("row", range(1, frame.height + 1), dtype=pl.Int64)
        if sort is not None:
            if sort not in columns:
                raise ApplicationError("UNKNOWN_COLUMN", "La columna no existe en la tabla.", 422)
            key = frame.get_column(sort).alias("key")
            if key.dtype == pl.String:
                numeric = key.cast(pl.Float64, strict=False)
                if numeric.null_count() == key.null_count():
                    key = numeric
            order = pl.DataFrame([key, numbers]).with_row_index("position")
            order = order.sort(
                ["key", "row"], descending=[descending, False], nulls_last=True, maintain_order=True
            )
            positions = order.get_column("position")
            frame, numbers = frame[positions], numbers.gather(positions)
            if mask is not None:
                mask = mask.gather(positions)
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
        result = PreviewPage(
            columns=columns, rows=rows, total=frame.height, limit=limit, offset=offset
        )
        if column_ids is None and sort is None and not search:
            return result
        return RecordsPage(
            **result.__dict__,
            column_ids=column_ids or [],
            sort=sort,
            descending=descending,
            search=search,
        )
