"""Fase 6B · B2-B3: conjuntos de reglas (revisiones inmutables) y quality.evaluate@2."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario
from test_csv_ingestion import account

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def rules(s: Scenario) -> list[dict[str, Any]]:
    c = s.columns
    return [
        {"id": "importe_obligatorio", "kind": "required", "column_id": c["importe"]},
        {"id": "clave_id", "kind": "unique_key", "column_ids": [c["id"]], "severity": "high"},
        {
            "id": "regiones",
            "kind": "allowed_values",
            "column_id": c["region"],
            "values": ["Norte", "Sur", "Este"],
        },
        {
            "id": "importe_decimal",
            "kind": "convertible",
            "column_id": c["importe"],
            "type": "decimal",
            "scale": 2,
        },
    ]


def save(
    s: Scenario,
    draft: dict[str, Any],
    expected: int,
    table: dict[str, Any] | None = None,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    table = table or s.table
    return s.client.post(
        f"/api/v1/representations/{table['id']}/quality-rulesets",
        json={"table_sha256": table["sha256"], "expected_revision": expected, "draft": draft},
        headers={**(headers or s.headers), "Idempotency-Key": key or str(uuid4())},
    )


def evaluate_plan(s: Scenario, revision: dict[str, Any], table: dict[str, Any] | None = None):
    table = table or s.table
    return s.client.post(
        f"/api/v1/projects/{s.project_id}/plans",
        json={
            "table_artifact_id": table["id"],
            "table_sha256": table["sha256"],
            "steps": [
                {
                    "id": "rules",
                    "operation": "quality.evaluate",
                    "version": 2,
                    "input": {"kind": "input"},
                    "parameters": {
                        "ruleset_revision_id": revision["id"],
                        "ruleset_sha256": revision["content_sha256"],
                    },
                }
            ],
        },
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    ).json()


def test_rulesets_are_immutable_revisions_with_conflicts_and_idempotency(
    scenario: Scenario,
) -> None:
    client = scenario.client
    draft = {"name": "Reglas de ventas", "rules": rules(scenario)}
    key = str(uuid4())
    first = save(scenario, draft, 0, key=key)
    assert first.status_code == 200, first.text
    revision = first.json()["revision"]
    assert (revision["revision"], revision["previous_revision_id"]) == (1, None)
    assert revision["content"]["rule_set"] == "csv-quality-v2"
    assert revision["content"]["base_table"]["artifact_id"] == scenario.table["id"]
    # Misma clave y contenido: la misma revisión. Sin cambios: no se crea revisión.
    assert save(scenario, draft, 0, key=key).json()["revision"]["id"] == revision["id"]
    unchanged = save(scenario, draft, 1).json()
    assert unchanged["changed"] is False and unchanged["revision"]["id"] == revision["id"]
    other_content = save(scenario, {**draft, "name": "Otro"}, 0, key=key)
    assert other_content.status_code == 409
    assert other_content.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = save(scenario, {**draft, "name": "Otro"}, 0)
    assert stale.status_code == 409 and stale.json()["code"] == "QUALITY_RULESET_CONFLICT"
    second = save(scenario, {**draft, "rules": rules(scenario)[:1]}, 1).json()["revision"]
    assert (second["revision"], second["previous_revision_id"]) == (2, revision["id"])
    # La revisión 1 sigue disponible tal cual (referencias históricas).
    assert client.get(f"/api/v1/quality-rulesets/{revision['id']}").json() == revision
    history = client.get(
        f"/api/v1/quality-ruleset-families/{revision['family_id']}/revisions"
    ).json()
    assert [item["revision"] for item in history["items"]] == [2, 1]
    context = client.get(f"/api/v1/representations/{scenario.table['id']}/quality-rulesets").json()
    assert context["own"]["head"]["id"] == second["id"] and context["own"]["applicable"]
    assert context["own"]["anchored_here"] and context["own"]["revision_count"] == 2

    invalid = save(
        scenario,
        {
            "name": "Mal",
            "rules": [
                {
                    "id": "rango",
                    "kind": "range",
                    "column_id": scenario.columns["importe"],
                    "minimum": "0",
                }
            ],
        },
        2,
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "QUALITY_RULESET_INVALID"
    assert "no admite «importe» de tipo string" in invalid.json()["message"]


def test_evaluate_v2_separates_technical_and_user_issues(scenario: Scenario) -> None:
    client = scenario.client
    revision = save(scenario, {"name": "Ventas", "rules": rules(scenario)}, 0).json()["revision"]
    plan = evaluate_plan(scenario, revision)
    assert plan["validation"]["valid"], plan["validation"]
    run = client.post(
        f"/api/v1/plans/{plan['id']}/executions",
        headers={**scenario.headers, "Idempotency-Key": str(uuid4())},
    )
    assert run.status_code == 202, run.text
    assert make_runner(scenario.db, scenario.objects).run_once()
    run_id = run.json()["id"]
    assert client.get(f"/api/v1/executions/{run_id}").json()["state"] == "succeeded"
    report = client.get(f"/api/v1/executions/{run_id}/quality-rules").json()
    assert report["rule_version"] == "csv-quality-v2"
    assert report["ruleset"] == {
        "id": revision["id"],
        "revision": 1,
        "content_sha256": revision["content_sha256"],
    }
    # La completitud es técnica (csv-quality-v1) y no incluye reglas de negocio.
    assert report["technical"]["completeness_percent"] == 96.67
    technical = sorted(i["rule"] for i in report["issues"] if i["origin"] == "technical")
    assert technical == ["Q-001", "Q-002", "Q-003"]
    user = {
        i["rule_id"]: (i["affected_rows"], i["sample_row_numbers"], i["severity"])
        for i in report["issues"]
        if i["origin"] == "user"
    }
    assert user == {
        "importe_obligatorio": (1, [2], "medium"),
        "clave_id": (1, [4], "high"),  # «001» repetido
        "regiones": (1, [3], "medium"),  # «Oeste»
        "importe_decimal": (1, [5], "medium"),  # « »: espacios; el nulo no cuenta
    }
    assert report["user"] == {"rules_evaluated": 4, "rules_failed": 4}
    # El contrato v1 no cambia: esta ejecución no publica un informe csv-quality-v1.
    assert client.get(f"/api/v1/executions/{run_id}/quality").status_code == 409


def test_plan_validation_requires_the_exact_accessible_revision(scenario: Scenario) -> None:
    revision = save(scenario, {"name": "Ventas", "rules": rules(scenario)}, 0).json()["revision"]
    forged = evaluate_plan(scenario, {**revision, "content_sha256": "0" * 64})
    assert [p["code"] for p in forged["validation"]["problems"]] == ["QUALITY_RULESET_MISMATCH"]
    missing = evaluate_plan(scenario, {**revision, "id": str(uuid4())})
    assert [p["code"] for p in missing["validation"]["problems"]] == ["QUALITY_RULESET_MISMATCH"]
    run = scenario.client.post(
        f"/api/v1/plans/{forged['id']}/executions",
        headers={**scenario.headers, "Idempotency-Key": str(uuid4())},
    )
    assert run.status_code == 422 and run.json()["code"] == "PLAN_INCOMPLETE"


def test_rulesets_are_private_to_their_owner(scenario: Scenario) -> None:
    client = scenario.client
    revision = save(scenario, {"name": "Ventas", "rules": rules(scenario)}, 0).json()["revision"]
    intruder = account(client)
    assert save(scenario, {"name": "x", "rules": []}, 1, headers=intruder).status_code == 404
    for path in [
        f"/api/v1/representations/{scenario.table['id']}/quality-rulesets",
        f"/api/v1/quality-rulesets/{revision['id']}",
        f"/api/v1/quality-ruleset-families/{revision['family_id']}/revisions",
    ]:
        assert client.get(path).status_code == 404, path
    no_csrf = client.post(
        f"/api/v1/representations/{scenario.table['id']}/quality-rulesets",
        json={
            "table_sha256": scenario.table["sha256"],
            "expected_revision": 0,
            "draft": {"name": "x"},
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert no_csrf.status_code == 403


def test_derived_versions_reuse_compatible_rules(scenario: Scenario) -> None:
    """Una derivada conserva los IDs de columna: las reglas de su origen se aplican si los
    tipos siguen siendo compatibles (convertir «importe» invalida la regla «convertible»)."""
    client, c = scenario.client, scenario.columns
    revision = save(scenario, {"name": "Ventas", "rules": rules(scenario)}, 0).json()["revision"]
    plan = scenario.plan(
        [
            {
                "id": "trim",
                "operation": "cleaning.trim_whitespace",
                "version": 1,
                "input": {"kind": "input"},
                "parameters": {"column_ids": [c["importe"]]},
            },
            {
                "id": "cast",
                "operation": "cleaning.cast",
                "version": 1,
                "input": {"kind": "step", "step_id": "trim"},
                "parameters": {
                    "column_id": c["importe"],
                    "type": "decimal",
                    "format": "decimal_dot",
                    "scale": 2,
                },
            },
        ]
    )
    preview = scenario.enqueue(plan, "cleaning_preview")
    assert scenario.run(preview).state == "succeeded"
    effect, _ = scenario.effect(preview)
    approval = scenario.approve(plan, preview, effect["effect_sha256"])
    assert scenario.run(scenario.enqueue(plan, "cleaning_apply", approval)).state == "succeeded"
    derived = client.get(f"/api/v1/projects/{scenario.project_id}/versions").json()["items"][0]
    assert scenario.run(UUID(derived["execution_id"])).state == "succeeded"
    table = client.get(f"/api/v1/versions/{derived['id']}/representations").json()[0]

    context = client.get(f"/api/v1/representations/{table['id']}/quality-rulesets").json()
    assert context["own"] is None
    [inherited] = context["others"]
    assert inherited["head"]["id"] == revision["id"] and not inherited["anchored_here"]
    assert not inherited["applicable"]
    assert [(p["rule_id"], p["code"]) for p in inherited["problems"]] == [
        ("importe_decimal", "COLUMN_TYPE_MISMATCH")
    ]
    problems = evaluate_plan(scenario, revision, table)["validation"]["problems"]
    assert [p["code"] for p in problems] == ["COLUMN_TYPE_MISMATCH"]

    # Reglas propias de la derivada: ahora el rango sobre el decimal sí es válido.
    own = save(
        scenario,
        {
            "name": "Derivada",
            "rules": [
                {"id": "positivo", "kind": "range", "column_id": c["importe"], "minimum": "0.01"},
                {"id": "obligatorio", "kind": "required", "column_id": c["importe"]},
            ],
        },
        0,
        table=table,
    ).json()["revision"]
    plan_v2 = evaluate_plan(scenario, own, table)
    assert plan_v2["validation"]["valid"], plan_v2["validation"]
