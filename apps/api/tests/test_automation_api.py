"""Fase 11B: política de automatización por API y aprobación por política."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_api import Flow
from test_csv_ingestion import account

from dataflow.modules.datasets.objects import LocalObjects

TRIM_POLICY: dict[str, Any] = {
    "enabled": True,
    "allowed_operations": ["cleaning.trim_whitespace"],
    "column_scopes": [{"operation": "cleaning.trim_whitespace", "columns": ["*"]}],
}


@pytest.fixture
def flow(client: TestClient, db: Session, objects: LocalObjects) -> Flow:
    return Flow(client, db, objects)


def save(flow: Flow, content: dict[str, Any], expected: int) -> Any:
    return flow.client.post(
        f"/api/v1/projects/{flow.project_id}/automation-policy",
        json={"expected_revision": expected, "content": content},
        headers=flow.keyed(),
    )


def approve(flow: Flow, preview: dict[str, Any]) -> dict[str, Any]:
    response = flow.client.post(
        f"/api/v1/previews/{preview['execution_id']}/policy-approvals", headers=flow.headers
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def codes(decision: dict[str, Any]) -> list[str]:
    return [reason["code"] for reason in decision["evaluation"]["reasons"]]


def test_policy_revisions_conflicts_and_validation(flow: Flow) -> None:
    client = flow.client
    path = f"/api/v1/projects/{flow.project_id}/automation-policy"
    assert client.get(path).json() == {"revision": None}
    first = save(flow, TRIM_POLICY, 0)
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1 and first.json()["content"]["enabled"] is True
    same = save(flow, TRIM_POLICY, 1)
    assert same.json()["id"] == first.json()["id"]  # sin cambios no hay revisión
    stale = save(flow, {"enabled": False}, 0)
    assert stale.status_code == 409 and stale.json()["code"] == "AUTOMATION_POLICY_CONFLICT"
    second = save(flow, {"enabled": False}, 1)
    assert second.json()["revision"] == 2
    assert second.json()["previous_revision_id"] == first.json()["id"]
    assert client.get(path).json()["revision"]["id"] == second.json()["id"]
    exact = client.get(f"/api/v1/automation-policies/{first.json()['id']}").json()
    assert exact == first.json()
    invalid = save(
        flow,
        {"enabled": True, "column_scopes": [{"operation": "cleaning.cast", "columns": ["*"]}]},
        2,
    )
    assert invalid.status_code == 422


def test_policy_blocks_then_approves_the_exact_effect_and_applies(flow: Flow) -> None:
    client = flow.client
    importe = flow.columns["importe"]
    preview = flow.preview(flow.plan([flow.trim()]))
    effects = {item["column_id"]: item for item in preview["column_effects"]}
    # ventas_calidad.csv: recortar «importe» deja un valor sólo de espacios como nulo.
    assert effects[importe] == {"column_id": importe, "modified_cells": 1, "created_nulls": 1}
    assert sum(item["created_nulls"] for item in effects.values()) == 1

    assert codes(approve(flow, preview)) == ["POLICY_MISSING"]
    assert save(flow, TRIM_POLICY, 0).status_code == 200
    blocked = approve(flow, preview)
    assert blocked["evaluation"]["decision"] == "blocked" and blocked["approval_id"] is None
    assert set(codes(blocked)) == {"NULLS_CREATED_ABOVE_LIMIT"}
    assert "importe" in {reason["column"] for reason in blocked["evaluation"]["reasons"]}
    current = client.get(f"/api/v1/previews/{preview['execution_id']}").json()
    assert current["approval"] is None  # bloquear no cambia nada

    permissive = {**TRIM_POLICY, "max_nulls_created_pct": "50"}
    policy = save(flow, permissive, 1).json()
    decision = approve(flow, preview)
    assert decision["evaluation"] == {"decision": "approved", "reasons": []}
    assert decision["policy_revision_id"] == policy["id"]
    assert decision["effect_sha256"] == preview["effect_sha256"]
    approval = client.get(f"/api/v1/previews/{preview['execution_id']}").json()["approval"]
    assert approval["id"] == decision["approval_id"]
    assert approval["effect_sha256"] == preview["effect_sha256"]
    origin = client.get(f"/api/v1/approvals/{approval['id']}/origin").json()
    assert origin["automatic"] is True and origin["policy_revision"] == 2
    assert origin["executor"] == "manual" and origin["evaluation"]["decision"] == "approved"
    assert approve(flow, preview)["approval_id"] == approval["id"]  # se reutiliza

    applied = client.post(f"/api/v1/approvals/{approval['id']}/apply", headers=flow.headers)
    assert applied.status_code == 202, applied.text
    flow.work()
    run = client.get(f"/api/v1/executions/{applied.json()['id']}").json()
    assert run["state"] == "succeeded"


def test_manual_approvals_are_not_automatic(flow: Flow) -> None:
    preview = flow.preview(flow.plan([flow.trim()]))
    manual = flow.client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": preview["effect_sha256"]},
        headers=flow.headers,
    ).json()
    origin = flow.client.get(f"/api/v1/approvals/{manual['id']}/origin").json()
    assert origin == {
        "approval_id": manual["id"],
        "automatic": False,
        "policy_revision_id": None,
        "policy_revision": None,
        "executor": None,
        "pipeline_run_id": None,
        "evaluation": None,
        "created_at": None,
    }


def test_new_policy_revision_revokes_pending_automatic_approvals(flow: Flow) -> None:
    preview = flow.preview(flow.plan([flow.trim()]))
    save(flow, {**TRIM_POLICY, "max_nulls_created_pct": "50"}, 0)
    approved = approve(flow, preview)
    assert approved["approval_id"]
    assert save(flow, {"enabled": False}, 1).status_code == 200
    current = flow.client.get(f"/api/v1/previews/{preview['execution_id']}").json()
    assert current["approval"] is None
    assert codes(approve(flow, preview)) == ["POLICY_DISABLED"]


def test_access_is_limited_to_the_owner(flow: Flow) -> None:
    preview = flow.preview(flow.plan([flow.trim()]))
    policy = save(flow, TRIM_POLICY, 0).json()
    stranger = account(flow.client)
    client = flow.client
    assert client.get(f"/api/v1/projects/{flow.project_id}/automation-policy").status_code == 404
    assert client.get(f"/api/v1/automation-policies/{policy['id']}").status_code == 404
    denied = client.post(
        f"/api/v1/previews/{preview['execution_id']}/policy-approvals", headers=stranger
    )
    assert denied.status_code == 404
