"""Fase 11E: dashboard automático determinista publicado por el pipeline."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_automation_interpretation import SECOND, TYPED_POLICY, save_mapping
from test_automation_pipeline import Pipeline

from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.templates.analysis import analysis_spec
from dataflow.modules.templates.contracts import MappingContent


@pytest.fixture
def pipe(client: TestClient, db: Session, objects: LocalObjects) -> Pipeline:
    return Pipeline(client, db, objects)


def test_sales_spec_is_stable_and_never_mixes_units() -> None:
    from test_templates import SALES

    ids = {name: __import__("uuid").uuid4() for name in ("fecha", "importe", "region")}
    spec = analysis_spec(MappingContent.model_validate(SALES), ids)
    assert spec is not None
    assert [q.name for q in spec.queries] == ["kpis", "monthly", "top", "detail"]
    assert [c.view for q in spec.queries for c in q.cards] == [
        "kpi",
        "kpi",
        "kpi",
        "line",
        "bar",
        "table",
    ]
    assert analysis_spec(MappingContent(template="generic@1"), {}) is None


def test_inventory_spec_uses_last_snapshot_and_separates_currency() -> None:
    content = MappingContent.model_validate(
        {
            "template": "inventory@1",
            "roles": [
                {"role": "product", "column": "sku", "target_type": "string"},
                {"role": "quantity", "column": "stock", "target_type": "integer"},
                {"role": "cut_date", "column": "corte", "target_type": "date"},
                {"role": "unit_cost", "column": "costo", "target_type": "decimal", "scale": 2},
            ],
            "currency": "PEN",
            "unit": "unidades",
            "grain": "producto por fecha de corte",
        }
    )
    ids = {name: __import__("uuid").uuid4() for name in ("sku", "stock", "corte", "costo")}
    spec = analysis_spec(content, ids)
    assert spec is not None
    metrics = {m.name: m.draft for m in spec.metrics}
    assert metrics["units"]["semi_additive"] == "last_snapshot"
    assert metrics["value"]["aggregation"] == "sum_product"
    assert all(q.version == 3 for q in spec.queries)
    # Unidades y moneda nunca en la misma consulta.
    for query in spec.queries:
        assert not {"units", "value"} <= set(query.metrics)


def test_pipeline_publishes_and_then_revises_the_same_dashboard(pipe: Pipeline) -> None:
    pipe.policy(TYPED_POLICY)
    save_mapping(pipe)
    first = pipe.load()
    run = pipe.drive(first["id"], limit=30)
    assert run["state"] == "completed", run
    assert run["dashboard_family_id"] and run["dashboard_revision_id"]
    view = pipe.client.get(f"/api/v1/dashboards/{run['dashboard_family_id']}").json()
    assert view["head"]["revision"] == 1 and len(view["cards"]) == 6
    assert {card["status"] for card in view["cards"]} == {"ready"}, view["cards"]

    second = pipe.load(SECOND)
    again = pipe.drive(second["id"], limit=30)
    assert again["state"] == "completed", again
    assert again["dashboard_family_id"] == run["dashboard_family_id"]  # no se duplica
    view = pipe.client.get(f"/api/v1/dashboards/{run['dashboard_family_id']}").json()
    assert view["head"]["revision"] == 2
    assert [c["card_id"] for c in view["cards"]] == [
        c["card_id"]
        for c in pipe.client.get(f"/api/v1/dashboards/{run['dashboard_family_id']}").json()["cards"]
    ]
