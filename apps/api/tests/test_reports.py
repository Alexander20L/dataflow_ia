"""Fase 9 · etapa 1: informes con revisiones, procedencia por bloque y PDF en el worker."""

import base64
import hashlib
import re
import zlib
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_analytics_runner import query_plan
from test_cleaning_runner import Scenario
from test_csv_ingestion import account
from test_dashboards import Analyses, card, drain, post, run_plan

from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def text(kind: str, value: str) -> dict[str, Any]:
    return {"id": str(uuid4()), "kind": kind, "text": value}


def analysis(plan: dict[str, Any], run: str | None, title: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "kind": "analysis",
        "title": title,
        "plan_revision_id": plan["id"],
        "execution_id": run,
    }


def pdf_text(content: bytes) -> str:
    """Texto de los flujos del PDF (ReportLab: Flate, opcionalmente sobre ASCII85)."""
    chunks = []
    # ReportLab escribe «~>endstream» sin salto de línea antes de endstream.
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.S):
        data = match.group(1).strip()
        for decode in (
            zlib.decompress,
            lambda d: zlib.decompress(base64.a85decode(d.removesuffix(b"~>"))),
        ):
            try:
                chunks.append(decode(data).decode("latin-1"))
                break
            except (zlib.error, ValueError):
                continue
    return "".join(chunks)


class Fixture:
    """v2 tipada, análisis ejecutados, un dashboard con un KPI y un informe con cinco bloques."""

    def __init__(self, s: Scenario) -> None:
        self.s = s
        self.a = Analyses(s)
        self.kpi = card(self.a.total, self.a.runs["total"], "kpi", "Ingresos totales")
        dashboard = post(
            s,
            f"/api/v1/projects/{s.project_id}/dashboards",
            {"draft": {"title": "Ventas", "cards": [self.kpi]}},
        ).json()["revision"]
        self.dashboard = dashboard
        self.blocks = [
            text("text", "Resumen de ventas de enero."),
            analysis(self.a.by_region, self.a.runs["by_region"], "Ingresos por región"),
            {
                "id": str(uuid4()),
                "kind": "dashboard_card",
                "title": "KPI del dashboard",
                "dashboard_revision_id": dashboard["id"],
                "card_id": self.kpi["id"],
            },
            text("conclusion", "Norte concentra la mitad de los ingresos."),
            text("limitations", "Sólo hay datos de enero; Sur tiene importes nulos."),
        ]
        self.draft = {"title": "Informe de ventas", "blocks": self.blocks}
        created = post(
            s,
            f"/api/v1/projects/{s.project_id}/reports",
            {"version_id": self.a.table["version_id"], "draft": self.draft},
        )
        assert created.status_code == 201, created.text
        self.revision = created.json()["revision"]
        self.family = self.revision["family_id"]


def test_report_revisions_provenance_conflict_and_idempotency(scenario: Scenario) -> None:
    s, c = scenario, scenario.columns
    f = Fixture(s)
    view = s.client.get(f"/api/v1/reports/{f.family}").json()
    by_block = {p["block_id"]: p for p in view["provenance"]}
    region, kpi = by_block[f.blocks[1]["id"]], by_block[f.blocks[2]["id"]]
    assert (region["status"], region["version_number"]) == ("ready", 2)
    assert region["dataset"] == "ventas.csv · limpieza"  # nombre de la versión derivada
    assert region["execution_id"] == f.a.runs["by_region"] and region["executed_at"]
    assert region["dimensions"] == [c["region"]] and region["view"] == "table"
    assert (kpi["execution_id"], kpi["view"], kpi["dashboard_revision_id"]) == (
        f.a.runs["total"],
        "kpi",
        f.dashboard["id"],
    )

    url = f"/api/v1/reports/{f.family}/revisions"
    key = str(uuid4())
    same = post(s, url, {"expected_revision": 1, "draft": f.draft}, key)
    assert same.json()["changed"] is False  # sin cambios no hay revisión
    edited = {**f.draft, "title": "Informe de ventas de enero"}
    key = str(uuid4())  # una solicitud sin cambios no registra su clave; una edición sí
    second = post(s, url, {"expected_revision": 1, "draft": edited}, key).json()
    assert second["revision"]["revision"] == 2
    stale = post(s, url, {"expected_revision": 1, "draft": f.draft})
    assert stale.status_code == 409 and stale.json()["code"] == "REPORT_CONFLICT"
    reuse = post(s, url, {"expected_revision": 2, "draft": f.draft}, key)
    assert reuse.status_code == 409 and reuse.json()["code"] == "IDEMPOTENCY_CONFLICT"
    history = s.client.get(url).json()
    assert [(h["revision"], h["cause"]) for h in history] == [(2, "edit"), (1, "create")]
    old = s.client.get(f"/api/v1/reports/{f.family}", params={"revision": f.revision["id"]})
    assert old.json()["head"]["content"]["title"] == "Informe de ventas"


def test_block_validation(scenario: Scenario) -> None:
    s = scenario
    f = Fixture(s)

    def invalid(blocks: list[dict[str, Any]]) -> Any:
        response = post(
            s,
            f"/api/v1/projects/{s.project_id}/reports",
            {"version_id": f.a.table["version_id"], "draft": {"title": "X", "blocks": blocks}},
        )
        return response

    foreign_run = invalid([analysis(f.a.total, f.a.runs["by_region"], "Mal")])
    assert foreign_run.status_code == 422 and "no corresponde" in foreign_run.json()["message"]
    missing_card = invalid(
        [
            {
                "id": str(uuid4()),
                "kind": "dashboard_card",
                "title": "T",
                "dashboard_revision_id": f.dashboard["id"],
                "card_id": str(uuid4()),
            }
        ]
    )
    assert missing_card.status_code == 422 and missing_card.json()["code"] == "CARD_NOT_FOUND"
    other_version = post(
        s,
        f"/api/v1/projects/{s.project_id}/reports",
        {"version_id": str(uuid4()), "draft": {"title": "X", "blocks": []}},
    )
    assert other_version.status_code == 404


def test_pdf_is_rendered_by_the_worker_with_provenance_even_with_a_failed_block(
    scenario: Scenario,
) -> None:
    s, c = scenario, scenario.columns
    f = Fixture(s)
    # Un bloque cuya ejecución falla (presupuesto de 1 fila) no impide el informe.
    failing = query_plan(
        s,
        f.a.table,
        f.a.metrics,
        f.a.semantic,
        version=2,
        dimensions=[c["region"]],
        max_result_rows=1,
    )
    failed_run = run_plan(s, failing)
    blocks = [*f.blocks, analysis(failing, failed_run, "Análisis fallido")]
    revision = post(
        s,
        f"/api/v1/reports/{f.family}/revisions",
        {"expected_revision": 1, "draft": {**f.draft, "blocks": blocks}},
    ).json()["revision"]
    view = s.client.get(f"/api/v1/reports/{f.family}").json()
    assert view["provenance"][-1]["status"] == "failed"

    key = str(uuid4())
    queued = post(s, f"/api/v1/report-revisions/{revision['id']}/pdf", None, key)
    assert queued.status_code == 202, queued.text
    run = queued.json()["execution_id"]
    again = post(s, f"/api/v1/report-revisions/{revision['id']}/pdf", None, key)
    assert again.json()["execution_id"] == run  # misma clave: misma ejecución
    early = s.client.get(f"/api/v1/report-pdfs/{run}")
    assert early.status_code == 409 and early.json()["code"] == "REPORT_PDF_NOT_READY"
    drain(s)
    renders = s.client.get(f"/api/v1/reports/{f.family}/pdfs").json()
    assert [(r["execution_id"], r["state"]) for r in renders] == [(run, "succeeded")]
    download = s.client.get(f"/api/v1/report-pdfs/{run}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    content = download.content
    assert content.startswith(b"%PDF-")
    sha = hashlib.sha256(content).hexdigest()
    assert download.headers["x-content-sha256"] == sha == renders[0]["sha256"]

    body = pdf_text(content)
    region = s.client.get(f"/api/v1/executions/{f.a.runs['by_region']}/analysis").json()
    for expected in [
        revision["id"],  # revisión exacta del informe (pie de página)
        f.a.runs["by_region"],  # ejecución del bloque
        f.a.runs["total"],  # ejecución de la tarjeta del dashboard
        f.a.by_region["id"],  # plan
        region["rows"][0]["evidence"]["m0"],  # evidence_id de una cifra
        f.a.table["version_id"],
        "ventas.csv",
        "201.00 EUR",
        failed_run,
        "UTC",
    ]:
        assert expected in body, expected
    assert "Ejecuci\\363n fallida" in body or "Ejecución fallida" in body


def test_refresh_blocks_on_another_version_and_follow_the_dashboard_head(
    scenario: Scenario,
) -> None:
    s = scenario
    f = Fixture(s)
    # El dashboard avanza a la revisión 2 (otro título de tarjeta).
    moved = post(
        s,
        f"/api/v1/dashboards/{f.dashboard['family_id']}/revisions",
        {
            "expected_revision": 1,
            "draft": {"title": "Ventas", "cards": [{**f.kpi, "title": "KPI"}]},
        },
    ).json()["revision"]
    url = f"/api/v1/reports/{f.family}/refresh"
    key = str(uuid4())
    refreshed = post(s, url, {"expected_revision": 1, "version_id": s.version["id"]}, key)
    assert refreshed.status_code == 200, refreshed.text
    revision = refreshed.json()["revision"]
    assert (revision["revision"], revision["cause"]) == (2, "refresh")
    assert revision["content"]["version_id"] == s.version["id"]
    blocks = revision["content"]["blocks"]
    assert blocks[1]["plan_revision_id"] != f.a.by_region["id"]  # plan nuevo en v1
    assert blocks[1]["execution_id"] is None  # v1 sin semántica: no se ejecuta
    assert blocks[2]["dashboard_revision_id"] == moved["id"]  # tarjeta de la revisión vigente
    again = post(s, url, {"expected_revision": 1, "version_id": s.version["id"]}, key)
    assert again.json()["revision"]["id"] == revision["id"]
    view = s.client.get(f"/api/v1/reports/{f.family}").json()
    assert view["provenance"][0]["status"] == "semantic_requirement_missing"
    assert view["provenance"][0]["version_number"] == 1
    # El plan original no cambia.
    assert s.client.get(f"/api/v1/plans/{f.a.by_region['id']}").json() == f.a.by_region | {
        "head_revision": f.a.by_region["head_revision"]
    }


def test_privacy_and_csrf(scenario: Scenario) -> None:
    s = scenario
    f = Fixture(s)
    run = post(s, f"/api/v1/report-revisions/{f.revision['id']}/pdf", None).json()["execution_id"]
    drain(s)
    no_csrf = s.client.post(
        f"/api/v1/reports/{f.family}/revisions",
        json={"expected_revision": 1, "draft": f.draft},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "CSRF_INVALID"
    s.headers = account(s.client)
    assert s.client.get(f"/api/v1/reports/{f.family}").status_code == 404
    assert s.client.get(f"/api/v1/projects/{s.project_id}/reports").status_code == 404
    assert s.client.get(f"/api/v1/report-pdfs/{run}").status_code == 404
    assert s.client.get(f"/api/v1/report-revisions/{f.revision['id']}").status_code == 404
    hijack = post(s, f"/api/v1/report-revisions/{f.revision['id']}/pdf", None)
    assert hijack.status_code == 404
