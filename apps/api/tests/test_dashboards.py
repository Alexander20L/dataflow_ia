"""Fase 8 · etapa 1: dashboards persistidos con revisiones inmutables y «Actualizar» explícito."""

from typing import Any
from uuid import uuid4

import pytest
from analytics_support import typed_table
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_analytics_runner import confirm_semantics, metrics_for, query_plan
from test_cleaning_runner import Scenario
from test_csv_ingestion import account

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def run_plan(s: Scenario, plan: dict[str, Any]) -> str:
    """Ejecuta el plan con el worker sin exigir éxito (las tarjetas toleran fallos)."""
    response = s.client.post(
        f"/api/v1/plans/{plan['id']}/executions",
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    drain(s)
    return str(response.json()["id"])


def drain(s: Scenario) -> None:
    runner = make_runner(s.db, s.objects)
    while runner.run_once():
        pass


def card(plan: dict[str, Any], run: str | None, view: str, title: str, **extra: Any) -> Any:
    return {
        "id": str(uuid4()),
        "title": title,
        "plan_revision_id": plan["id"],
        "execution_id": run,
        "view": view,
        "size": "medium",
        "metric": "m0",
        **extra,
    }


def post(s: Scenario, url: str, body: Any, key: str | None = None) -> Any:
    return s.client.post(
        url, json=body, headers={**s.headers, "Idempotency-Key": key or str(uuid4())}
    )


class Analyses:
    """Análisis de la v2 tipada: total (KPI), por región (barras), por mes (líneas)."""

    def __init__(self, s: Scenario) -> None:
        c = s.columns
        self.table = typed_table(s)
        income, operations = metrics_for(s, self.table)
        self.semantic = confirm_semantics(
            s, self.table, importe=("measure", "EUR"), fecha=("business_date", None)
        )
        self.metrics = [income, operations]
        self.total = query_plan(s, self.table, self.metrics, self.semantic, version=2)
        self.by_region = query_plan(
            s, self.table, self.metrics, self.semantic, version=2, dimensions=[c["region"]]
        )
        self.by_month = query_plan(
            s, self.table, [income], self.semantic, version=2, time_grain="month"
        )
        for plan in (self.total, self.by_region, self.by_month):
            assert plan["validation"]["valid"], plan["validation"]
        self.runs = {
            "total": run_plan(s, self.total),
            "by_region": run_plan(s, self.by_region),
            "by_month": run_plan(s, self.by_month),
        }

    def cards(self) -> list[dict[str, Any]]:
        return [
            card(self.total, self.runs["total"], "kpi", "Ingresos totales", size="small"),
            card(self.by_region, self.runs["by_region"], "bar", "Ingresos por región"),
            card(self.by_month, self.runs["by_month"], "line", "Ingresos por mes", size="large"),
        ]


def test_dashboard_revisions_conflict_idempotency_and_card_states(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    a = Analyses(s)
    draft = {
        "title": "Ventas",
        "cards": a.cards(),
        "filters": [{"column_id": c["region"], "values": ["Norte"]}],
    }
    key = str(uuid4())
    created = post(s, f"/api/v1/projects/{s.project_id}/dashboards", {"draft": draft}, key)
    assert created.status_code == 201, created.text
    revision = created.json()["revision"]
    family = revision["family_id"]
    assert (revision["revision"], revision["cause"]) == (1, "create")
    # Misma clave y mismo cuerpo: la misma revisión. Otro cuerpo: conflicto de idempotencia.
    again = post(s, f"/api/v1/projects/{s.project_id}/dashboards", {"draft": draft}, key)
    assert again.json()["revision"]["id"] == revision["id"]
    other = post(
        s, f"/api/v1/projects/{s.project_id}/dashboards", {"draft": {**draft, "title": "X"}}, key
    )
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"

    view = s.client.get(f"/api/v1/dashboards/{family}").json()
    states = {state["card_id"]: state for state in view["cards"]}
    kpi, bar, line = (states[c["id"]] for c in draft["cards"])
    assert [state["status"] for state in (kpi, bar, line)] == ["ready"] * 3
    assert bar["version_number"] == 2 and bar["executed_at"] and bar["result_rows"] == 4
    # El filtro de región sólo se aplica a la tarjeta que agrupa por región.
    assert [state["filters"][0]["applicable"] for state in (kpi, bar, line)] == [
        False,
        True,
        False,
    ]

    # Revisión: sin cambios no hay revisión; con cambios, la 2; revisión antigua: conflicto.
    url = f"/api/v1/dashboards/{family}/revisions"
    same = post(s, url, {"expected_revision": 1, "draft": draft})
    assert same.status_code == 200 and same.json()["changed"] is False
    moved = {**draft, "cards": [draft["cards"][2], *draft["cards"][:2]]}
    second = post(s, url, {"expected_revision": 1, "draft": moved})
    assert second.json()["changed"] and second.json()["revision"]["revision"] == 2
    stale = post(s, url, {"expected_revision": 1, "draft": draft})
    assert stale.status_code == 409 and stale.json()["code"] == "DASHBOARD_CONFLICT"
    old = s.client.get(f"/api/v1/dashboard-revisions/{revision['id']}").json()
    assert old["content"]["cards"] == draft["cards"]  # la revisión 1 no cambia
    listed = s.client.get(f"/api/v1/projects/{s.project_id}/dashboards").json()
    assert [(d["family_id"], d["revision_count"]) for d in listed] == [(family, 2)]


def test_card_validation_against_the_query(scenario: Scenario) -> None:
    s = scenario
    a = Analyses(s)

    def problems(cards: list[dict[str, Any]]) -> Any:
        response = post(
            s,
            f"/api/v1/projects/{s.project_id}/dashboards",
            {"draft": {"title": "X", "cards": cards}},
        )
        assert response.status_code == 422, response.text
        return response.json()

    kpi_by_region = problems([card(a.by_region, a.runs["by_region"], "kpi", "Mal KPI")])
    assert kpi_by_region["code"] == "DASHBOARD_INVALID"
    assert "una sola fila" in kpi_by_region["message"]
    assert (
        "agrupar por tiempo" in problems([card(a.total, a.runs["total"], "line", "L")])["message"]
    )
    foreign_run = problems([card(a.total, a.runs["by_region"], "table", "T")])
    assert "no corresponde" in foreign_run["message"]
    assert "m5" in problems([card(a.total, a.runs["total"], "table", "T", metric="m5")])["message"]
    v1 = query_plan(s, a.table, a.metrics, a.semantic)  # analytics.query@1
    assert "analytics.query@2" in problems([card(v1, None, "table", "T")])["message"]


def test_failed_execution_and_insufficient_data_do_not_break_other_cards(
    scenario: Scenario,
) -> None:
    s, c = scenario, scenario.columns
    a = Analyses(s)
    # Válido al planificar, pero 4 regiones superan el presupuesto de 1 fila al ejecutar.
    too_large = query_plan(
        s, a.table, a.metrics, a.semantic, version=2, dimensions=[c["region"]], max_result_rows=1
    )
    # Ninguna fila cumple el filtro: el resultado está vacío.
    empty = query_plan(
        s,
        a.table,
        a.metrics,
        a.semantic,
        version=2,
        filters=[{"column_id": c["region"], "operator": "eq", "values": ["Atlántida"]}],
    )
    cards = [
        card(too_large, run_plan(s, too_large), "table", "Falla"),
        card(empty, run_plan(s, empty), "kpi", "Vacía"),
        card(a.total, a.runs["total"], "kpi", "Bien"),
    ]
    family = post(
        s, f"/api/v1/projects/{s.project_id}/dashboards", {"draft": {"title": "D", "cards": cards}}
    ).json()["revision"]["family_id"]
    view = s.client.get(f"/api/v1/dashboards/{family}").json()
    assert [(state["status"], bool(state["message"])) for state in view["cards"]] == [
        ("failed", True),
        ("insufficient_data", True),
        ("ready", False),
    ]
    assert "filas" in view["cards"][0]["message"]


def test_refresh_reexecutes_on_the_chosen_version_without_changing_saved_plans(
    scenario: Scenario,
) -> None:
    s = scenario
    a = Analyses(s)
    cards = [
        card(a.total, a.runs["total"], "kpi", "Ingresos totales"),
        card(a.by_region, a.runs["by_region"], "table", "Por región"),
    ]
    family = post(
        s, f"/api/v1/projects/{s.project_id}/dashboards", {"draft": {"title": "D", "cards": cards}}
    ).json()["revision"]["family_id"]
    saved = {
        plan["id"]: s.client.get(f"/api/v1/plans/{plan['id']}").json()
        for plan in (a.total, a.by_region)
    }
    url = f"/api/v1/dashboards/{family}/refresh"

    # Misma versión: mismos planes, ejecuciones nuevas.
    key = str(uuid4())
    same = post(s, url, {"expected_revision": 1, "version_id": a.table["version_id"]}, key)
    assert same.status_code == 200, same.text
    body = same.json()
    assert (body["revision"]["revision"], body["revision"]["cause"]) == (2, "refresh")
    assert body["revision"]["refreshed_version_id"] == a.table["version_id"]
    assert [c["plan_created"] for c in body["cards"]] == [False, False]
    new_runs = [c["execution_id"] for c in body["cards"]]
    assert new_runs[0] != a.runs["total"] and all(new_runs)
    # Repetir la solicitud no crea nada nuevo.
    replay = post(s, url, {"expected_revision": 1, "version_id": a.table["version_id"]}, key)
    assert replay.json()["revision"]["id"] == body["revision"]["id"]
    drain(s)
    assert [c["status"] for c in s.client.get(f"/api/v1/dashboards/{family}").json()["cards"]] == [
        "ready",
        "ready",
    ]
    stale = post(s, url, {"expected_revision": 1, "version_id": a.table["version_id"]})
    assert stale.status_code == 409 and stale.json()["code"] == "DASHBOARD_CONFLICT"

    # v1 (texto, sin revisión semántica): planes nuevos; los que suman importe quedan con el
    # requisito semántico pendiente y sin ejecución; el resto del dashboard no se rompe.
    original = post(s, url, {"expected_revision": 2, "version_id": s.version["id"]})
    assert original.status_code == 200, original.text
    refreshed = original.json()
    assert all(c["plan_created"] for c in refreshed["cards"])
    assert all(c["execution_id"] is None and c["problems"] for c in refreshed["cards"])
    view = s.client.get(f"/api/v1/dashboards/{family}").json()
    assert {c["status"] for c in view["cards"]} == {"semantic_requirement_missing"}
    assert {c["version_number"] for c in view["cards"]} == {1}
    # Los planes guardados no cambian.
    assert {plan_id: s.client.get(f"/api/v1/plans/{plan_id}").json() for plan_id in saved} == saved


def test_privacy_csrf_and_unknown_version(scenario: Scenario) -> None:
    s = scenario
    a = Analyses(s)
    family = post(
        s,
        f"/api/v1/projects/{s.project_id}/dashboards",
        {"draft": {"title": "D", "cards": a.cards()[:1]}},
    ).json()["revision"]["family_id"]
    without_csrf = s.client.post(
        f"/api/v1/dashboards/{family}/revisions",
        json={"expected_revision": 1, "draft": {"title": "Otro"}},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert without_csrf.status_code == 403 and without_csrf.json()["code"] == "CSRF_INVALID"
    foreign_version = post(
        s,
        f"/api/v1/dashboards/{family}/refresh",
        {"expected_revision": 1, "version_id": str(uuid4())},
    )
    assert foreign_version.status_code == 404

    s.headers = account(s.client)  # otra cuenta
    assert s.client.get(f"/api/v1/dashboards/{family}").status_code == 404
    assert s.client.get(f"/api/v1/projects/{s.project_id}/dashboards").status_code == 404
    hijack = post(
        s,
        f"/api/v1/dashboards/{family}/revisions",
        {"expected_revision": 1, "draft": {"title": "X"}},
    )
    assert hijack.status_code == 404
