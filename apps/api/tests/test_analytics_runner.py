"""Fase 7A · A4: analytics.query@1 de punta a punta (plan normal, resultado y evidencia)."""

from typing import Any
from uuid import uuid4

import pytest
from analytics_support import save_metric, typed_table
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario
from test_csv_ingestion import account

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def confirm_semantics(s: Scenario, table: dict[str, Any], **roles: tuple[str, str | None]) -> Any:
    """Revisión semántica de la tabla con los roles (y moneda) indicados confirmados."""
    context = s.client.get(f"/api/v1/representations/{table['id']}/understanding").json()
    draft = context["editable"]
    names = {v: k for k, v in s.columns.items()}
    for column in draft["columns"]:
        name = names[column["column_id"]]
        if name in roles:
            role, currency = roles[name]
            column.update(role=role, currency=currency, review_state="confirmed")
    response = s.client.post(
        f"/api/v1/representations/{table['id']}/semantic-contracts",
        json={
            "table_sha256": table["sha256"],
            "expected_revision": context["revision_count"],
            "draft": draft,
        },
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    revision = response.json()["revision"]
    return {k: revision[k] for k in ["id", "revision", "content_sha256"]}


def query_plan(
    s: Scenario, table: dict[str, Any], metrics: list[dict[str, Any]], semantic: Any, **query: Any
) -> Any:
    response = s.client.post(
        f"/api/v1/projects/{s.project_id}/plans",
        json={
            "table_artifact_id": table["id"],
            "table_sha256": table["sha256"],
            "semantic_ref": semantic,
            "steps": [
                {
                    "id": "query",
                    "operation": "analytics.query",
                    "version": 1,
                    "input": {"kind": "input"},
                    "parameters": {
                        "metrics": [
                            {"revision_id": m["id"], "content_sha256": m["content_sha256"]}
                            for m in metrics
                        ],
                        **query,
                    },
                }
            ],
        },
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def execute(s: Scenario, plan: dict[str, Any]) -> str:
    run = s.client.post(
        f"/api/v1/plans/{plan['id']}/executions",
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert run.status_code == 202, run.text
    assert make_runner(s.db, s.objects).run_once()
    run_id: str = run.json()["id"]
    state = s.client.get(f"/api/v1/executions/{run_id}").json()
    assert state["state"] == "succeeded", state
    return run_id


def metrics_for(s: Scenario, table: dict[str, Any]) -> tuple[Any, Any]:
    c = s.columns
    income = save_metric(
        s,
        table,
        {
            "label": "Ingresos",
            "measure_column_id": c["importe"],
            "aggregation": "sum",
            "time_column_id": c["fecha"],
        },
    ).json()["revision"]
    operations = save_metric(
        s,
        table,
        {
            "label": "Operaciones",
            "measure_column_id": c["id"],
            "aggregation": "count",
            "time_column_id": c["fecha"],
        },
    ).json()["revision"]
    return income, operations


def test_total_amount_by_region_and_month(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    table = typed_table(s)
    income, operations = metrics_for(s, table)

    # Sin revisión semántica: el requisito queda pendiente y enlaza con Entendimiento.
    pending = query_plan(s, table, [income], None, dimensions=[c["region"]], time_grain="month")[
        "validation"
    ]["problems"]
    assert {(p["code"], p["resolve_in"]) for p in pending} == {
        ("SEMANTIC_REQUIREMENT_MISSING", "understanding")
    }
    blocked = s.client.post(
        f"/api/v1/plans/{query_plan(s, table, [income], None)['id']}/executions",
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert blocked.status_code == 422 and blocked.json()["code"] == "PLAN_INCOMPLETE"

    semantic = confirm_semantics(
        s, table, importe=("measure", "EUR"), fecha=("business_date", None)
    )
    plan = query_plan(
        s, table, [income, operations], semantic, dimensions=[c["region"]], time_grain="month"
    )
    assert plan["validation"]["valid"], plan["validation"]
    run = execute(s, plan)
    result = s.client.get(f"/api/v1/executions/{run}/analysis").json()
    rows = [
        (r["labels"]["d0"], r["labels"]["period"], r["values"]["m0"], r["values"]["m1"])
        for r in result["rows"]
    ]
    # Norte: 100.50 + 100.50 (fila repetida). «Sur» sólo tiene importe nulo: suma None.
    assert rows == [
        ("Este", "2026-01", "120.25", "1"),
        ("Norte", "2026-01", "201.00", "3"),
        ("Oeste", "2026-01", "80.00", "1"),
        ("Sur", "2026-01", None, "1"),
    ]
    income_def = result["metrics"][0]
    assert (income_def["label"], income_def["currency"], income_def["scale"]) == (
        "Ingresos",
        "EUR",
        2,
    )
    assert income_def["counts"] == {
        "input_rows": 6,
        "excluded_by_filters": 0,
        "excluded_by_nulls": 2,  # registro 2 (vacío) y 5 (sólo espacios → nulo)
        "included_rows": 4,
    }
    assert result["scope"]["semantic_ref"] == semantic
    assert result["scope"]["input"]["artifact_id"] == table["id"]

    # «De dónde sale este número»: cada cifra se resuelve por su evidence_id.
    north = result["rows"][1]
    evidence = s.client.get(f"/api/v1/executions/{run}/evidence/{north['evidence']['m0']}").json()
    assert evidence["value"] == "201.00" and evidence["labels"]["d0"] == "Norte"
    reference = evidence["reference"]
    assert reference["metric"] == {
        "revision_id": income["id"],
        "content_sha256": income["content_sha256"],
    }
    assert reference["row_key"]["dimensions"] == [{"column_id": c["region"], "value": "Norte"}]
    assert reference["row_key"]["period"] == {"grain": "month", "start": "2026-01-01"}
    assert reference["input"]["version_id"] == table["version_id"]
    missing = s.client.get(f"/api/v1/executions/{run}/evidence/{'0' * 64}")
    assert missing.status_code == 404

    # Determinismo: otra ejecución del mismo plan calcula lo mismo (evidencia propia).
    again = s.client.get(f"/api/v1/executions/{execute(s, plan)}/analysis").json()
    assert [r["values"] for r in again["rows"]] == [r["values"] for r in result["rows"]]
    assert again["rows"][1]["evidence"]["m0"] != north["evidence"]["m0"]


def test_units_filters_and_privacy(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    table = typed_table(s)
    semantic = confirm_semantics(
        s, table, importe=("measure", "EUR"), fecha=("business_date", None)
    )
    filtered = save_metric(
        s,
        table,
        {
            "label": "Ingresos del Norte",
            "measure_column_id": c["importe"],
            "aggregation": "avg",
            "filters": [{"column_id": c["region"], "operator": "eq", "values": ["Norte"]}],
        },
    ).json()["revision"]
    plan = query_plan(
        s,
        table,
        [filtered],
        semantic,
        filters=[{"column_id": c["fecha"], "operator": "gte", "values": ["2026-01-02"]}],
        avg_scale=3,
    )
    assert plan["validation"]["valid"], plan["validation"]
    run = execute(s, plan)
    result = s.client.get(f"/api/v1/executions/{run}/analysis").json()
    # Norte desde el 2 de enero: sólo el registro 5, de importe nulo. Sin filas incluidas,
    # no hay grupos: el resultado está vacío, no es 0.
    assert result["rows"] == []
    counts = result["metrics"][0]["counts"]
    assert counts == {
        "input_rows": 6,
        "excluded_by_filters": 5,
        "excluded_by_nulls": 1,
        "included_rows": 0,
    }
    unknown = query_plan(
        s, table, [filtered], semantic, filters=[{"column_id": str(uuid4()), "operator": "is_null"}]
    )["validation"]["problems"]
    assert [p["code"] for p in unknown] == ["UNKNOWN_COLUMN"]

    account(s.client)  # el cliente pasa a la sesión de otra cuenta
    assert s.client.get(f"/api/v1/executions/{run}/analysis").status_code == 404
