"""Apoyo de la suite de evaluación del copiloto (Fase 10): escenario con la v2 tipada de
ventas_calidad.csv, proveedor sustituible y atajos HTTP. Ninguna prueba necesita clave ni red."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from analytics_support import save_metric, typed_table
from test_analytics_runner import confirm_semantics
from test_cleaning_runner import Scenario

from dataflow.bootstrap.ai import simulated
from dataflow.bootstrap.app import app
from dataflow.bootstrap.dependencies import ai_setup
from dataflow.bootstrap.services import make_runner
from dataflow.integrations.ai import AIProvider, FakeProvider
from dataflow.modules.copilot.application import CopilotConfig


def config(**overrides: Any) -> CopilotConfig:
    values: dict[str, Any] = {
        "provider": "fake",
        "unavailable": None,
        "model": "fake",
        "user_daily_tokens": 1_000_000,
        "project_monthly_cost_usd": Decimal("100"),
        "max_output_tokens": 4000,
    }
    return CopilotConfig(**(values | overrides))


class Copilot:
    """Conversación sobre una versión con el proveedor indicado."""

    def __init__(self, s: Scenario, table: dict[str, Any]) -> None:
        self.s, self.table = s, table
        self.provider: AIProvider = FakeProvider(responder=simulated)
        self.config = config()
        app.dependency_overrides[ai_setup] = lambda: (self.provider, self.config)
        response = s.client.post(
            f"/api/v1/projects/{s.project_id}/copilot/conversations",
            json={"title": "Ventas"},
            headers={**s.headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        self.conversation = response.json()["id"]

    def use(self, provider: AIProvider, **overrides: Any) -> None:
        self.provider = provider
        if overrides:
            self.config = config(**overrides)

    def script(self, *outputs: Any) -> FakeProvider:
        provider = FakeProvider(script=list(outputs))
        self.use(provider)
        return provider

    def ask(self, text: str, key: str | None = None, status: int = 200) -> Any:
        response = self.s.client.post(
            f"/api/v1/copilot/conversations/{self.conversation}/messages",
            json={"version_id": self.table["version_id"], "text": text},
            headers={**self.s.headers, "Idempotency-Key": key or str(uuid4())},
        )
        assert response.status_code == status, response.text
        return response.json()

    def explain(self, execution: str, status: int = 200) -> Any:
        response = self.s.client.post(
            f"/api/v1/copilot/conversations/{self.conversation}/explanations",
            json={"execution_id": execution},
            headers={**self.s.headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == status, response.text
        return response.json()

    def act(self, message: str, action: str, status: int = 200) -> Any:
        response = self.s.client.post(
            f"/api/v1/copilot/messages/{message}/{action}", headers=self.s.headers
        )
        assert response.status_code == status, response.text
        return response.json()

    def run_worker(self) -> None:
        assert make_runner(self.s.db, self.s.objects).run_once()


def ready_table(s: Scenario, semantics: bool = True) -> tuple[dict[str, Any], Any]:
    """v2 tipada; con `semantics`, importe confirmado como medida (EUR) y fecha de negocio."""
    table = typed_table(s)
    semantic = (
        confirm_semantics(s, table, importe=("measure", "EUR"), fecha=("business_date", None))
        if semantics
        else None
    )
    return table, semantic


def income_metric(s: Scenario, table: dict[str, Any]) -> Any:
    c = s.columns
    return save_metric(
        s,
        table,
        {
            "label": "Ingresos",
            "measure_column_id": c["importe"],
            "aggregation": "sum",
            "time_column_id": c["fecha"],
        },
    ).json()["revision"]


def turn(action: str, message: str = "Propuesta.", **payload: Any) -> dict[str, Any]:
    return {
        "action": action,
        "message": message,
        "query": None,
        "metric": None,
        "cleaning_steps": [],
        "clarification": None,
        **payload,
    }


def query(metric_ids: list[str], **overrides: Any) -> dict[str, Any]:
    return {
        "metric_ids": metric_ids,
        "dimension_ids": [],
        "filters": [],
        "time_grain": None,
        "time_start": None,
        "time_end": None,
        "comparisons": [],
        "ranking_metric_id": None,
        "ranking_direction": None,
        "top_n": None,
        "share_metric_ids": [],
        **overrides,
    }


def visible_text(message: dict[str, Any]) -> str:
    return "".join(segment["text"] for segment in message["assistant"]["segments"])
