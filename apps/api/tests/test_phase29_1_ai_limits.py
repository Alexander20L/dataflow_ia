"""Fase 29.1: la IA tiene tiempo y presupuesto para investigar, y sus textos leen bien las cifras.

- Los trabajos con IA tienen su propio plazo (`ai_job_timeout_seconds`, 100 s) dentro de la lease
  de 120 s; la lectura de archivos sigue con `processing_timeout_seconds`.
- Cada llamada espera como mucho el menor entre su límite (`ai_timeout_seconds`, 60 s) y lo que le
  queda a la investigación; el presupuesto de la investigación (0,20 USD) deja sitio a la
  propuesta y al juicio.
- En los textos de la IA cada cifra tiene como mucho tres decimales (ADR-042) y no se escriben
  las unidades internas (`number`, `count`, `index`).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase25_investigation import reference_csv, run_all

from dataflow.bootstrap.ai import ai_job_config
from dataflow.bootstrap.services import processing_config
from dataflow.integrations.ai import AIMessage, AIRequest, FakeProvider
from dataflow.modules.copilot.contracts import ResultCell
from dataflow.modules.copilot.domain import display_number, format_cell
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.exploration.contracts import ExplorationLimits
from dataflow.platform.config import Settings, get_settings


def cell(value: str, unit: str | None = "number", **changes: Any) -> ResultCell:
    data: dict[str, Any] = {
        "evidence_id": "e1",
        "cell": "value",
        "metric_key": "e1",
        "metric_label": "costo",
        "aggregation": "report",
        "currency": None,
        "unit": unit,
        "value": value,
        "group": {},
        "period": None,
    }
    data.update(changes)
    return ResultCell(**data)


def test_figures_in_ai_texts_have_three_decimals_and_no_internal_units() -> None:
    assert display_number("347.744800") == "347,745"
    assert display_number("2.0004") == "2"
    assert display_number("12.50") == "12,50"  # tres o menos decimales: no cambia
    assert display_number("1234567.1239") == "1.234.567,124"
    assert display_number("-0.0001") == "0"
    assert format_cell(cell("347.744800")) == "347,745"
    assert format_cell(cell("200", "count")) == "200"
    assert format_cell(cell("37.14", "percent")) == "37,14 %"
    assert format_cell(cell("1.5", "index")) == "1,5"
    assert format_cell(cell("1234.5678", None, currency="COP")) == "1.234,568 COP"
    assert format_cell(cell("12.3456", None, cell="change_pct")) == "12,346 %"


def test_ai_jobs_have_their_own_deadline() -> None:
    settings = Settings()
    assert settings.ai_timeout_seconds == 60 and settings.ai_job_timeout_seconds == 100
    config = processing_config()
    assert config.timeout_seconds == get_settings().processing_timeout_seconds
    assert ai_job_config(config).timeout_seconds == get_settings().ai_job_timeout_seconds
    limits = ExplorationLimits()
    assert limits.max_seconds == 95 and limits.max_cost_usd == "0.20" and limits.max_ai_calls == 3


class Echo(BaseModel):
    ok: bool


def test_a_call_waits_at_most_what_is_left() -> None:
    from dataflow.integrations.ai.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider("sk-ant-test", "claude-opus-5-5", "low", 60)
    used: list[float] = []

    class Stop(Exception):
        pass

    class Client:
        def __init__(self, timeout: float) -> None:
            used.append(timeout)
            self.beta = self

        @property
        def messages(self) -> "Client":
            return self

        def parse(self, **_: Any) -> None:
            raise Stop

    provider.client.with_options = lambda **options: Client(options["timeout"])  # type: ignore[method-assign]

    def request(timeout: float | None) -> AIRequest[Echo]:
        return AIRequest(
            task="t",
            prompt_id="p",
            prompt_version="1",
            system="s",
            messages=[AIMessage(role="user", content="hola")],
            output_schema=Echo,
            max_output_tokens=10,
            timeout_seconds=timeout,
        )

    for left in (25.5, 300.0, 0.2):
        with pytest.raises(Stop):
            provider.complete(request(left))
    assert used == [25.5, 60.0, 1.0]


def test_the_investigation_gives_each_ai_call_the_time_left(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    seen: list[tuple[str, float | None]] = []
    parts: list[int] = []
    original = FakeProvider.complete

    def recording(self: FakeProvider, request: AIRequest[Any]) -> Any:
        seen.append((request.task, request.timeout_seconds))
        if request.task == "exploration_relevance":
            parts.append(len(request.context["contexto"]["resultados"]))
        return original(self, request)

    monkeypatch.setattr(FakeProvider, "complete", recording)
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    result = client.get(f"/api/v1/versions/{version['id']}/exploration").json()["exploration"]
    # Con el plazo de los trabajos con IA (100 s), la investigación dispone de 95 s.
    assert result["limits"]["max_seconds"] == 95 and result["limits"]["max_cost_usd"] == "0.20"
    purposes = [call["purpose"] for call in result["calls"]]
    assert purposes.count("proposal") == 1
    # El juicio del primer nivel va en partes de 10 resultados como mucho (en paralelo).
    assert 1 <= purposes.count("relevance") <= 2 and parts and max(parts) <= 10
    assert sum(parts) > 10  # hubo más de una parte
    assert result["consumption"]["ai_calls"] == len(result["calls"]) <= 3
    timed = [t for task, t in seen if task.startswith("exploration_")]
    assert timed and all(t is not None and 0 < t <= 95 for t in timed)
