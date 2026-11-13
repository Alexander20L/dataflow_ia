"""Fase 27 (ADR-045): pestaña Informe con `automatic-report-v2`.

Criterios de la especificación (5.9): informe honesto sin hallazgos relevantes, sólo los
aprobados como principales, cifras que coinciden con sus evidencias, metodología con las
operaciones y exclusiones, limitaciones, recomendaciones sin causalidad, PDF legible, una
selección nueva genera otra versión y el historial conserva las anteriores.
"""

import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase16_investigation import reference_analysis
from test_phase21_dashboard import exploration

from dataflow.bootstrap.services import make_runner
from dataflow.modules.copilot.contracts import NarrativaIA
from dataflow.modules.copilot.investigation import Figure
from dataflow.modules.copilot.report import verify_narrative
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.contracts import ReportSource
from dataflow.modules.delivery.public import build_report_v2, render_pdf, review_items
from dataflow.modules.delivery.report import CAUTION
from dataflow.platform.config import get_settings


def source() -> ReportSource:
    return ReportSource(
        project_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        file_name="ventas.csv",
        analysis_execution_id=uuid4(),
        analysis_sha256="a" * 64,
    )


def report(verdicts: dict[str, str], explored: bool = True):  # type: ignore[no-untyped-def]
    analysis = reference_analysis()
    found = exploration() if explored else None
    return (
        build_report_v2(
            source(),
            datetime(2026, 11, 13, tzinfo=UTC),
            analysis,
            None,
            None,
            None,
            found,
            None,
            verdicts,
        ),
        analysis,
        found,
    )


def section(document, identifier: str):  # type: ignore[no-untyped-def]
    return next(s for s in document.sections if s.id == identifier)


# --- Revisión humana ---------------------------------------------------------------------------


def test_only_approved_findings_are_principal_and_rejected_never() -> None:
    _, analysis, found = report({})
    assert found is not None
    items = review_items(analysis, found, {})
    # Sin revisar: los relevantes de la investigación, marcados «Sin revisar».
    principal = [i for i in items if i.principal]
    assert principal and all(i.origin == "exploration" for i in principal)
    assert all(i.status == "pending" for i in items)
    first, second = principal[0].item, principal[1].item
    approved = review_items(analysis, found, {first: "keep"})
    assert [i.item for i in approved if i.principal] == [first]
    rejected = review_items(analysis, found, {second: "drop"})
    assert second not in {i.item for i in rejected if i.principal}
    document, _, _ = report({first: "keep", second: "drop"})
    findings = section(document, "findings")
    titles = [b.title for b in findings.blocks]
    assert titles[0] == next(i.title for i in approved if i.item == first)
    assert "Rechazados por ti" in titles
    assert findings.blocks[0].badge == "Aprobado por ti"


def test_without_relevant_findings_the_report_is_honest() -> None:
    document, _, _ = report({}, explored=False)
    findings = section(document, "findings")
    # Sin investigación, sólo los hallazgos importantes del análisis, «Sin revisar».
    principal = [i for i in document.review if i.principal]
    assert all(i.origin == "insight" for i in principal)
    # Rechazados todos, no queda nada principal y el informe lo dice sin inventar.
    everything = {i.item: "drop" for i in document.review}
    honest, _, _ = report(everything, explored=False)
    findings = section(honest, "findings")
    assert "No hay hallazgos principales" in findings.blocks[0].paragraphs[0]
    conclusions = section(honest, "conclusions")
    assert "no muestran hallazgos relevantes" in conclusions.blocks[0].paragraphs[0]
    summary = section(honest, "summary")
    discoveries = next(b for b in summary.blocks if b.title == "Principales descubrimientos")
    assert "No se encontraron hallazgos relevantes" in discoveries.paragraphs[0]


# --- Cifras, metodología, recomendaciones y PDF ------------------------------------------------


def test_figures_match_evidence_and_the_methodology_is_described() -> None:
    document, _, found = report({})
    assert found is not None
    values = {
        f.evidence_id[:12]: f.value for r in found.results for row in r.rows for f in row.figures
    }
    annex = section(document, "evidence")
    for short, _label, value in annex.blocks[0].table.rows:  # type: ignore[union-attr]
        assert short in values
        assert value.replace(".", "").replace(",", ".") == (values[short] or "sin dato") or (
            value == "sin dato"
        )
    assert set(document.evidence_ids) <= {
        f.evidence_id for r in found.results for row in r.rows for f in row.figures
    }
    recommendations = section(document, "conclusions").blocks[1].paragraphs
    assert recommendations[-1] == CAUTION
    for text in recommendations[:-1]:
        assert not re.search(r"\b(causa|provoca|se debe a|debido a|porque)\b", text, re.I)
    pdf = render_pdf(document)
    assert pdf.startswith(b"%PDF") and render_pdf(document) == pdf


def test_ai_narrative_cannot_write_numbers_or_causes() -> None:
    figure = Figure(
        evidence_id="e" * 64, label="Ventas", value="1200", unit="number", execution_id=uuid4()
    )
    narrative, invalid = verify_narrative(
        NarrativaIA(
            resumen=f"Las ventas suman {{{{evidence:{'e' * 64}}}}} en 12 meses. "
            "Bajaron porque subió el precio.",
            conclusiones=["La caída se debe a la competencia.", "Las ventas se concentran."],
            recomendaciones=["Revisar los grupos que más aportan."],
        ),
        [figure],
    )
    assert narrative is not None and invalid == []
    assert narrative.causal_removed == 2 and narrative.unverified_numbers == 1
    assert [s.kind for s in narrative.summary].count("evidence") == 1
    assert len(narrative.conclusions) == 1
    # Una evidencia ajena anula toda la narrativa (el informe la escribe por reglas).
    foreign, wrong = verify_narrative(
        NarrativaIA(resumen="{{evidence:otra}}", conclusiones=[], recomendaciones=[]), [figure]
    )
    assert foreign is None and wrong


# --- Recorrido por la API ------------------------------------------------------------------------


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def test_review_generates_new_versions_and_the_history_keeps_the_old_ones(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}"
    run_all(db, objects)
    view = client.get(f"{base}/report").json()
    assert view["state"] == "ready" and view["number"] == 1
    document = view["document"]
    assert [s["id"] for s in document["sections"]][:6] == [
        "summary",
        "dataset",
        "methodology",
        "findings",
        "investigations",
        "conclusions",
    ]
    # La IA falsa redactó la narrativa: su cifra libre y su frase causal se retiraron.
    assert document["narrative_by"] == "ai"
    conclusions = next(s for s in document["sections"] if s["id"] == "conclusions")
    written = " ".join(p for b in conclusions["blocks"] for p in b["paragraphs"])
    assert "se debe a" not in written
    summary = next(s for s in document["sections"] if s["id"] == "summary")
    assert "[cifra retirada]" in " ".join(p for b in summary["blocks"] for p in b["paragraphs"])
    dataset = next(s for s in document["sections"] if s["id"] == "dataset")
    rows = {r[0]: r[1] for r in dataset["blocks"][0]["table"]["rows"]}
    assert rows["Registros"] == "276" and rows["Formato de origen"] == "CSV"
    methodology = next(s for s in document["sections"] if s["id"] == "methodology")
    assert any(b["title"] == "Métodos aplicados" for b in methodology["blocks"])

    # Revisión: sin cambios no se genera otra versión.
    review = client.get(f"{base}/report/review").json()
    assert review["changed"] is False
    same = client.post(f"{base}/report/versions", headers=headers)
    assert same.status_code == 409 and same.json()["code"] == "REPORT_UP_TO_DATE"
    candidate = next(i for i in review["items"] if not i["principal"])
    approved = client.post(
        f"{base}/report/review",
        json={"item": candidate["item"], "status": "approved"},
        headers=headers,
    ).json()
    assert approved["changed"] is True
    assert [i["item"] for i in approved["items"] if i["principal"]] == [candidate["item"]]
    missing = client.post(
        f"{base}/report/review", json={"item": "x", "status": "approved"}, headers=headers
    )
    assert missing.json()["code"] == "FINDING_NOT_FOUND"
    generated = client.post(f"{base}/report/versions", headers=headers)
    assert generated.status_code == 200, generated.json()
    run_all(db, objects)
    latest = client.get(f"{base}/report").json()
    assert latest["number"] == 2
    principal = [i for i in latest["document"]["review"] if i["principal"]]
    assert [i["item"] for i in principal] == [candidate["item"]]

    # Historial: la versión anterior se conserva con su documento y su PDF.
    history = client.get(f"{base}/report/history").json()["items"]
    assert [h["number"] for h in history] == [2, 1]
    assert history[0]["trigger"] == "selection" and history[1]["trigger"] == "load"
    first = client.get(f"{base}/report/versions/{history[1]['execution_id']}").json()
    assert first["document"]["review"] == document["review"]
    old_pdf = client.get(f"{base}/report.pdf", params={"execution_id": history[1]["execution_id"]})
    assert old_pdf.status_code == 200 and old_pdf.content.startswith(b"%PDF")
    assert "-v1.pdf" in old_pdf.headers["content-disposition"]
    account(client)
    assert client.get(f"{base}/report/history").status_code == 404
