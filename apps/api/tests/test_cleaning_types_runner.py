"""Fase 6 · A5: efecto tipado, errores estrictos y versión derivada con columnas tipadas."""

import io
from typing import Any
from uuid import UUID, uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario

from dataflow.bootstrap.services import make_executions
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.tabular import table_logical_sha256


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def step(id: str, operation: str, source: str | None, **parameters: Any) -> dict[str, Any]:
    return {
        "id": id,
        "operation": f"cleaning.{operation}",
        "version": 1,
        "input": {"kind": "step", "step_id": source} if source else {"kind": "input"},
        "parameters": parameters,
    }


def typed_plan(scenario: Scenario) -> dict[str, Any]:
    c = scenario.columns
    return scenario.plan(
        [
            step("trim", "trim_whitespace", None, column_ids=[c["importe"]]),
            step(
                "importe",
                "cast",
                "trim",
                column_id=c["importe"],
                type="decimal",
                format="decimal_dot",
                scale=1,
            ),
            step(
                "unidades",
                "cast",
                "importe",
                column_id=c["unidades"],
                type="integer",
                format="integer_ascii",
            ),
            step("fecha", "cast", "unidades", column_id=c["fecha"], type="date", format="iso_date"),
            step(
                "dedupe",
                "deduplicate",
                "fecha",
                column_ids=list(c.values()),
                null_keys="group_nulls",
            ),
        ]
    )


def test_typed_preview_apply_and_derived_version(scenario: Scenario) -> None:
    client, c = scenario.client, scenario.columns
    plan = typed_plan(scenario)
    first, second = (scenario.enqueue(plan, "cleaning_preview") for _ in range(2))
    assert scenario.run(first).state == "succeeded"
    assert scenario.run(second).state == "succeeded"
    effect, samples = scenario.effect(first)
    assert effect["effect_sha256"] == scenario.effect(second)[0]["effect_sha256"]  # determinista
    manifest = effect["manifest"]
    # Registro 4 repite el 1; registro 5 («importe» sólo espacios) pasa a nulo; 120.25 → 120.2.
    assert manifest["counts"] == {
        "input_rows": 6,
        "output_rows": 5,
        "excluded_rows": 1,
        "modified_rows": 5,
        # importe: 4 (tres cambian de tipo y una pasa a nulo); unidades y fecha: 5 cada una.
        "modified_cells": 14,
        "created_nulls": 1,
    }
    assert manifest["rounded_cells"] == 1
    types = {
        col["name"]: (col["technical_type"], col["type_parameters"])
        for col in manifest["output"]["columns"]
    }
    assert types == {
        "id": ("string", {}),
        "fecha": ("date", {}),
        "region": ("string", {}),
        "importe": ("decimal", {"scale": 1}),
        "unidades": ("integer", {}),
    }
    by_row = {sample["source_row"]: sample for sample in samples}
    assert by_row[4]["change"] == "excluded"
    assert (
        by_row[6]["before"][c["importe"]] == "120.25"
        and by_row[6]["after"][c["importe"]] == "120.2"
    )
    assert by_row[1]["before"][c["unidades"]] == "2" and by_row[1]["after"][c["unidades"]] == "2"

    approval = scenario.approve(plan, first, effect["effect_sha256"])
    applied = scenario.enqueue(plan, "cleaning_apply", approval)
    assert scenario.run(applied).state == "succeeded"
    versions = client.get(f"/api/v1/projects/{scenario.project_id}/versions").json()["items"]
    derived = versions[0]
    assert derived["kind"] == "derived"
    assert scenario.run(UUID(derived["execution_id"])).state == "succeeded"  # perfil y calidad

    table = client.get(f"/api/v1/versions/{derived['id']}/representations").json()[0]
    assert [col["technical_type"] for col in table["columns"]] == [
        "string",
        "date",
        "string",
        "decimal",
        "integer",
    ]
    stored = next(
        a for a in make_executions(scenario.db).representations(scenario.owner, UUID(derived["id"]))
    )
    frame = pl.read_parquet(io.BytesIO(scenario.objects.read(stored.content)))
    assert frame.schema["importe"] == pl.Decimal(38, 1) and frame.schema["fecha"] == pl.Date
    assert stored.logical_content_sha256 == manifest["output"]["logical_content_sha256"]
    assert table_logical_sha256(stored.columns or [], frame) == stored.logical_content_sha256

    diagnostic = client.get(f"/api/v1/versions/{derived['id']}/diagnostic").json()
    profile = {col["name"]: col for col in diagnostic["profile"]["columns"]}
    assert profile["importe"]["technical_type"] == "decimal"
    assert profile["importe"]["numeric"]["total"] == "300.7"  # 100.5 + 80.0 + 120.2
    assert profile["fecha"]["examples"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    quality = diagnostic["quality"]
    assert {(i["rule"], i["column"]) for i in quality["issues"]} == {
        ("Q-001", "importe"),  # sin Q-003: ya no es texto
    }
    preview = client.get(f"/api/v1/versions/{derived['id']}/preview").json()
    assert preview["rows"][-1]["values"] == {
        "id": "005",
        "fecha": "2026-01-05",
        "region": "Este",
        "importe": "120.2",
        "unidades": "2",
    }

    # Sobre la tabla tipada, recortar o volver a convertir «importe» es incompatible.
    response = client.post(
        f"/api/v1/projects/{scenario.project_id}/plans",
        json={
            "table_artifact_id": table["id"],
            "table_sha256": table["sha256"],
            "steps": [
                step("trim", "trim_whitespace", None, column_ids=[c["importe"]]),
                step("nulls", "filter_rows", None, column_ids=[c["importe"]], predicate="is_null"),
            ],
        },
        headers={**scenario.headers, "Idempotency-Key": str(uuid4())},
    )
    problems = response.json()["validation"]["problems"]
    assert [(p["code"], p["step_id"]) for p in problems] == [("COLUMN_TYPE_MISMATCH", "trim")]


def test_conversion_failure_lists_values_and_publishes_nothing(scenario: Scenario) -> None:
    c = scenario.columns
    # Sin recortar, el «importe» sólo de espacios (registro 5) no convierte.
    plan = scenario.plan(
        [
            step(
                "importe",
                "cast",
                None,
                column_id=c["importe"],
                type="decimal",
                format="decimal_dot",
                scale=2,
            )
        ]
    )
    preview = scenario.enqueue(plan, "cleaning_preview")
    run = scenario.run(preview)
    assert (run.state, run.error_code) == ("failed", "CONVERSION_FAILED")
    view = scenario.client.get(f"/api/v1/previews/{preview}").json()
    assert view["effect_sha256"] is None and view["manifest"] is None
    assert view["failure"] == {
        "code": "CONVERSION_FAILED",
        "total": 1,
        "samples": [
            {
                "column_id": c["importe"],
                "column": "importe",
                "source_row": 5,
                "value": " ",
                "reason": "whitespace",
                "message": "Tiene espacios en los bordes; añade un paso «Recortar espacios» antes.",
            }
        ],
    }
    approve = scenario.client.post(
        f"/api/v1/previews/{preview}/approvals",
        json={"effect_sha256": "0" * 64},
        headers=scenario.headers,
    )
    assert approve.status_code == 409 and approve.json()["code"] == "PREVIEW_NOT_READY"
    assert make_executions(scenario.db).artifacts(scenario.owner, preview) == []
    assert scenario.derived_count() == 0


def test_rejected_null_keys_fail_with_detail(scenario: Scenario) -> None:
    c = scenario.columns
    plan = scenario.plan(
        [step("dedupe", "deduplicate", None, column_ids=[c["importe"]], null_keys="reject")]
    )
    preview = scenario.enqueue(plan, "cleaning_preview")
    run = scenario.run(preview)
    assert (run.state, run.error_code) == ("failed", "NULL_KEY_REJECTED")
    failure = scenario.client.get(f"/api/v1/previews/{preview}").json()["failure"]
    assert failure["total"] == 1
    assert [(s["source_row"], s["reason"]) for s in failure["samples"]] == [(2, "null_key")]
    assert scenario.derived_count() == 0


def test_null_tokens_create_nulls_counted_in_the_effect(scenario: Scenario) -> None:
    c = scenario.columns
    plan = scenario.plan(
        [step("tokens", "normalize_null_tokens", None, column_ids=[c["region"]], tokens=["Sur"])]
    )
    preview = scenario.enqueue(plan, "cleaning_preview")
    assert scenario.run(preview).state == "succeeded"
    effect, samples = scenario.effect(preview)
    counts = effect["manifest"]["counts"]
    assert (counts["created_nulls"], counts["modified_cells"]) == (1, 1)
    assert effect["manifest"]["rounded_cells"] == 0
    assert samples[0]["source_row"] == 2 and samples[0]["after"] == {c["region"]: None}
