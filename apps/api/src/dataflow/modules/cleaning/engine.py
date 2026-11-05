import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataflow.modules.cleaning.contracts import (
    EffectCounts,
    EffectSample,
    Match,
    NullKeys,
    Predicate,
)
from dataflow.modules.cleaning.conversion import CastType
from dataflow.modules.executions.public import ProcessingConfig
from dataflow.platform.isolation import run_isolated

MODULE = "dataflow.modules.cleaning.processor"


@dataclass(frozen=True)
class EffectResult:
    table: bytes
    lineage: bytes
    counts: EffectCounts
    samples: list[EffectSample]
    logical_content_sha256: str
    row_lineage_sha256: str
    rounded_cells: int = 0


class IsolatedCleaner:
    """Ejecuta cada operación de limpieza en un subproceso acotado (plazo restante del plan)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def arguments(self, config: ProcessingConfig, columns: Any, lineage: bool) -> list[str]:
        return [
            "--input",
            "{dir}/input.parquet",
            "--columns-json",
            json.dumps(columns, ensure_ascii=False),
            "--lineage",
            "present" if lineage else "absent",
            "--max-rows",
            str(config.max_rows),
            "--max-columns",
            str(config.max_columns),
        ]

    def trim(
        self,
        table: bytes,
        names: list[str],
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        return run_isolated(
            self.root,
            MODULE,
            {"input.parquet": table},
            ["--mode", "trim", *self.arguments(config, names, lineage)],
            ["data.parquet"],
            min(timeout, config.timeout_seconds),
        )["data.parquet"]

    def filter(
        self,
        table: bytes,
        names: list[str],
        predicate: Predicate,
        match: Match,
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        return run_isolated(
            self.root,
            MODULE,
            {"input.parquet": table},
            [
                "--mode",
                "filter",
                "--predicate",
                predicate,
                "--match",
                match,
                *self.arguments(config, names, lineage),
            ],
            ["data.parquet"],
            min(timeout, config.timeout_seconds),
        )["data.parquet"]

    def run(
        self,
        table: bytes,
        mode: str,
        names: list[str],
        extra: list[str],
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        return run_isolated(
            self.root,
            MODULE,
            {"input.parquet": table},
            ["--mode", mode, *extra, *self.arguments(config, names, lineage)],
            ["data.parquet"],
            min(timeout, config.timeout_seconds),
        )["data.parquet"]

    def normalize_null_tokens(
        self,
        table: bytes,
        names: list[str],
        tokens: list[str],
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        extra = ["--tokens-json", json.dumps(tokens, ensure_ascii=False)]
        return self.run(table, "tokens", names, extra, lineage, config, timeout)

    def deduplicate(
        self,
        table: bytes,
        names: list[str],
        ids: list[str],
        null_keys: NullKeys,
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        extra = ["--column-ids-json", json.dumps(ids), "--null-keys", null_keys]
        return self.run(table, "dedupe", names, extra, lineage, config, timeout)

    def cast(
        self,
        table: bytes,
        name: str,
        column_id: str,
        type: CastType,
        scale: int | None,
        lineage: bool,
        config: ProcessingConfig,
        timeout: float,
    ) -> bytes:
        return run_isolated(
            self.root,
            MODULE,
            {"input.parquet": table},
            [
                "--mode",
                "cast",
                "--type",
                type,
                *(["--scale", str(scale)] if scale is not None else []),
                "--column-id",
                column_id,
                *self.arguments(config, [name], lineage),
            ],
            ["data.parquet"],
            min(timeout, config.timeout_seconds),
        )["data.parquet"]

    def effect(
        self,
        source: bytes,
        result: bytes,
        columns: list[dict[str, Any]],
        output_columns: list[dict[str, Any]],
        config: ProcessingConfig,
        timeout: float,
    ) -> EffectResult:
        files = run_isolated(
            self.root,
            MODULE,
            {"input.parquet": result, "source.parquet": source},
            [
                "--mode",
                "effect",
                "--source",
                "{dir}/source.parquet",
                "--output-columns-json",
                json.dumps(output_columns, ensure_ascii=False),
                *self.arguments(config, columns, True),
            ],
            ["table.parquet", "lineage.parquet", "effect.json"],
            min(timeout, config.timeout_seconds),
        )
        payload = json.loads(files["effect.json"])
        return EffectResult(
            files["table.parquet"],
            files["lineage.parquet"],
            EffectCounts.model_validate(payload["counts"]),
            [EffectSample.model_validate(sample) for sample in payload["samples"]],
            str(payload["logical_content_sha256"]),
            str(payload["row_lineage_sha256"]),
            int(payload["rounded_cells"]),
        )
