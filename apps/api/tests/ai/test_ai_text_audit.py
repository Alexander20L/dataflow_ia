"""Fase 11F · auditoría textual IA de una revisión de dashboard publicada, con el proveedor falso:
cifras sólo por evidencia, respuesta guardada por clave de contenido (sin otra llamada), fallos
que no tocan el dashboard, registro de llamadas, límites y accesos."""

from typing import Any
from uuid import uuid4

import pytest
from ai_support import config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario
from test_csv_ingestion import account
from test_dashboards import Analyses, card, post

from dataflow.bootstrap.ai import simulated
from dataflow.bootstrap.app import app
from dataflow.bootstrap.dependencies import ai_setup
from dataflow.integrations.ai import AIProvider, AIProviderError, FakeProvider
from dataflow.modules.copilot import prompts
from dataflow.modules.copilot.contracts import AuditoriaTextual, ResultCell
from dataflow.modules.copilot.domain import verify_audit
from dataflow.modules.copilot.infrastructure import AICallRecord, TextAuditRecord
from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


class Audits:
    """Dashboard publicado con tres tarjetas (KPI, barras y líneas) y el proveedor indicado."""

    def __init__(self, s: Scenario, cards: list[dict[str, Any]] | None = None) -> None:
        self.s = s
        self.analyses = Analyses(s)
        response = post(
            s,
            f"/api/v1/projects/{s.project_id}/dashboards",
            {"draft": {"title": "Ventas", "cards": cards or self.analyses.cards()}},
        )
        assert response.status_code == 201, response.text
        self.revision = response.json()["revision"]
        self.provider: AIProvider | None = FakeProvider(responder=simulated)
        self.config = config()
        app.dependency_overrides[ai_setup] = lambda: (self.provider, self.config)

    @property
    def url(self) -> str:
        return f"/api/v1/dashboard-revisions/{self.revision['id']}/text-audits"

    def request(self, status: int = 200, key: str | None = None) -> Any:
        response = self.s.client.post(
            self.url, headers={**self.s.headers, "Idempotency-Key": key or str(uuid4())}
        )
        assert response.status_code == status, response.text
        return response.json()

    def script(self, *outputs: Any) -> FakeProvider:
        provider = FakeProvider(script=list(outputs))
        self.provider = provider
        return provider

    def calls(self) -> list[AICallRecord]:
        return list(
            self.s.db.scalars(
                select(AICallRecord)
                .where(AICallRecord.task == "text_audit")
                .order_by(AICallRecord.created_at)
            )
        )

    def evidence(self) -> list[tuple[str, str]]:
        """(ejecución, evidence_id) de las cifras de las tarjetas, como las lee la interfaz."""
        found = []
        for run in self.analyses.runs.values():
            result = self.s.client.get(f"/api/v1/executions/{run}/analysis").json()
            for row in result["rows"]:
                found += [(run, evidence) for evidence in row["evidence"].values()]
        return found


def text(segments: list[dict[str, Any]]) -> str:
    return "".join(segment["text"] for segment in segments)


def audit_output(**overrides: Any) -> dict[str, Any]:
    return {
        "resumen_ejecutivo": "Resumen.",
        "alertas_criticas": [],
        "recomendaciones": ["Revisa los datos.", "Comparte el dashboard."],
        **overrides,
    }


def test_audit_cites_figures_by_evidence_and_is_saved_and_reused(scenario: Scenario) -> None:
    s = scenario
    audits = Audits(s)
    dashboard_before = s.client.get(f"/api/v1/dashboards/{audits.revision['family_id']}").json()

    first = audits.request()
    assert first["reused"] is False
    audit = first["audit"]
    assert (audit["dashboard_revision_id"], audit["prompt_id"], audit["prompt_version"]) == (
        audits.revision["id"],
        "copilot-audit",
        "v1",
    )
    assert [c["included"] for c in audit["cards"]] == [True, True, True]
    content = audit["content"]
    assert len(content["recomendaciones"]) == 2 and content["alertas_criticas"] == []
    # Cada cifra del resumen es la de su evidencia, con la ejecución de su tarjeta.
    figures = [seg for seg in content["resumen_ejecutivo"] if seg["kind"] == "evidence"]
    assert len(figures) == 2
    runs = set(audits.analyses.runs.values())
    for figure in figures:
        assert figure["execution_id"] in runs
        evidence = s.client.get(
            f"/api/v1/executions/{figure['execution_id']}/evidence/{figure['evidence_id']}"
        ).json()
        assert evidence["value"].replace(".", ",") in figure["text"]
    assert content["unverified_numbers"] == 0
    [call] = audits.calls()
    assert (call.outcome, call.prompt_id, call.prompt_version, call.conversation_id) == (
        "accepted",
        "copilot-audit",
        "v1",
        None,
    )
    assert call.validation["evidence_references"] == 2

    # Misma clave de contenido: la auditoría guardada, sin otra llamada al proveedor.
    again = audits.request()
    assert again["reused"] is True and again["audit"] == audit
    key = str(uuid4())
    assert audits.request(key=key)["audit"]["id"] == audit["id"]
    assert audits.request(key=key)["audit"]["id"] == audit["id"]  # misma Idempotency-Key
    assert len(audits.calls()) == 1
    listed = s.client.get(audits.url).json()
    assert [a["id"] for a in listed] == [audit["id"]]

    # Otra configuración es otra clave: nueva llamada y nueva auditoría.
    audits.config = config(max_output_tokens=2000)
    other = audits.request()
    assert other["reused"] is False and other["audit"]["audit_key"] != audit["audit_key"]
    assert other["audit"]["result_sha256"] == audit["result_sha256"]
    assert len(audits.calls()) == 2

    # El dashboard no cambia.
    dashboard_after = s.client.get(f"/api/v1/dashboards/{audits.revision['family_id']}").json()
    assert dashboard_after == dashboard_before


def test_free_numbers_are_removed_and_counted(scenario: Scenario) -> None:
    audits = Audits(scenario)
    run, evidence = audits.evidence()[0]
    audits.script(
        audit_output(
            resumen_ejecutivo=f"Las ventas suman 1.234,56 € ({{{{evidence:{evidence}}}}}).",
            alertas_criticas=[
                {"titulo": "Caída del 12 %", "detalle": "Bajó en 2026.", "severidad": "alta"}
            ],
        )
    )
    content = audits.request()["audit"]["content"]
    assert "1.234,56" not in text(content["resumen_ejecutivo"])
    assert "[cifra no verificada]" in text(content["resumen_ejecutivo"])
    assert text(content["alertas_criticas"][0]["titulo"]) == "Caída del [cifra no verificada]"
    assert content["unverified_numbers"] == 3
    [figure] = [s for s in content["resumen_ejecutivo"] if s["kind"] == "evidence"]
    assert (figure["execution_id"], figure["evidence_id"]) == (run, evidence)


def test_missing_or_foreign_evidence_voids_the_audit_and_the_dashboard_stays(
    scenario: Scenario,
) -> None:
    s = scenario
    audits = Audits(s)
    for reference in ["{{evidence:" + "0" * 64 + "}}", "{{evidence:}}", "{{otra:cosa}}"]:
        audits.script(audit_output(recomendaciones=[f"Mira {reference}.", "Revisa."]))
        error = audits.request(status=422)
        assert error["code"] == "INVALID_EVIDENCE_REFERENCE"
    assert s.client.get(audits.url).json() == []
    assert s.db.scalar(select(func.count()).select_from(TextAuditRecord)) == 0
    assert [c.outcome for c in audits.calls()] == ["rejected"] * 3
    assert s.client.get(f"/api/v1/dashboards/{audits.revision['family_id']}").status_code == 200


def test_provider_failures_are_logged_and_save_nothing(scenario: Scenario) -> None:
    s = scenario
    audits = Audits(s)
    audits.script(AIProviderError("AI_TIMEOUT", "Tiempo agotado."))
    error = audits.request(status=502)
    assert error["code"] == "AI_TIMEOUT"
    # Fuera del esquema (una sola recomendación): se descarta.
    audits.script(audit_output(recomendaciones=["Sólo una."]))
    assert audits.request(status=502)["code"] == "AI_INVALID_OUTPUT"
    assert [(c.outcome, c.error_code) for c in audits.calls()] == [
        ("provider_error", "AI_TIMEOUT"),
        ("provider_error", "AI_INVALID_OUTPUT"),
    ]
    assert s.client.get(audits.url).json() == []
    # El siguiente intento funciona.
    audits.provider = FakeProvider(responder=simulated)
    assert audits.request()["reused"] is False


def test_only_published_results_and_no_rows_reach_the_provider(scenario: Scenario) -> None:
    s = scenario
    analyses_cards = Analyses(s)
    pending = card(analyses_cards.total, None, "kpi", "Sin ejecutar")
    audits = Audits(s, cards=[*analyses_cards.cards()[:2], pending])
    provider = FakeProvider(responder=simulated)
    audits.provider = provider
    audit = audits.request()["audit"]
    assert [(c["title"], c["included"], c["reason"]) for c in audit["cards"]] == [
        ("Ingresos totales", True, None),
        ("Ingresos por región", True, None),
        ("Sin ejecutar", False, "not_executed"),
    ]
    assert [text(a["titulo"]) for a in audit["content"]["alertas_criticas"]] == [
        "Tarjetas sin resultado"
    ]
    sent = provider.requests[0]
    assert sent.system == prompts.AUDIT_SYSTEM and sent.output_schema is AuditoriaTextual
    prompt = "\n".join(m.content for m in sent.messages)
    assert '"dato_no_confiable":"Ventas"' in prompt  # título del dashboard: dato, no instrucción
    # Agregados y etiquetas autorizadas, nunca filas de detalle (fechas o importes por fila).
    for value in ["100.50", "2026-01-01"]:
        assert value not in prompt, value
    context = sent.context["contexto"]
    assert set(context) == {"dashboard", "tarjetas", "tarjetas_sin_resultado"}
    assert context["tarjetas_sin_resultado"] == 1


def test_nothing_to_audit_unavailable_ai_budget_and_access(scenario: Scenario) -> None:
    s = scenario
    analyses = Analyses(s)
    audits = Audits(s, cards=[card(analyses.total, None, "kpi", "Sin ejecutar")])
    assert audits.request(status=409)["code"] == "RESULT_NOT_READY"

    audits = Audits(s)
    audits.provider = None
    audits.config = config(unavailable="disabled")
    assert audits.request(status=503)["code"] == "COPILOT_UNAVAILABLE"
    audits.provider = FakeProvider(responder=simulated)
    audits.config = config(user_daily_tokens=0)
    assert audits.request(status=429)["code"] == "AI_BUDGET_EXCEEDED"
    audits.config = config()

    without_csrf = s.client.post(audits.url, headers={"Idempotency-Key": str(uuid4())})
    assert without_csrf.status_code == 403
    assert s.client.post(audits.url, headers=s.headers).status_code == 422  # sin Idempotency-Key
    saved = audits.request()["audit"]["id"]
    s.headers = account(s.client)  # otra cuenta
    assert audits.request(status=404)["code"]
    assert s.client.get(audits.url).status_code == 404
    unknown = f"/api/v1/dashboard-revisions/{uuid4()}/text-audits"
    assert s.client.get(unknown).status_code == 404
    assert saved


def test_verification_rules_without_the_api() -> None:
    from uuid import UUID

    execution = UUID(int=7)
    cell = ResultCell(
        evidence_id="e" * 64,
        cell="value",
        metric_key="m0",
        metric_label="Ingresos",
        aggregation="sum",
        currency="EUR",
        unit=None,
        value="1234.50",
        group={"region": "Norte"},
        period=None,
    )
    output = AuditoriaTextual.model_validate(
        audit_output(resumen_ejecutivo="Total {{evidence:" + "e" * 64 + "}} y 15 más.")
    )
    content, invalid = verify_audit(output, {cell.evidence_id: cell}, {cell.evidence_id: execution})
    assert invalid == [] and content is not None
    figure = next(s for s in content.resumen_ejecutivo if s.kind == "evidence")
    assert figure.execution_id == execution and "1.234,50" in figure.text
    assert content.unverified_numbers == 1
    foreign = AuditoriaTextual.model_validate(
        audit_output(
            alertas_criticas=[{"titulo": "x", "detalle": "{{evidence:f}}", "severidad": "baja"}]
        )
    )
    assert verify_audit(foreign, {cell.evidence_id: cell}, {})[0] is None
    with pytest.raises(ValueError):
        AuditoriaTextual.model_validate(audit_output(recomendaciones=["a", "b", "c"]))
    with pytest.raises(ValueError):
        AuditoriaTextual.model_validate(
            audit_output(
                alertas_criticas=[{"titulo": "t", "detalle": "d", "severidad": "alta"}] * 4
            )
        )
