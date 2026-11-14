"""Fase 7A · A2: métricas como revisiones inmutables."""

from uuid import uuid4

import pytest
from analytics_support import save_metric, typed_table
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario
from test_csv_ingestion import account

from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def test_metric_revisions_conflicts_and_idempotency(scenario: Scenario) -> None:
    client, table = scenario.client, scenario.table
    draft = {
        "label": "Operaciones",
        "measure_column_id": scenario.columns["id"],
        "aggregation": "count",
    }
    key = str(uuid4())
    first = save_metric(scenario, table, draft, key=key)
    assert first.status_code == 200, first.text
    revision = first.json()["revision"]
    assert (revision["revision"], revision["content"]["null_policy"]) == (1, "exclude")
    assert revision["content"]["base_table"]["artifact_id"] == table["id"]
    family = revision["family_id"]
    assert save_metric(scenario, table, draft, key=key).json()["revision"]["id"] == revision["id"]
    unchanged = save_metric(scenario, table, draft, family, 1).json()
    assert unchanged["changed"] is False and unchanged["revision"]["id"] == revision["id"]
    stale = save_metric(scenario, table, {**draft, "label": "Ventas"}, family, 0)
    assert stale.status_code == 409 and stale.json()["code"] == "METRIC_CONFLICT"
    second = save_metric(scenario, table, {**draft, "label": "Ventas"}, family, 1).json()
    assert (second["revision"]["revision"], second["revision"]["previous_revision_id"]) == (
        2,
        revision["id"],
    )
    assert client.get(f"/api/v1/metrics/{revision['id']}").json() == revision
    context = client.get(f"/api/v1/representations/{table['id']}/metrics").json()
    [summary] = context["metrics"]
    assert summary["head"]["content"]["label"] == "Ventas" and summary["applicable"]
    assert summary["anchored_here"] and summary["revision_count"] == 2
    # Una métrica nueva es otra familia, aunque tenga la misma definición.
    other = save_metric(scenario, table, draft).json()["revision"]
    assert other["family_id"] != family


def test_measured_aggregations_need_numeric_columns(scenario: Scenario) -> None:
    response = save_metric(
        scenario,
        scenario.table,
        {
            "label": "Ingresos",
            "measure_column_id": scenario.columns["importe"],
            "aggregation": "sum",
        },
    )
    assert response.status_code == 422 and response.json()["code"] == "METRIC_INVALID"
    assert "Conviértela en Limpieza" in response.json()["message"]


def test_metrics_on_a_typed_derived_version(scenario: Scenario) -> None:
    client, c = scenario.client, scenario.columns
    count = save_metric(
        scenario,
        scenario.table,
        {"label": "Operaciones", "measure_column_id": c["id"], "aggregation": "count"},
    ).json()["revision"]
    typed = typed_table(scenario)
    income = save_metric(
        scenario,
        typed,
        {
            "label": "Ingresos",
            "measure_column_id": c["importe"],
            "aggregation": "sum",
            "time_column_id": c["fecha"],
            "filters": [{"column_id": c["importe"], "operator": "gt", "values": ["0"]}],
        },
    )
    assert income.status_code == 200, income.text
    # En v2 se ven las dos; la de v1 es aplicable porque «count» admite cualquier tipo.
    context = client.get(f"/api/v1/representations/{typed['id']}/metrics").json()
    applicable = {
        m["head"]["content"]["label"]: (m["applicable"], m["anchored_here"])
        for m in context["metrics"]
    }
    assert applicable == {"Operaciones": (True, False), "Ingresos": (True, True)}
    # En v1 (texto) la suma no es aplicable.
    original = client.get(f"/api/v1/representations/{scenario.table['id']}/metrics").json()
    income_v1 = next(m for m in original["metrics"] if m["head"]["content"]["label"] == "Ingresos")
    assert not income_v1["applicable"]
    # Medida y fecha de texto, y un filtro «gt» sobre texto: tres incompatibilidades.
    assert [p["code"] for p in income_v1["problems"]] == ["COLUMN_TYPE_MISMATCH"] * 3
    # Una métrica se edita desde la versión en la que se definió.
    moved = save_metric(
        scenario,
        typed,
        {"label": "Operaciones v2", "measure_column_id": c["id"], "aggregation": "count"},
        count["family_id"],
        1,
    )
    assert moved.status_code == 409 and moved.json()["code"] == "METRIC_ANCHOR_MISMATCH"


def test_metrics_are_private(scenario: Scenario) -> None:
    client = scenario.client
    draft = {"label": "x", "measure_column_id": scenario.columns["id"], "aggregation": "count"}
    revision = save_metric(scenario, scenario.table, draft).json()["revision"]
    intruder = account(client)
    assert save_metric(scenario, scenario.table, draft, headers=intruder).status_code == 404
    for path in [
        f"/api/v1/representations/{scenario.table['id']}/metrics",
        f"/api/v1/metrics/{revision['id']}",
    ]:
        assert client.get(path).status_code == 404, path
    no_csrf = client.post(
        f"/api/v1/representations/{scenario.table['id']}/metrics",
        json={"table_sha256": scenario.table["sha256"], "expected_revision": 0, "draft": draft},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert no_csrf.status_code == 403
