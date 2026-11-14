"""Fase 17: informe automático (`delivery.report@1`) y progreso por etapas.

El informe no calcula: cada cifra que muestra es la cifra canónica publicada (sólo cambia su
formato) y cada evidencia citada existe en el análisis o en la investigación.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase16_investigation import (
    INVESTIGATION,
    Engine,
    Explainer,
    Proposer,
    clock,
    reference_analysis,
)

from dataflow.bootstrap.services import make_runner
from dataflow.modules.analytics.contracts import AutomaticAnalysis
from dataflow.modules.copilot.contracts import AuditContent, Segment
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.contracts import ReportSource, RunSummary
from dataflow.modules.delivery.domain import es
from dataflow.modules.delivery.public import build_report, progress, render_pdf
from dataflow.modules.investigation.contracts import (
    Investigation,
    InvestigationLimits,
    ProposalContext,
    RawProposal,
)
from dataflow.modules.investigation.public import Investigator
from dataflow.platform.config import get_settings

GENERATED = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def investigation(analysis: AutomaticAnalysis) -> Investigation:
    def reply(context: ProposalContext) -> list[RawProposal]:
        if context.iteration > 2:
            return []
        return [
            RawProposal(kind="group_evolution", dimension="Region", group="Norte", motive="m"),
            RawProposal(kind="group_evolution", dimension="Customer", group="C003", motive="m"),
        ]

    result = Investigator(
        Engine(), Proposer(reply), Explainer(), InvestigationLimits(), clock()
    ).run(analysis, INVESTIGATION)
    first = result.results[0].insight
    assert first is not None
    cited = first.figures[0]
    # Explicación ya verificada (como la que produce copilot): cita una evidencia real.
    return result.model_copy(
        update={
            "explanation": AuditContent(
                resumen_ejecutivo=[
                    Segment(kind="text", text="El mayor desvío fue "),
                    Segment(kind="evidence", text=es(cited.value), evidence_id=cited.evidence_id),
                    Segment(kind="text", text=" y "),
                    Segment(kind="unverified", text="12"),
                ],
                alertas_criticas=[],
                recomendaciones=[[Segment(kind="text", text="Revisar el mes atípico.")]],
                unverified_numbers=1,
            )
        }
    )


def source(analysis: AutomaticAnalysis, result: Investigation) -> ReportSource:
    return ReportSource(
        project_id=uuid4(),
        version_id=result.scope.version_id,
        version_number=1,
        file_name="ventas_mensuales.csv",
        analysis_execution_id=analysis.scope.execution_id,
        analysis_sha256=result.scope.analysis_sha256,
        investigation_execution_id=result.scope.execution_id,
        investigation_sha256="c" * 64,
    )


def test_report_copies_published_figures_and_cites_only_known_evidence() -> None:
    analysis = reference_analysis()
    result = investigation(analysis)
    document = build_report(source(analysis, result), analysis, result, None, GENERATED)
    ids = [section.id for section in document.sections]
    assert ids == [
        "summary",
        "explanation",
        "findings",
        "investigation",
        "omitted",
        "limitations",
        "evidence",
    ]
    known = {item.evidence_id: item for item in analysis.evidence}
    for item in result.results:
        known.update({e.evidence_id: e for e in item.evidence})
    assert document.evidence_ids and set(document.evidence_ids) <= set(known)
    # Cada cifra de los hallazgos aparece con su valor canónico formateado y su evidencia.
    findings = next(s for s in document.sections if s.id == "findings")
    for insight, block in zip(analysis.insights, findings.blocks, strict=True):
        assert block.title == insight.title
        rows = block.table.rows if block.table else []
        assert rows == [[f.label, es(f.value, f.unit), f.evidence_id[:12]] for f in insight.figures]
    annex = next(s for s in document.sections if s.id == "evidence").blocks[0].table
    assert annex is not None and [row[0] for row in annex.rows] == document.evidence_ids
    for row in annex.rows:
        assert row[2] == es(known[row[0]].value, known[row[0]].unit)
    explanation = next(s for s in document.sections if s.id == "explanation")
    summary = explanation.blocks[0].paragraphs[0]
    assert "[cifra retirada]" in summary and "12" not in summary
    investigated = next(s for s in document.sections if s.id == "investigation")
    assert any(block.badge == "Propuesto por la IA" for block in investigated.blocks)
    assert any(block.title == "Propuestas rechazadas" for block in investigated.blocks)


def test_report_without_ai_explains_the_absence() -> None:
    analysis = reference_analysis()
    result = Investigator(Engine(), None, None, InvestigationLimits(), clock(), "disabled").run(
        analysis, INVESTIGATION
    )
    document = build_report(source(analysis, result), analysis, result, None, GENERATED)
    explanation = next(s for s in document.sections if s.id == "explanation")
    assert "Sin explicación de la IA" in explanation.blocks[0].paragraphs[0]


def test_pdf_is_reproducible_for_the_same_document() -> None:
    analysis = reference_analysis()
    result = investigation(analysis)
    document = build_report(source(analysis, result), analysis, result, None, GENERATED)
    first, second = render_pdf(document), render_pdf(document)
    assert first.startswith(b"%PDF") and first == second


@pytest.mark.parametrize("value", ["1234567.5", "-0.25", "12", "abc"])
def test_spanish_format_never_rounds(value: str) -> None:
    text = es(value)
    assert text.replace(".", "").replace(",", ".") == value or text == value


def run(kind: str, state: str) -> RunSummary:
    return RunSummary(id=uuid4(), kind=kind, state=state)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("runs", "states", "complete"),
    [
        ([run("csv_import", "running")], ["running"] + ["pending"] * 5, False),
        (
            [
                run("investigation", "queued"),
                run("comprehension", "running"),
                run("csv_import", "succeeded"),
            ],
            ["done", "running", "pending", "pending", "queued", "pending"],
            False,
        ),
        (
            [
                run("automatic_report", "succeeded"),
                run("dashboard", "succeeded"),
                run("exploration", "succeeded"),
                run("investigation", "succeeded"),
                run("comprehension", "succeeded"),
                run("csv_import", "succeeded"),
            ],
            ["done"] * 6,
            True,
        ),
        # Versión anterior a la Fase 19: sin comprensión ni exploración, el resto sigue igual.
        (
            [
                run("automatic_report", "succeeded"),
                run("investigation", "succeeded"),
                run("csv_import", "succeeded"),
            ],
            ["done", "skipped", "skipped", "skipped", "done", "done"],
            True,
        ),
        (
            [run("investigation", "failed"), run("csv_import", "succeeded")],
            ["done", "skipped", "skipped", "skipped", "failed", "skipped"],
            True,
        ),
        # Fase 27: sin seguimiento de hallazgos (retirado), la etapa no aparece.
        (
            [
                run("automatic_report", "succeeded"),
                run("dashboard", "succeeded"),
                run("exploration", "succeeded"),
                run("comprehension", "succeeded"),
                run("csv_import", "succeeded"),
            ],
            ["done"] * 5,
            True,
        ),
        ([run("csv_import", "succeeded")], ["done"] + ["skipped"] * 5, True),
        ([run("csv_import", "failed")], ["failed"] + ["skipped"] * 5, True),
    ],
)
def test_progress_by_stage(runs: list[RunSummary], states: list[str], complete: bool) -> None:
    result = progress(UUID(int=1), runs)
    assert [stage.state for stage in result.stages] == states
    expected = ["analysis", "comprehension", "exploration", "dashboard", "investigation", "report"]
    if len(states) == 5:  # Fase 27: sin seguimiento de hallazgos
        expected.remove("investigation")
    assert [stage.id for stage in result.stages] == expected
    assert result.complete is complete


# --- De extremo a extremo -------------------------------------------------------------------


def test_upload_ends_with_a_downloadable_report(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}"
    stages = client.get(f"{base}/progress").json()["stages"]
    assert [s["state"] for s in stages] == ["queued"] + ["pending"] * 5
    runner = make_runner(db, objects)
    assert runner.run_once()
    # Fase 27: mientras la cadena sigue, el informe está en cola (sin trabajo todavía).
    waiting = client.get(f"{base}/report").json()
    assert waiting["state"] == "queued" and waiting["execution_id"] is None
    assert runner.run_once()  # inspección del dataset (Fase 22)
    assert runner.run_once()  # comprensión del negocio (Fase 19)
    assert runner.run_once()  # investigación (Fase 25)
    # Fase 27: el informe parte del dashboard (sin seguimiento de la Fase 16).
    assert client.get(f"{base}/report").json()["execution_id"] is None
    assert runner.run_once()  # diseño del dashboard (Fase 21)
    assert client.get(f"{base}/report").json()["state"] == "queued"
    assert client.get(f"{base}/report.pdf").json()["code"] == "REPORT_NOT_READY"
    assert runner.run_once()  # informe
    assert not runner.run_once()
    progress_view = client.get(f"{base}/progress").json()
    assert progress_view["complete"] is True
    assert [s["state"] for s in progress_view["stages"]] == ["done"] * 5
    view = client.get(f"{base}/report").json()
    assert view["state"] == "ready" and view["file_name"] == "informe-ventas_mensuales-v1.pdf"
    assert view["evidence_count"] > 0 and view["number"] == 1
    assert view["document"]["rules_version"] == "automatic-report-v2"
    pdf = client.get(f"{base}/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    # El PDF se dibuja del documento: es el mismo cada vez.
    assert client.get(f"{base}/report.pdf").content == pdf.content
    assert "informe-ventas_mensuales-v1.pdf" in pdf.headers["content-disposition"]
    account(client)
    assert client.get(f"{base}/report").status_code == 404
    assert client.get(f"{base}/progress").status_code == 404


def test_reports_wait_behind_newer_uploads(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    first = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    runner = make_runner(db, objects)
    # Carga, inspección (Fase 22), comprensión, investigación y dashboard (Fase 27: el informe
    # se encola al publicarse el dashboard).
    for _ in range(5):
        assert runner.run_once()
    second = upload(client, headers, pid, reference_csv() + b"\n", name="otra.csv").json()
    assert runner.run_once()
    assert client.get(f"/api/v1/executions/{second['execution_id']}").json()["state"] == (
        "succeeded"
    )
    assert client.get(f"/api/v1/versions/{first['id']}/report").json()["state"] == "queued"
