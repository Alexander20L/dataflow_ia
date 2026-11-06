"""Fase 10 · copiloto de punta a punta con el proveedor falso: ciclo completo, IA desactivada,
privacidad del contexto, registro de llamadas, límites, idempotencia y accesos."""

import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from ai_support import Copilot, income_metric, ready_table, visible_text
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_cleaning_runner import Scenario
from test_csv_ingestion import account

from dataflow.bootstrap.ai import configured, simulated
from dataflow.integrations.ai import AIRequest, AIResult, FakeProvider
from dataflow.modules.copilot.infrastructure import AICallRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import Settings


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def test_request_clarification_proposal_execution_and_verified_explanation(
    scenario: Scenario,
) -> None:
    s = scenario
    table, _ = ready_table(s, semantics=False)
    copilot = Copilot(s, table)
    request = "Compara las ventas mensuales por región"

    # 1. Sin fecha de negocio confirmada: pregunta antes de proponer.
    first = copilot.ask(request)["assistant"]
    assert first["assistant"]["action"] == "ask_clarification"
    assert first["assistant"]["clarification"] == {
        "topic": "business_date",
        "resolve_in": "understanding",
    }

    # 2. Con la semántica confirmada y sin métricas: borrador de métrica que la persona crea.
    from test_analytics_runner import confirm_semantics

    confirm_semantics(s, table, importe=("measure", "EUR"), fecha=("business_date", None))
    second = copilot.ask(request)["assistant"]
    card = second["assistant"]["metric"]
    assert second["assistant"]["action"] == "propose_metric" and card["valid"], card
    assert card["draft"]["aggregation"] == "sum" and card["measure_column"] == "importe"
    assert card["draft"]["label"] == "Ventas"
    created = copilot.act(second["id"], "create-metric")["link"]
    assert created["kind"] == "metric" and created["metric_revision_id"]
    assert copilot.act(second["id"], "create-metric")["link"] == created  # idempotente

    # 3. Con la métrica: consulta validada por planning, que sólo corre al confirmarla.
    third = copilot.ask(request)["assistant"]
    proposal = third["assistant"]["query"]
    assert third["assistant"]["action"] == "propose_query" and proposal["valid"], proposal
    assert [d["name"] for d in proposal["dimensions"]] == ["region"]
    assert proposal["time_grain"] == "month"
    assert proposal["steps"][0]["operation"] == "analytics.query"
    assert proposal["steps"][0]["version"] == 2
    run = copilot.act(third["id"], "run-query")["link"]
    assert run["kind"] == "query_execution" and run["execution_id"]
    copilot.run_worker()
    assert s.client.get(f"/api/v1/executions/{run['execution_id']}").json()["state"] == (
        "succeeded"
    )

    # 4. Explicación: cada cifra sale de una evidencia del resultado, con su valor exacto.
    explanation = copilot.explain(run["execution_id"])["assistant"]
    content = explanation["assistant"]
    assert content["action"] == "explain_result" and content["status"] == "ok", content
    assert content["unverified_numbers"] == 0
    figures = [seg for seg in content["segments"] if seg["kind"] == "evidence"]
    assert len(figures) == 2
    for figure in figures:
        evidence = s.client.get(
            f"/api/v1/executions/{run['execution_id']}/evidence/{figure['evidence_id']}"
        ).json()
        expected = evidence["value"].replace(".", ",")
        assert figure["text"] == f"{expected} EUR", (figure, evidence["value"])
    # La conversación conserva todo, con las acciones registradas en cada propuesta.
    view = s.client.get(f"/api/v1/copilot/conversations/{copilot.conversation}").json()
    assert [m["role"] for m in view["messages"]] == ["user", "assistant"] * 4
    assert view["messages"][5]["links"][0]["execution_id"] == run["execution_id"]
    assert "source_text" not in json.dumps(view)


def test_without_ai_the_product_works_and_the_copilot_says_why(scenario: Scenario) -> None:
    s = scenario
    table, _ = ready_table(s)
    copilot = Copilot(s, table)
    for settings, reason in [
        (Settings(ai_provider="disabled"), "disabled"),
        (Settings(ai_provider="anthropic", ai_api_key=None, ai_api_key_file=None), "missing_key"),
    ]:
        provider, setup = configured(settings)
        assert provider is None
        copilot.provider, copilot.config = None, setup  # type: ignore[assignment]
        status = s.client.get(f"/api/v1/projects/{s.project_id}/copilot/status").json()
        assert status["available"] is False and status["reason"] == reason
        error = copilot.ask("Total de ventas", status=503)
        assert error["code"] == "COPILOT_UNAVAILABLE"
    # El resto del producto sigue igual.
    assert s.client.get(f"/api/v1/projects/{s.project_id}/plans").status_code == 200
    assert income_metric(s, table)["id"]


def test_authorized_context_and_call_log_carry_no_rows(scenario: Scenario) -> None:
    s = scenario
    table, _ = ready_table(s)
    income_metric(s, table)
    copilot = Copilot(s, table)
    provider = FakeProvider(responder=simulated)
    copilot.use(provider)
    copilot.ask("Ventas por región")
    sent = provider.requests[0]
    prompt = "\n".join(m.content for m in sent.messages) + sent.system
    # Nombres, tipos, roles y conteos sí; filas, ejemplos y resumen numérico, no.
    assert '"dato_no_confiable":"region"' in prompt
    for value in ["Norte", "Oeste", "Sur", "100.50", "80.00", "2026-01-01", "401.25"]:
        assert value not in prompt, value
    context = sent.context["contexto"]
    assert set(context) == {"tabla", "semantica", "metricas"}
    assert set(context["tabla"]["columnas"][0]) == {
        "id",
        "nombre",
        "tipo",
        "nulos",
        "distintos",
        "rol",
        "rol_confirmado",
        "moneda",
        "unidad",
        "descripcion",
    }
    calls = list(s.db.scalars(select(AICallRecord)))
    assert len(calls) == 1
    call = calls[0]
    assert (call.provider, call.model, call.task, call.outcome) == (
        "fake",
        "fake",
        "copilot_turn",
        "accepted",
    )
    assert call.prompt_id == "copilot-turn" and call.prompt_version == "v1"
    assert call.input_tokens > 0 and len(call.context_sha256) == 64
    assert call.parameters["max_output_tokens"] == 4000
    logged = json.dumps([call.parameters, call.validation])
    assert "region" not in logged and "importe" not in logged


class PricedProvider(FakeProvider):
    """Proveedor falso con precio real para probar el límite de costo."""

    @property
    def model(self) -> str:
        return "claude-opus-5-5"

    def complete[T: Any](self, request: AIRequest[T]) -> AIResult[T]:  # type: ignore[type-var]
        result = super().complete(request)
        return AIResult(result.output, result.usage, self.model, result.latency_ms)


def test_token_and_cost_limits(scenario: Scenario) -> None:
    s = scenario
    table, _ = ready_table(s)
    copilot = Copilot(s, table)
    copilot.use(FakeProvider(responder=simulated), user_daily_tokens=1)
    copilot.ask("Total de ventas")
    error = copilot.ask("Total de ventas", status=429)
    assert error["code"] == "AI_BUDGET_EXCEEDED" and "diario" in error["message"]
    status = s.client.get(f"/api/v1/projects/{s.project_id}/copilot/status").json()
    assert status["reason"] == "budget_exhausted" and status["usage"]["user_tokens_today"] > 1

    copilot.use(PricedProvider(responder=simulated), project_monthly_cost_usd=Decimal("0.000001"))
    copilot.ask("Total de ventas")
    error = copilot.ask("Total de ventas", status=429)
    assert error["code"] == "AI_BUDGET_EXCEEDED" and "mensual" in error["message"]
    costs = [c.cost_usd for c in s.db.scalars(select(AICallRecord))]
    assert any(c and c > 0 for c in costs)


def test_idempotency_and_access(scenario: Scenario) -> None:
    s = scenario
    table, _ = ready_table(s)
    copilot = Copilot(s, table)
    key = str(uuid4())
    first = copilot.ask("Total de ventas", key=key)
    again = copilot.ask("Total de ventas", key=key)
    assert again == first
    assert len(copilot.provider.requests) == 1  # type: ignore[attr-defined]
    conflict = copilot.ask("Otra pregunta", key=key, status=409)
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"

    # Otra persona no ve la conversación ni actúa sobre sus mensajes.
    original = dict(s.client.cookies)
    other = account(s.client)
    assert s.client.get(f"/api/v1/copilot/conversations/{copilot.conversation}").status_code == 404
    response = s.client.post(
        f"/api/v1/copilot/messages/{first['assistant']['id']}/run-query", headers=other
    )
    assert response.status_code == 404
    s.client.cookies.clear()
    for name, value in original.items():
        s.client.cookies.set(name, value)
    # CSRF obligatorio en las mutaciones.
    response = s.client.post(
        f"/api/v1/copilot/conversations/{copilot.conversation}/messages",
        json={"version_id": table["version_id"], "text": "Hola"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 403


def test_message_view_hides_internal_fields(scenario: Scenario) -> None:
    s = scenario
    table, _ = ready_table(s)
    copilot = Copilot(s, table)
    reply: dict[str, Any] = copilot.ask("Limpia los espacios")["assistant"]
    assert reply["assistant"]["action"] == "propose_cleaning_plan"
    assert "source_text" not in reply["assistant"]
    assert visible_text(reply).startswith("Propongo recortar")
