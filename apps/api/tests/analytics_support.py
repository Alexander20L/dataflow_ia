"""Apoyo de pruebas de analytics: versión derivada tipada de ventas_calidad.csv y métricas."""

from typing import Any
from uuid import UUID, uuid4

from test_cleaning_runner import Scenario


def step(id: str, operation: str, source: str | None, **parameters: Any) -> dict[str, Any]:
    return {
        "id": id,
        "operation": operation,
        "version": 1,
        "input": {"kind": "step", "step_id": source} if source else {"kind": "input"},
        "parameters": parameters,
    }


def typed_table(s: Scenario) -> dict[str, Any]:
    """v2: «importe» recortado y convertido a decimal(2), «fecha» a fecha. Devuelve su tabla."""
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
                "fecha",
                "cleaning.cast",
                "importe",
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
    assert scenario_run(s, derived["execution_id"])
    table: dict[str, Any] = s.client.get(
        f"/api/v1/versions/{derived['id']}/representations"
    ).json()[0]
    table["version_id"] = derived["id"]
    return table


def scenario_run(s: Scenario, execution: str) -> bool:
    return bool(s.run(UUID(execution)).state == "succeeded")


def save_metric(
    s: Scenario,
    table: dict[str, Any],
    draft: dict[str, Any],
    family: str | None = None,
    expected: int = 0,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    return s.client.post(
        f"/api/v1/representations/{table['id']}/metrics",
        json={
            "table_sha256": table["sha256"],
            "family_id": family,
            "expected_revision": expected,
            "draft": draft,
        },
        headers={**(headers or s.headers), "Idempotency-Key": key or str(uuid4())},
    )
