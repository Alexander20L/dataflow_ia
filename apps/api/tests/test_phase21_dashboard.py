"""Fase 21: dashboard adaptado a los datos. La IA diseña secciones, orden y tipo de gráfico sin
cifras; Python valida el diseño contra la forma de cada elemento; sin IA, lo hacen las reglas. Las
marcas «sí va / no va» del usuario reordenan el dashboard y encolan una versión nueva del informe.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase16_investigation import reference_analysis
from test_phase17_delivery import investigation, source
from test_phase20_exploration import table

from dataflow.bootstrap.services import make_runner
from dataflow.modules.copilot.contracts import DisenoIA, ElementoIA, SeccionIA
from dataflow.modules.copilot.dashboard import design_context
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.contracts import (
    Dashboard,
    DashboardScope,
    DashboardSection,
    DashboardWidget,
)
from dataflow.modules.delivery.dashboard import (
    WIDGETS,
    arrange,
    catalog,
    insight_key,
    result_key,
    rules_design,
    safe_text,
    validate_design,
)
from dataflow.modules.delivery.public import build_report, render_pdf
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.exploration.contracts import (
    Exploration,
    ExplorationLimits,
    ExplorationScope,
    ExploreQuery,
)
from dataflow.modules.exploration.engine import compute
from dataflow.platform.config import get_settings


def exploration() -> Exploration:
    content = table()
    queries = [
        ExploreQuery(kind="aggregate", measure="Revenue", dimensions=["Region"], aggregation="sum"),
        ExploreQuery(kind="crosstab", dimensions=["Region", "Product"]),
        ExploreQuery(kind="ratio", measure="Revenue", measure_b="Units"),
    ]
    results = []
    for query in queries:
        computed = compute(content, query, "x")
        assert not isinstance(computed, str)
        results.append(
            computed.model_copy(update={"relevant": True, "judged_by": "rules", "reason": "r"})
        )
    return Exploration(
        scope=ExplorationScope(
            execution_id=uuid4(),
            version_id=uuid4(),
            comprehension_sha256="c" * 64,
            table_sha256="t" * 64,
        ),
        limits=ExplorationLimits(),
        ai_state="unavailable",
        proposals=[],
        results=results,
        limitations=[],
    )


def dashboard(sections: list[DashboardSection]) -> Dashboard:
    return Dashboard(
        scope=DashboardScope(
            execution_id=uuid4(),
            version_id=uuid4(),
            analysis_sha256="a" * 64,
            exploration_sha256="e" * 64,
        ),
        designed_by="rules",
        ai_state="unavailable",
        title="Dashboard",
        sections=sections,
    )


def test_chart_types_follow_the_shape_of_each_element() -> None:
    analysis = reference_analysis()
    explored = exploration()
    items = {item.id: item for item in catalog(analysis.insights, explored)}
    summed, crossed, ratio = (items[result_key(r)] for r in explored.results)
    # Suma por una dimensión con dos grupos: barras y circular; nunca líneas ni mapa de calor.
    assert set(summed.widgets) == {"bar", "pie", "table"}
    # Dos dimensiones: mapa de calor; cociente total: indicador con su evidencia.
    assert set(crossed.widgets) == {"heatmap", "table"}
    assert ratio.widgets == ["kpi", "table"] and len(ratio.figures) == 3
    lines = [i for i in analysis.insights if i.chart is not None and i.chart.type == "line"]
    assert lines and all("line" in items[insight_key(i)].widgets for i in lines)
    others = [i for i in analysis.insights if i.chart is None or i.chart.type != "line"]
    assert all("line" not in items[insight_key(i)].widgets for i in others)
    # Ninguna cifra en lo que ve la IA: sólo forma, clase e ids de evidencia (Fase 26: el
    # origen de cada elemento, con sus registros, queda fuera del contexto de la IA).
    context = design_context(None, [], [i.model_dump(mode="json") for i in items.values()], WIDGETS)
    for element in context["elementos"]:
        assert set(element) == {
            "id",
            "origen",
            "titulo",
            "tipo",
            "graficos_compatibles",
            "cifras",
            "clase",
        }


def test_ai_design_is_validated_and_completed() -> None:
    analysis = reference_analysis()
    explored = exploration()
    items = catalog(analysis.insights, explored)
    summed, crossed, ratio = (result_key(r) for r in explored.results)
    design = DisenoIA(
        titulo="Ventas por zona",
        secciones=[
            SeccionIA(
                titulo="Lo esencial en 2025",  # cifra propia: se descarta el título
                elementos=[
                    ElementoIA(elemento=ratio, grafico="kpi"),
                    ElementoIA(elemento=crossed, grafico="heatmap", titulo="Mapa"),
                    ElementoIA(elemento=crossed, grafico="heatmap"),
                    ElementoIA(elemento=summed, grafico="line"),
                    ElementoIA(elemento="insight:inventado", grafico="bar"),
                    ElementoIA(elemento=summed, grafico="sankey"),
                    ElementoIA(elemento=ratio, grafico="kpi", cifra="0" * 64),
                ],
            )
        ],
    )
    title, sections, decisions = validate_design(design, items)
    assert title == "Ventas por zona"
    assert sections[0].title == "Hallazgos"
    assert [(w.item, w.type) for w in sections[0].widgets] == [
        (ratio, "kpi"),
        (crossed, "heatmap"),
    ]
    assert sections[0].widgets[0].evidence_id == explored.results[2].rows[0].figures[0].evidence_id
    reasons = [d.reason for d in decisions if d.status == "rejected"]
    assert reasons == [
        "Repetido.",
        "Un gráfico de líneas necesita una serie en el tiempo.",
        "No es un elemento publicado.",
        "No es un gráfico del catálogo.",
        "Un indicador necesita una cifra publicada de ese elemento.",
    ]
    # La IA no puede ocultar hallazgos: lo que no colocó va al final.
    assert sections[-1].title == "Otros hallazgos"
    shown = {w.item for s in sections for w in s.widgets if w.type != "kpi"}
    assert {i.id for i in items} <= shown | {ratio}


def test_text_from_the_ai_cannot_carry_its_own_figures() -> None:
    vocabulary = ["Revenue por Region 2024", "Top 5 clientes"]
    assert safe_text("Evolución 2024", vocabulary) == "Evolución 2024"
    assert safe_text("Crece un 12,5 %", vocabulary) is None
    assert safe_text("  Lo   esencial ", vocabulary) == "Lo esencial"
    assert safe_text("", vocabulary) is None


def test_marks_pin_and_hide_without_changing_the_design() -> None:
    a, b, c = "insight:a", "insight:b", "exploration:c"
    design = dashboard(
        [
            DashboardSection(
                title="Uno",
                widgets=[
                    DashboardWidget(type="kpi", item=a, title="A", evidence_id="e"),
                    DashboardWidget(type="bar", item=b, title="B"),
                ],
            ),
            DashboardSection(
                title="Dos",
                widgets=[
                    DashboardWidget(type="table", item=a, title="A"),
                    DashboardWidget(type="heatmap", item=c, title="C"),
                ],
            ),
        ]
    )
    arranged = arrange(design, {c: "keep", b: "drop", "insight:otro": "keep"})
    assert arranged.pinned == [c] and arranged.hidden == [b]
    assert [s.title for s in arranged.sections] == ["Fijados por ti", "Uno", "Dos"]
    assert [w.item for w in arranged.sections[0].widgets] == [c]
    assert [w.item for w in arranged.sections[1].widgets] == [a]
    assert arrange(design, {}).sections == design.sections


def test_report_follows_the_dashboard_and_the_marks() -> None:
    analysis = reference_analysis()
    explored = exploration()
    items = catalog(analysis.insights, explored)
    design = dashboard(rules_design(analysis.insights, items))
    result = investigation(analysis)
    last, first = analysis.insights[-1], analysis.insights[0]
    document = build_report(
        source(analysis, result),
        analysis,
        result,
        None,
        datetime(2026, 11, 10, tzinfo=UTC),
        None,
        None,
        explored,
        design,
        {insight_key(last): "keep", insight_key(first): "drop"},
    )
    findings = next(s for s in document.sections if s.id == "findings")
    assert findings.blocks[0].title == last.title and findings.blocks[0].badge == "Fijado por ti"
    assert first.title not in [b.title for b in findings.blocks]
    summary = next(s for s in document.sections if s.id == "summary")
    assert summary.blocks[0].title == last.title
    dropped = next(s for s in document.sections if s.id == "dropped")
    assert dropped.blocks[0].paragraphs == [first.title]
    # Las evidencias del descartado siguen en el anexo: no se borra nada.
    assert all(f.evidence_id in document.evidence_ids for f in first.figures)
    assert render_pdf(document).startswith(b"%PDF")


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def reports(db: Session, version: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ExecutionRecord)
            .where(
                ExecutionRecord.version_id == version, ExecutionRecord.kind == "automatic_report"
            )
        )
        or 0
    )


def test_upload_gets_a_dashboard_designed_by_the_fake_ai_and_marks_update_the_report(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}"
    assert make_runner(db, objects).run_once()  # carga
    # Sin trabajo todavía: la comprensión y la exploración van antes; no es un 404.
    pending = client.get(f"{base}/dashboard").json()
    assert pending["state"] == "queued" and pending["execution_id"] is None
    run_all(db, objects)
    view = client.get(f"{base}/dashboard").json()
    assert view["state"] == "ready", view
    designed = view["dashboard"]
    assert designed["designed_by"] == "ai" and designed["ai_state"] == "ready"
    assert designed["title"] == "Panorama del negocio"
    assert [s["title"] for s in designed["sections"]][:2] == ["Lo esencial", "Detalle"]
    reasons = {d["reason"] for d in designed["decisions"] if d["status"] == "rejected"}
    assert "No es un elemento publicado." in reasons
    titles = [w["title"] for s in designed["sections"] for w in s["widgets"]]
    assert "Top 99 de la exploración" not in titles  # título con cifra propia, retirado
    # Todo lo que cita está en la vista, con sus cifras publicadas.
    cited = {w["item"] for s in designed["sections"] for w in s["widgets"]}
    given = {f"insight:{i['id']}" for i in view["insights"]} | {
        f"exploration:{r['key']}" for r in view["results"]
    }
    # Fase 26: también lo que calcula el propio dashboard (indicadores y distribuciones).
    given |= {f"computed:{r['key']}" for r in designed["computed"]}
    # Desde la Fase 26 la vista trae todos los elementos (la versión personalizada puede
    # mostrar cualquiera): lo citado es un subconjunto.
    assert cited and cited <= given
    # El informe se generó una sola vez, ya con el dashboard.
    assert reports(db, version["id"]) == 1
    stages = client.get(f"{base}/progress").json()["stages"]
    assert [s["id"] for s in stages][3] == "dashboard" and stages[3]["state"] == "done"

    # Marcas «sí va / no va».
    items = [w["item"] for w in view["arrangement"]["sections"][-1]["widgets"]]
    keep, drop = items[-1], items[0]
    response = client.post(
        f"{base}/dashboard/feedback", json={"item": keep, "verdict": "keep"}, headers=headers
    )
    assert response.status_code == 200, response.json()
    client.post(
        f"{base}/dashboard/feedback", json={"item": drop, "verdict": "drop"}, headers=headers
    )
    arranged = client.get(f"{base}/dashboard").json()["arrangement"]
    assert arranged["sections"][0]["title"] == "Fijados por ti"
    assert arranged["pinned"] == [keep] and arranged["hidden"] == [drop]
    # Una sola versión nueva en cola; mientras, se sirve el informe anterior.
    assert reports(db, version["id"]) == 2
    report = client.get(f"{base}/report").json()
    assert report["state"] == "ready" and report["updating"] is True
    run_all(db, objects)
    report = client.get(f"{base}/report").json()
    assert report["state"] == "ready" and report["updating"] is False
    assert client.get(f"{base}/report.pdf").content.startswith(b"%PDF")
    # Retirar la marca vuelve al diseño original.
    client.post(
        f"{base}/dashboard/feedback", json={"item": keep, "verdict": "none"}, headers=headers
    )
    client.post(
        f"{base}/dashboard/feedback", json={"item": drop, "verdict": "none"}, headers=headers
    )
    again = client.get(f"{base}/dashboard").json()
    assert again["arrangement"]["sections"] == designed["sections"]
    missing = client.post(
        f"{base}/dashboard/feedback", json={"item": "x", "verdict": "keep"}, headers=headers
    )
    assert missing.json()["code"] == "FINDING_NOT_FOUND"
    account(client)
    assert client.get(f"{base}/dashboard").status_code == 404


def test_without_ai_the_rules_design_the_dashboard(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    view = client.get(f"/api/v1/versions/{version['id']}/dashboard").json()
    designed = view["dashboard"]
    assert designed["designed_by"] == "rules" and designed["ai_state"] == "unavailable"
    assert designed["sections"][0]["title"] == "Indicadores clave"
    assert {w["type"] for w in designed["sections"][0]["widgets"]} == {"kpi"}
    assert reports(db, version["id"]) == 1
