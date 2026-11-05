import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataflow.modules.cleaning.contracts import EffectCounts, EffectSample, Match, Predicate
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

    def effect(
        self,
        source: bytes,
        result: bytes,
        columns: list[dict[str, Any]],
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
        )
