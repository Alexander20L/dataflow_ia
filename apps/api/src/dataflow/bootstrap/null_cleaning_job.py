"""Textos declarados como nulos (Fase 23, ADR-040): une el Diccionario de la pestaña Dataset con
la limpieza y las versiones derivadas sin acoplar los módulos entre sí.

Cuando el usuario declara en el Diccionario que textos como «N/A» significan «sin dato», se
encola un trabajo `null_cleaning` sobre la tabla leída de la versión que está viendo: sólo pasos
`cleaning.normalize_null_tokens@1` con las escrituras exactas que la inspección encontró. Al
terminar se registra una versión derivada con su linaje y su efecto (`effect_sha256`) y se analiza
como una carga nueva (inspección, comprensión, investigación, exploración, dashboard e informe).
El original y la versión de partida no cambian.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Execution, Executions, PlanRevision
from dataflow.modules.inspection.contracts import ColumnAnnotation, Inspection
from dataflow.platform.canonical import digest

OPERATION = "cleaning.normalize_null_tokens"


def null_steps(
    inspection: Inspection, annotations: dict[str, ColumnAnnotation]
) -> list[dict[str, Any]]:
    """Pasos de la limpieza: por cada columna, los textos declarados que siguen en la tabla
    (una versión derivada ya no los tiene). Columnas con los mismos textos comparten paso."""
    groups: dict[str, list[str]] = {}
    for column in inspection.columns:
        note = annotations.get(column.name)
        if note is None or not note.null_tokens:
            continue
        present = {v for token in column.missing.tokens for v in token.variants}
        tokens = [t for t in note.null_tokens if t in present]
        if tokens:
            groups.setdefault(json.dumps(sorted(tokens)), []).append(str(column.id))
    steps: list[dict[str, Any]] = []
    for index, (key, ids) in enumerate(groups.items(), start=1):
        steps.append(
            {
                "id": f"null_tokens_{index}",
                "operation": OPERATION,
                "version": 1,
                "input": (
                    {"kind": "step", "step_id": steps[-1]["id"]}
                    if steps
                    else {"kind": "input", "alias": "source"}
                ),
                "parameters": {"column_ids": ids, "tokens": json.loads(key)},
            }
        )
    return steps


def enqueue_null_cleaning(
    executions: Executions,
    datasets: Datasets,
    owner: UUID,
    inspection_run: Execution,
    inspection: Inspection,
    annotations: dict[str, ColumnAnnotation],
) -> Execution | None:
    """Encola la versión derivada si algún texto declarado sigue en la tabla. Idempotente: la
    misma tabla con los mismos pasos devuelve la ejecución existente."""
    assert inspection_run.plan
    steps = null_steps(inspection, annotations)
    if not steps:
        return None
    given = inspection_run.plan.content["input"]
    table = given["table"]
    version = datasets.get(owner, inspection_run.version_id)
    fingerprint = digest(
        "null_cleaning_request",
        {"table_sha256": str(table["sha256"]), "steps": steps, "operation": f"{OPERATION}@1"},
    )
    key = uuid5(version.id, f"null-cleaning:{fingerprint}")
    existing = executions.find_request(
        owner, inspection_run.project_id, "null_cleaning", key, fingerprint
    )
    if existing is not None:
        return existing
    content = {
        "objective": None,
        "input": {
            "kind": "table",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "artifact_id": str(table["artifact_id"]),
            "artifact_sha256": str(table["sha256"]),
        },
        "semantic_ref": None,
        "steps": steps,
        "config": inspection_run.plan.content["config"],
        # La versión derivada conserva la identidad de la fuente (correcciones heredadas).
        "source_key": str(given["source_key"]),
        "trigger": "dictionary",
    }
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
    return executions.enqueue_followup(
        owner,
        inspection_run.project_id,
        version.id,
        key,
        fingerprint,
        plan,
        str(uuid5(version.id, fingerprint)),  # correlación (36 caracteres)
        UUID(str(table["artifact_id"])),
        str(table["sha256"]),
        kind="null_cleaning",
    )
