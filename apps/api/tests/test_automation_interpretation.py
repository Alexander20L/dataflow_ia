"""Fase 11D: el pipeline pide la interpretación la primera vez y la reutiliza si es compatible."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_automation_pipeline import FULL_POLICY, Pipeline
from test_templates import SALES

from dataflow.modules.datasets.objects import LocalObjects

TYPED_POLICY: dict[str, Any] = {
    **FULL_POLICY,
    "allowed_operations": [*FULL_POLICY["allowed_operations"], "cleaning.cast"],
    "column_scopes": [
        *FULL_POLICY["column_scopes"],
        {"operation": "cleaning.cast", "columns": ["fecha", "importe"]},
    ],
}
SECOND = (
    b"id,fecha,region,importe,unidades\n010,2026-02-01,Sur,15.00,1\n011,2026-02-02,Norte,7.50,2\n"
)
WITHOUT_AMOUNT = b"id,fecha,region,unidades\n020,2026-03-01,Sur,1\n"


@pytest.fixture
def pipe(client: TestClient, db: Session, objects: LocalObjects) -> Pipeline:
    return Pipeline(client, db, objects)


def save_mapping(pipe: Pipeline) -> dict[str, Any]:
    response = pipe.client.post(
        f"/api/v1/projects/{pipe.project_id}/template-mappings",
        json={"expected_revision": 0, "content": SALES},
        headers={**pipe.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def semantics_of(pipe: Pipeline, version: str) -> dict[str, Any]:
    table = pipe.client.get(f"/api/v1/versions/{version}/representations").json()[0]
    context = pipe.client.get(f"/api/v1/representations/{table['id']}/understanding").json()
    return {c["name"]: c for c in context["head"]["content"]["columns"]}, table  # type: ignore[return-value]


def test_first_load_asks_then_resume_reprocesses_with_the_confirmed_mapping(
    pipe: Pipeline,
) -> None:
    pipe.policy(TYPED_POLICY)
    version = pipe.load()
    run = pipe.drive(version["id"])
    assert run["state"] == "needs_review" and run["step"] == "interpret"
    assert [r["code"] for r in run["reasons"]] == ["MAPPING_REQUIRED"]
    first_clean = run["result_version_id"]
    assert pipe.active()["version_id"] == first_clean  # type: ignore[index]

    mapping = save_mapping(pipe)
    resumed = pipe.client.post(f"/api/v1/automation-runs/{run['id']}/resume", headers=pipe.headers)
    assert resumed.status_code == 200, resumed.text
    run = pipe.drive(version["id"])
    assert run["state"] == "completed", run
    assert run["pass_number"] == 2 and run["mapping_revision_id"] == mapping["id"]
    assert run["result_version_id"] != first_clean
    assert pipe.active()["version_id"] == run["result_version_id"]  # type: ignore[index]
    columns, table = semantics_of(pipe, run["result_version_id"])
    types = {c["name"]: c["technical_type"] for c in table["columns"]}
    assert types["importe"] == "decimal" and types["fecha"] == "date"
    assert columns["importe"]["role"] == "measure" and columns["importe"]["currency"] == "PEN"
    assert columns["fecha"]["role"] == "business_date"
    assert columns["region"]["role"] == "dimension"
    assert all(columns[n]["review"]["state"] == "confirmed" for n in ("importe", "fecha", "region"))


def test_compatible_load_reuses_the_mapping_without_asking(pipe: Pipeline) -> None:
    pipe.policy(TYPED_POLICY)
    mapping = save_mapping(pipe)
    version = pipe.load(SECOND)
    run = pipe.drive(version["id"])
    assert run["state"] == "completed", run
    assert run["mapping_revision_id"] == mapping["id"] and run["semantic_revision_id"]
    columns, _ = semantics_of(pipe, run["result_version_id"])
    assert columns["importe"]["role"] == "measure"


def test_incompatible_load_stops_before_cleaning(pipe: Pipeline) -> None:
    pipe.policy(TYPED_POLICY)
    save_mapping(pipe)
    version = pipe.load(WITHOUT_AMOUNT)
    run = pipe.drive(version["id"])
    assert run["state"] == "needs_review" and run["step"] == "propose"
    assert [r["code"] for r in run["reasons"]] == ["MAPPING_INCOMPATIBLE"]
    assert "importe" in run["reasons"][0]["measured"]
    assert run["plan_revision_id"] is None and pipe.active() is None


def test_only_interpretation_stops_can_be_resumed(pipe: Pipeline) -> None:
    pipe.policy(
        {
            "enabled": True,
            "allowed_operations": ["cleaning.trim_whitespace"],
            "column_scopes": [{"operation": "cleaning.trim_whitespace", "columns": ["*"]}],
        }
    )
    version = pipe.load()
    run = pipe.drive(version["id"])
    assert run["state"] == "needs_review"
    refused = pipe.client.post(f"/api/v1/automation-runs/{run['id']}/resume", headers=pipe.headers)
    assert refused.status_code == 409 and refused.json()["code"] == "AUTOMATION_RUN_NOT_RESUMABLE"
