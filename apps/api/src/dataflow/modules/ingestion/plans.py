import csv
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from dataflow.modules.datasets.contracts import DatasetVersion
from dataflow.modules.executions.public import Artifact, PlanRevision, ProcessingConfig
from dataflow.modules.ingestion.contracts import (
    ReadPdfParameters,
    ReadXlsxParameters,
    ReadXlsxV2Parameters,
    SourceOrigin,
    XlsxSelection,
)
from dataflow.modules.ingestion.domain import detect_separator
from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.canonical import digest


def import_fingerprint(name: str, sha256: str, requested_separator: str) -> str:
    return digest(
        "import_request", {"name": name, "sha256": sha256, "separator": requested_separator}
    )


def xlsx_import_fingerprint(name: str, sha256: str, parameters: ReadXlsxParameters) -> str:
    return digest(
        "import_request",
        {"name": name, "sha256": sha256, "xlsx": parameters.model_dump(mode="json")},
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


def resolve_encoding(content: bytes) -> Literal["utf-8-sig", "cp1252"]:
    """Fase 18: UTF-8 (con o sin BOM) y, si no lo es, Windows-1252 (el «ANSI» con que Excel
    guarda CSV en Windows). Determinista sobre los bytes; queda fijada en el plan. Si tampoco
    es Windows-1252, el worker falla con CSV_ENCODING."""
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def resolve_separator(content: bytes, requested: str, encoding: str = "utf-8-sig") -> str:
    if requested == "tab":
        return "\t"
    if requested != "auto":
        return requested
    try:
        return detect_separator(content.decode(encoding, errors="replace"))
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
    xlsx: ReadXlsxParameters | None = None,
    source_selection: XlsxSelection | None = None,
    encoding: Literal["utf-8-sig", "cp1252"] = "utf-8-sig",
    pdf: ReadPdfParameters | None = None,
    source_origin: SourceOrigin | None = None,
) -> PlanRevision:
    # analysis-v13 (Fase 18): lecturas @2 con codificación y valores regionales.
    regional = config.operation_catalog == "analysis-v13"
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
                "operation": "ingestion.read_pdf",
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": pdf.model_dump(mode="json"),
            }
            if pdf
            else {
                "id": "read",
                "operation": "ingestion.read_xlsx",
                "version": 2 if regional else 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": (
                    ReadXlsxV2Parameters(**xlsx.model_dump()) if regional else xlsx
                ).model_dump(mode="json"),
            }
            if xlsx
            else {
                "id": "read",
                "operation": "ingestion.read_csv",
                "version": 2 if regional else 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {
                    "requested_separator": "\t"
                    if requested_separator == "tab"
                    else requested_separator,
                    "separator": separator,
                    "encoding": encoding if regional else "utf-8-sig",
                    **({"values": "regional-values-v1"} if regional else {}),
                    "strict": True,
                    "empty_cells": "null",
                    "blank_lines": "skip",
                },
            }
        ]
        step_input = {"kind": "step", "step_id": "read"}
    # analysis-v11 (Fase 14): las cargas nuevas usan la interpretación analítica y la calidad
    # que indica los análisis afectados. Las tablas derivadas conservan profile@1/quality@1.
    analytical = table is None and config.operation_catalog in {
        "analysis-v11",
        "analysis-v12",
        "analysis-v13",
    }
    if analysis_kind == "profile_quality":
        profile_version = 1
        if table is None:
            if analytical:
                profile_version = 4
            elif config.operation_catalog == "analysis-v10":
                profile_version = 3
            elif config.operation_catalog == "analysis-v9":
                profile_version = 2
        steps.append(
            {
                "id": "profile",
                "operation": "understanding.profile",
                "version": profile_version,
                "input": step_input,
                "parameters": {
                    "algorithm": {
                        1: "column-profile-v1",
                        2: "column-profile-overview-v1",
                        3: "column-profile-interpreted-v1",
                        4: "column-profile-analytical-v1",
                    }[profile_version]
                },
            }
        )
    steps.append(
        {
            "id": "quality",
            "operation": "quality.evaluate",
            "version": 3 if analytical else 1,
            "input": step_input,
            "parameters": {
                "rule_set": "csv-quality-v1",
                "rules": ["Q-001", "Q-002", "Q-003"],
                "score": "cell_completeness_v1",
                **({"analytical_rules": "automatic-quality-v1"} if analytical else {}),
            },
        }
    )
    if table is None and config.operation_catalog in {"analysis-v12", "analysis-v13"}:
        # Fase 15: plan analítico automático y hallazgos sobre la misma tabla importada.
        steps.append(
            {
                "id": "analysis",
                "operation": "analytics.automatic",
                "version": 1,
                "input": step_input,
                "parameters": {"rules": "automatic-analysis-v1", "plan_rules": "automatic-plan-v1"},
            }
        )
    content = {
        "objective": None,
        "input": input_ref,
        "semantic_ref": semantic_ref.model_dump(mode="json") if semantic_ref else None,
        "steps": steps,
        "config": config.model_dump(),
    }
    if source_selection is not None:
        content["source_selection"] = source_selection.model_dump(mode="json")
    if source_origin is not None:
        content["source_origin"] = source_origin.model_dump(mode="json")
    return PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
