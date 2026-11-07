from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects

CSV = (Path(__file__).resolve().parents[3] / "examples" / "ventas_calidad.csv").read_bytes()


class Flow:
    def __init__(self, client: TestClient, db: Session, objects: LocalObjects) -> None:
        self.client, self.db, self.objects = client, db, objects
        self.headers = account(client)
        self.project_id = project(client, self.headers)
        self.version = upload(client, self.headers, self.project_id, CSV).json()
        self.work()
        self.table = client.get(f"/api/v1/versions/{self.version['id']}/representations").json()[0]
        self.columns = {c["name"]: c["id"] for c in self.table["columns"]}

    def work(self) -> None:
        assert make_runner(self.db, self.objects).run_once()

    def keyed(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        return {**(headers or self.headers), "Idempotency-Key": str(uuid4())}

    def plan(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/plans",
            json={
                "table_artifact_id": self.table["id"],
                "table_sha256": self.table["sha256"],
                "steps": steps,
            },
            headers=self.keyed(),
        )
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    def trim(self) -> dict[str, Any]:
        return {
            "id": "trim",
            "operation": "cleaning.trim_whitespace",
            "version": 1,
            "input": {"kind": "input"},
            "parameters": {"column_ids": [self.columns["importe"]]},
        }

    def preview(self, plan: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"/api/v1/plans/{plan['id']}/previews", headers=self.keyed())
        assert response.status_code == 202, response.text
        self.work()
        result = self.client.get(f"/api/v1/previews/{response.json()['id']}")
        assert result.status_code == 200, result.text
        return result.json()  # type: ignore[no-any-return]


@pytest.fixture
def flow(client: TestClient, db: Session, objects: LocalObjects) -> Flow:
    return Flow(client, db, objects)


def test_preview_approve_apply_and_lineage(flow: Flow) -> None:
    client = flow.client
    plan = flow.plan([flow.trim()])
    # Un plan que transforma datos no se ejecuta como plan normal.
    blocked = client.post(f"/api/v1/plans/{plan['id']}/executions", headers=flow.keyed())
    assert blocked.status_code == 409 and blocked.json()["code"] == "APPROVAL_REQUIRED"

    preview = flow.preview(plan)
    assert preview["state"] == "succeeded" and preview["approval"] is None
    counts = preview["manifest"]["counts"]
    assert (counts["created_nulls"], counts["modified_cells"], counts["excluded_rows"]) == (1, 1, 0)
    assert preview["samples"][0]["source_row"] == 5
    effect = preview["effect_sha256"]

    wrong = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": "0" * 64},
        headers=flow.headers,
    )
    assert wrong.status_code == 409 and wrong.json()["code"] == "APPROVAL_SCOPE_MISMATCH"
    approved = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": effect},
        headers=flow.headers,
    )
    assert approved.status_code == 201, approved.text
    approval = approved.json()
    assert approval["status"] == "active" and approval["effect_sha256"] == effect
    assert approval["input_artifact_sha256"] == flow.table["sha256"]
    again = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": effect},
        headers=flow.headers,
    )
    assert again.json()["id"] == approval["id"]

    applied = client.post(f"/api/v1/approvals/{approval['id']}/apply", headers=flow.headers)
    assert applied.status_code == 202, applied.text
    run = applied.json()
    assert run["kind"] == "cleaning_apply"
    replay = client.post(f"/api/v1/approvals/{approval['id']}/apply", headers=flow.headers)
    assert replay.json()["id"] == run["id"]
    flow.work()
    assert client.get(f"/api/v1/executions/{run['id']}").json()["state"] == "succeeded"
    status = client.get(f"/api/v1/previews/{preview['execution_id']}").json()["apply"]
    assert status == {
        "execution_id": run["id"],
        "state": "succeeded",
        "error_code": None,
        "error_message": None,
    }
    revoke_late = client.post(f"/api/v1/approvals/{approval['id']}/revoke", headers=flow.headers)
    assert revoke_late.status_code == 409
    assert revoke_late.json()["code"] == "APPROVAL_ALREADY_APPLIED"

    versions = client.get(f"/api/v1/projects/{flow.project_id}/versions").json()["items"]
    v2, v1 = versions
    assert (v2["number"], v2["kind"], v2["parent_version_id"]) == (2, "derived", v1["id"])
    assert (v1["kind"], v1["parent_version_id"]) == ("imported", None)
    # Una versión por ID devuelve lo mismo que el listado (el selector la carga fuera de página).
    for item in versions:
        single = client.get(f"/api/v1/versions/{item['id']}")
        assert single.status_code == 200 and single.json() == item
    flow.work()  # perfil y calidad de v2
    diagnostic = client.get(f"/api/v1/versions/{v2['id']}/diagnostic").json()
    assert diagnostic["quality"]["completeness_percent"] == 93.33
    original = client.get(f"/api/v1/versions/{v2['id']}/original")
    assert original.status_code == 409 and original.json()["code"] == "DERIVED_HAS_NO_ORIGINAL"
    assert "descarga el original de la versión de origen" in original.json()["message"]
    assert client.get(f"/api/v1/versions/{v1['id']}/original").content == CSV
    lineage = client.get(f"/api/v1/versions/{v2['id']}/lineage").json()
    assert lineage["kind"] == "derived" and lineage["parent_version_id"] == v1["id"]
    assert lineage["producer_execution_id"] == run["id"]
    assert lineage["effect_sha256"] == effect and lineage["plan_revision_id"] == plan["id"]
    assert [op["operation"] for op in lineage["operations"]] == ["cleaning.trim_whitespace"]
    root = client.get(f"/api/v1/versions/{v1['id']}/lineage").json()
    assert root["kind"] == "imported" and root["parent_version_id"] is None


def test_revocation_cancels_queued_apply_and_blocks_new_ones(flow: Flow) -> None:
    client = flow.client
    preview = flow.preview(flow.plan([flow.trim()]))
    approval = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": preview["effect_sha256"]},
        headers=flow.headers,
    ).json()
    run = client.post(f"/api/v1/approvals/{approval['id']}/apply", headers=flow.headers).json()
    revoked = client.post(f"/api/v1/approvals/{approval['id']}/revoke", headers=flow.headers)
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert client.get(f"/api/v1/executions/{run['id']}").json()["state"] == "cancelled"
    # Revocar dos veces es idempotente; la vista previa admite una aprobación nueva.
    assert (
        client.post(f"/api/v1/approvals/{approval['id']}/revoke", headers=flow.headers).json()[
            "revoked_at"
        ]
        == revoked.json()["revoked_at"]
    )
    fresh = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": preview["effect_sha256"]},
        headers=flow.headers,
    )
    assert fresh.status_code == 201 and fresh.json()["id"] != approval["id"]
    other = flow.preview(flow.plan([flow.trim()]))
    unapproved = client.post(
        f"/api/v1/previews/{other['execution_id']}/approvals",
        json={"effect_sha256": other["effect_sha256"]},
        headers=flow.headers,
    ).json()
    client.post(f"/api/v1/approvals/{unapproved['id']}/revoke", headers=flow.headers)
    denied = client.post(f"/api/v1/approvals/{unapproved['id']}/apply", headers=flow.headers)
    assert denied.status_code == 409 and denied.json()["code"] == "APPROVAL_REVOKED"


def test_preview_requires_valid_cleaning_chain(flow: Flow) -> None:
    client = flow.client
    quality = {
        "id": "quality",
        "operation": "quality.evaluate",
        "version": 1,
        "input": {"kind": "input"},
    }
    for steps in (
        [quality],  # diagnóstico, no limpieza
        [flow.trim(), {**quality, "input": {"kind": "step", "step_id": "trim"}}],
        [flow.trim(), {**flow.trim(), "id": "again"}],  # no encadenado: ambos sobre la entrada
    ):
        plan = flow.plan(steps)
        response = client.post(f"/api/v1/plans/{plan['id']}/previews", headers=flow.keyed())
        assert response.status_code == 422 and response.json()["code"] == (
            "CLEANING_PLAN_REQUIRED"
        ), (steps, response.text)
    incomplete = flow.plan([{**flow.trim(), "parameters": {}}])
    response = client.post(f"/api/v1/plans/{incomplete['id']}/previews", headers=flow.keyed())
    assert response.status_code == 422 and response.json()["code"] == "PLAN_INCOMPLETE"


def test_cleaning_routes_enforce_ownership_and_csrf(flow: Flow) -> None:
    client = flow.client
    plan = flow.plan([flow.trim()])
    preview = flow.preview(plan)
    approval = client.post(
        f"/api/v1/previews/{preview['execution_id']}/approvals",
        json={"effect_sha256": preview["effect_sha256"]},
        headers=flow.headers,
    ).json()
    no_csrf = client.post(
        f"/api/v1/approvals/{approval['id']}/apply", headers={"Idempotency-Key": str(uuid4())}
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "CSRF_INVALID"
    intruder = account(client)
    for response in [
        client.post(f"/api/v1/plans/{plan['id']}/previews", headers=flow.keyed(intruder)),
        client.get(f"/api/v1/previews/{preview['execution_id']}"),
        client.post(
            f"/api/v1/previews/{preview['execution_id']}/approvals",
            json={"effect_sha256": preview["effect_sha256"]},
            headers=intruder,
        ),
        client.post(f"/api/v1/approvals/{approval['id']}/revoke", headers=intruder),
        client.post(f"/api/v1/approvals/{approval['id']}/apply", headers=intruder),
        client.get(f"/api/v1/versions/{flow.version['id']}/lineage"),
        client.get(f"/api/v1/versions/{flow.version['id']}"),
        client.get(f"/api/v1/versions/{uuid4()}"),
    ]:
        assert response.status_code == 404, response.text


def semantic_revision(flow: Flow, roles: dict[str, str]) -> dict[str, Any]:
    """Revisión semántica de la tabla fijada con las columnas indicadas confirmadas."""
    table = flow.table
    context = flow.client.get(f"/api/v1/representations/{table['id']}/understanding").json()
    draft = context["editable"]
    for column in draft["columns"]:
        name = next(n for n, i in flow.columns.items() if i == column["column_id"])
        if name in roles:
            column.update(
                role=roles[name],
                interpretation_type="string",
                parse_format=None,
                review_state="confirmed",
            )
    response = flow.client.post(
        f"/api/v1/representations/{table['id']}/semantic-contracts",
        json={"table_sha256": table["sha256"], "expected_revision": 0, "draft": draft},
        headers=flow.keyed(),
    )
    assert response.status_code == 200, response.text
    revision: dict[str, Any] = response.json()["revision"]
    return {k: revision[k] for k in ["id", "revision", "content_sha256"]}


def cast_id(flow: Flow, confirm: bool) -> dict[str, Any]:
    return {
        "id": "cast",
        "operation": "cleaning.cast",
        "version": 1,
        "input": {"kind": "input"},
        "parameters": {
            "column_id": flow.columns["id"],
            "type": "integer",
            "format": "integer_ascii",
            "confirm_identifier_conversion": confirm,
        },
    }


def test_identifier_guard_and_leading_zero_defense(flow: Flow) -> None:
    client = flow.client
    ref = semantic_revision(flow, {"id": "identifier"})

    def plan(confirm: bool) -> dict[str, Any]:
        response = client.post(
            f"/api/v1/projects/{flow.project_id}/plans",
            json={
                "table_artifact_id": flow.table["id"],
                "table_sha256": flow.table["sha256"],
                "semantic_ref": ref,
                "steps": [cast_id(flow, confirm)],
            },
            headers=flow.keyed(),
        )
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    guarded = plan(confirm=False)
    problems = guarded["validation"]["problems"]
    assert [(p["code"], p["resolve_in"], p["parameter"]) for p in problems] == [
        ("IDENTIFIER_CONVERSION_UNCONFIRMED", "plan_steps", "confirm_identifier_conversion")
    ]
    blocked = client.post(f"/api/v1/plans/{guarded['id']}/previews", headers=flow.keyed())
    assert blocked.status_code == 422 and blocked.json()["code"] == "PLAN_INCOMPLETE"

    # Con la confirmación explícita el plan es válido, pero «001» no es un entero ASCII
    # canónico: la conversión falla y no se publica nada (segunda línea de defensa).
    confirmed = plan(confirm=True)
    assert confirmed["validation"]["valid"]
    preview = flow.preview(confirmed)
    assert (preview["state"], preview["error_code"]) == ("failed", "CONVERSION_FAILED")
    failure = preview["failure"]
    assert failure["code"] == "CONVERSION_FAILED" and failure["total"] == 6
    assert {s["reason"] for s in failure["samples"]} == {"leading_zero"}
    assert preview["effect_sha256"] is None and preview["approval"] is None


def test_new_operations_are_published_with_column_references(flow: Flow) -> None:
    catalog = flow.client.get("/api/v1/operations").json()
    operations = {op["key"]: op for op in catalog["operations"]}
    assert catalog["catalog_version"] == "analysis-v8"
    for key, field in [
        ("cleaning.cast@1", "column_id"),
        ("cleaning.normalize_null_tokens@1", "column_ids"),
        ("cleaning.deduplicate@1", "column_ids"),
    ]:
        schema = operations[key]["parameters_schema"]
        assert schema["properties"][field]["x-dataflow-column-ref"] is True, key
        assert operations[key]["transforms_data"] is True
    cast = operations["cleaning.cast@1"]["parameters_schema"]["properties"]
    assert cast["confirm_identifier_conversion"]["default"] is False
