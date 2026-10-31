import csv
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from dataflow.modules.datasets.contracts import DatasetVersion
from dataflow.modules.executions.public import Artifact, PlanRevision, ProcessingConfig
from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.canonical import digest


def import_fingerprint(name: str, sha256: str, requested_separator: str) -> str:
    return digest(
        "import_request", {"name": name, "sha256": sha256, "separator": requested_separator}
    )


def analysis_fingerprint(
    version: UUID,
    artifact: UUID,
    sha256: str,
    kind: str,
    semantic_ref: SemanticReference | None = None,
) -> str:
    payload: dict[str, Any] = {
        "version_id": str(version),
        "artifact_id": str(artifact),
        "artifact_sha256": sha256,
        "analysis_kind": kind,
    }
    if semantic_ref is not None:
        payload["semantic_ref"] = semantic_ref.model_dump(mode="json")
    return digest("analysis_request", payload)


def resolve_separator(content: bytes, requested: str) -> str:
    if requested == "tab":
        return "\t"
    if requested != "auto":
        return requested
    try:
        return (
            csv.Sniffer()
            .sniff(content.decode("utf-8-sig", errors="replace")[:65536], delimiters=",;\t")
            .delimiter
        )
    except csv.Error:
        return ","


def build_plan(
    owner: UUID,
    version: DatasetVersion,
    config: ProcessingConfig,
    requested_separator: str | None = None,
    separator: str | None = None,
    table: Artifact | None = None,
    analysis_kind: Literal["profile_quality", "quality_only"] = "profile_quality",
    semantic_ref: SemanticReference | None = None,
) -> PlanRevision:
    if table:
        input_ref: dict[str, Any] = {
            "kind": "table",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "artifact_id": str(table.id),
            "artifact_sha256": table.content.sha256,
        }
        steps: list[dict[str, Any]] = []
        step_input = {"kind": "input", "alias": "source"}
    else:
        input_ref = {
            "kind": "source",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
        }
        steps = [
            {
                "id": "read",
                "operation": "ingestion.read_csv",
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {
                    "requested_separator": "\t"
                    if requested_separator == "tab"
                    else requested_separator,
                    "separator": separator,
                    "encoding": "utf-8-sig",
                    "strict": True,
                    "empty_cells": "null",
                    "blank_lines": "skip",
                },
            }
        ]
        step_input = {"kind": "step", "step_id": "read"}
    if analysis_kind == "profile_quality":
        steps.append(
            {
                "id": "profile",
                "operation": "understanding.profile",
                "version": 1,
                "input": step_input,
                "parameters": {"algorithm": "column-profile-v1"},
            }
        )
    steps.append(
        {
            "id": "quality",
            "operation": "quality.evaluate",
            "version": 1,
            "input": step_input,
            "parameters": {
                "rule_set": "csv-quality-v1",
                "rules": ["Q-001", "Q-002", "Q-003"],
                "score": "cell_completeness_v1",
            },
        }
    )
    content = {
        "objective": None,
        "input": input_ref,
        "semantic_ref": semantic_ref.model_dump(mode="json") if semantic_ref else None,
        "steps": steps,
        "config": config.model_dump(),
    }
    return PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
