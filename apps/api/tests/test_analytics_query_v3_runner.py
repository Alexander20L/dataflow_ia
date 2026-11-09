"""Fase 11E: analytics.query@3 de punta a punta (métricas, planning, ejecución, evidencia y CSV)."""

from typing import Any
from uuid import UUID

import pytest
from analytics_support import save_metric, step
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_analytics_runner import confirm_semantics, execute, query_plan
from test_cleaning_runner import Scenario

from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def inventory_table(s: Scenario) -> dict[str, Any]:
    """v2 de ventas_calidad.csv con «importe» decimal(2), «unidades» entero y «fecha» fecha."""
    c = s.columns
    plan = s.plan(
        [
            step("trim", "cleaning.trim_whitespace", None, column_ids=[c["importe"]]),
            step(
                "importe",
                "cleaning.cast",
                "trim",
                column_id=c["importe"],
                type="decimal",
                format="decimal_dot",
                scale=2,
            ),
            step(
                "unidades",
                "cleaning.cast",
                "importe",
                column_id=c["unidades"],
                type="integer",
                format="integer_ascii",
            ),
            step(
                "fecha",
                "cleaning.cast",
                "unidades",
                column_id=c["fecha"],
                type="date",
                format="iso_date",
            ),
        ]
    )
    preview = s.enqueue(plan, "cleaning_preview")
    assert s.run(preview).state == "succeeded"
    effect, _ = s.effect(preview)
    approval = s.approve(plan, preview, effect["effect_sha256"])
    assert s.run(s.enqueue(plan, "cleaning_apply", approval)).state == "succeeded"
    derived = s.client.get(f"/api/v1/projects/{s.project_id}/versions").json()["items"][0]
    assert s.run(UUID(derived["execution_id"])).state == "succeeded"
    table: dict[str, Any] = s.client.get(
        f"/api/v1/versions/{derived['id']}/representations"
    ).json()[0]
    table["version_id"] = derived["id"]
    return table


def test_query_v3_sum_product_and_last_snapshot_end_to_end(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    table = inventory_table(s)

    # La segunda medida debe ser numérica (validación de la métrica al guardarla).
    invalid = save_metric(
        s,
        table,
        {
            "label": "Valor",
            "measure_column_id": c["unidades"],
            "aggregation": "sum_product",
            "second_measure_column_id": c["region"],
        },
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "METRIC_INVALID"
    response = save_metric(
        s,
        table,
        {
            "label": "Valor del inventario",
            "measure_column_id": c["unidades"],
            "aggregation": "sum_product",
            "second_measure_column_id": c["importe"],
            "time_column_id": c["fecha"],
        },
    )
    assert response.status_code == 200, response.text
    value = response.json()["revision"]
    assert value["content"]["second_measure_column_id"] == c["importe"]
    last = save_metric(
        s,
        table,
        {
            "label": "Unidades del último corte",
            "measure_column_id": c["unidades"],
            "aggregation": "sum",
            "time_column_id": c["fecha"],
            "semi_additive": "last_snapshot",
        },
    ).json()["revision"]
    semantic = confirm_semantics(
        s,
        table,
        importe=("measure", "EUR"),
        unidades=("measure", None),
        fecha=("business_date", None),
    )

    # @2 no calcula estas métricas: el plan queda pendiente con un motivo verificable.
    old = query_plan(s, table, [value], semantic, version=2)
    assert [p["code"] for p in old["validation"]["problems"]] == ["METRIC_UNSUPPORTED"]

    plan = query_plan(s, table, [value], semantic, version=3, dimensions=[c["region"]])
    assert plan["validation"]["valid"], plan["validation"]
    assert plan["content"]["config"]["operation_catalog"] == "analysis-v11"
    run = execute(s, plan)
    result = s.client.get(f"/api/v1/executions/{run}/analysis").json()
    assert result["operation"] == "analytics.query@3"
    # unidades × importe por fila; los importes nulos se excluyen y se cuentan («Sur» sólo
    # tiene un importe nulo: sin filas, no hay grupo).
    assert [(r["labels"]["d0"], r["values"]["m0"]) for r in result["rows"]] == [
        ("Este", "240.50"),
        ("Norte", "402.00"),
        ("Oeste", "240.00"),
    ]
    definition = result["metrics"][0]
    assert (definition["currency"], definition["scale"], definition["second_measure_column"]) == (
        "EUR",
        2,
        "importe",
    )
    assert definition["counts"]["excluded_by_nulls"] == 2
    north = result["rows"][1]
    evidence = s.client.get(f"/api/v1/executions/{run}/evidence/{north['evidence']['m0']}").json()
    assert (evidence["operation"], evidence["value"]) == ("analytics.query@3", "402.00")
    assert evidence["reference"]["cell"] == "value"

    # Último corte sin agrupar por tiempo: sólo las filas de la última fecha (5 de enero).
    kpi = execute(s, query_plan(s, table, [last], semantic, version=3))
    snapshot = s.client.get(f"/api/v1/executions/{kpi}/analysis").json()
    assert snapshot["rows"][0]["values"] == {"m0": "2"}
    assert snapshot["rows"][0]["snapshots"] == {"m0": "2026-01-05"}
    assert snapshot["metrics"][0]["snapshot"]["superseded_rows"] == 5
    cell = s.client.get(
        f"/api/v1/executions/{kpi}/evidence/{snapshot['rows'][0]['evidence']['m0']}"
    ).json()
    assert (cell["value"], cell["snapshot"]) == ("2", "2026-01-05")

    csv = s.client.get(f"/api/v1/executions/{run}/analysis.csv")
    assert csv.status_code == 200 and "402.00" in csv.text
