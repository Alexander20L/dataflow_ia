"""Fase 24B: mejoras de la pestaña Comprensión (ADR-042).

- Una columna se puede marcar como desconocida (migración 0025); lo heredan las versiones
  siguientes y nunca se combina con un significado escrito.
- El significado vigente del usuario llega al informe: guardarlo pide otra versión del informe y
  el informe describe la columna con ese significado y su procedencia.
- La IA justifica cada significado (prompt v3) y la justificación no puede traer cifras.
- El PDF muestra cada cifra con tres decimales como mucho (`display-decimals-v1`); las cifras
  canónicas y sus evidencias no cambian.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase24_comprehension import get, run_all, runs, students

import dataflow.bootstrap.delivery_job as delivery_job
from dataflow.modules.comprehension.contracts import (
    AIComprehension,
    ColumnMeaning,
    Comprehension,
    UserMeaning,
)
from dataflow.modules.comprehension.domain import (
    USER_UNKNOWN_MEANING,
    accept_ai,
    with_user_meanings,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.numbers import cap_decimals
from dataflow.modules.delivery.pdf import axis_label
from dataflow.modules.delivery.pdf import text as pdf_text
from dataflow.platform.config import get_settings


def test_unknown_mark_replaces_the_ai_meaning() -> None:
    ai = [ColumnMeaning(column="ESTREG", meaning="Estado del registro", confidence="low")]
    marked = with_user_meanings(ai, {"ESTREG": UserMeaning(None, False, True)})
    assert marked[0].unknown and marked[0].source == "user"
    assert marked[0].meaning == USER_UNKNOWN_MEANING and marked[0].confidence is None
    # Sin marca vuelve el de la IA.
    assert with_user_meanings(ai, {}) == ai


def test_ai_justification_is_kept_without_figures() -> None:
    reply = AIComprehension(
        domain="Notas de estudiantes.",
        entities=[],
        meanings=[
            ColumnMeaning(
                column="nota", meaning="Nota final", confidence="high", reason="Por el nombre."
            ),
            ColumnMeaning(
                column="horas", meaning="Horas", confidence="medium", reason="Promedia 12,5."
            ),
        ],
        orders={},
        relationships=[],
        questions=[],
    )
    accepted, discarded = accept_ai(reply, ["nota", "horas"])
    by = {m.column: m for m in accepted.meanings}
    assert by["nota"].reason == "Por el nombre."
    assert by["horas"].reason is None and any("Justificación" in d for d in discarded)


def test_unknown_mark_is_inherited_and_meanings_reach_the_report(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Comprehension | None] = []
    # Fase 27: las cargas nuevas usan el informe v2 (la comprensión es su sexto argumento).
    original = delivery_job.build_report_v2

    def capture(*args: Any) -> Any:
        seen.append(args[5])
        return original(*args)

    monkeypatch.setattr(delivery_job, "build_report_v2", capture)
    headers = account(client)
    pid = project(client, headers)
    content = students()
    version = upload(client, headers, pid, content, name="notas.csv").json()["id"]
    run_all(db, objects)
    reports = len(runs(db, version, "automatic_report"))
    path = f"/api/v1/versions/{version}/comprehension/meanings"
    invalid = client.post(
        path, json={"column": "tutor", "meaning": "Tutor", "unknown": True}, headers=headers
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "MEANING_INVALID"
    marked = client.post(path, json={"column": "tutor", "unknown": True}, headers=headers)
    assert marked.status_code == 200, marked.text
    meaning = {m["column"]: m for m in marked.json()["comprehension"]["meanings"]}["tutor"]
    assert meaning["unknown"] and meaning["source"] == "user"
    written = client.post(
        path, json={"column": "horas", "meaning": "Horas de estudio por semana"}, headers=headers
    )
    assert written.status_code == 200, written.text
    # Guardar un significado pide otra versión del informe (sólo una mientras espera en cola);
    # no se rehace ningún cálculo.
    assert len(runs(db, version, "automatic_report")) == reports + 1
    explorations = len(runs(db, version, "exploration"))
    seen.clear()
    run_all(db, objects)
    assert len(runs(db, version, "exploration")) == explorations
    latest = runs(db, version, "automatic_report")[-1]
    assert latest.state == "succeeded"
    assert seen and seen[-1] is not None
    described = {m.column: m for m in seen[-1].meanings}
    assert described["horas"].meaning == "Horas de estudio por semana"
    assert described["horas"].source == "user"
    assert described["tutor"].unknown
    # La siguiente versión del mismo archivo hereda la marca.
    second = upload(client, headers, pid, content, name="notas.csv").json()["id"]
    run_all(db, objects)
    inherited = get(client, f"/api/v1/versions/{second}/comprehension")["comprehension"]
    assert {m["column"]: m for m in inherited["meanings"]}["tutor"]["unknown"]
    # Quitar la marca (sin texto, sin confirmar y sin marcar) vuelve al de la IA.
    client.post(path, json={"column": "tutor"}, headers=headers)
    back = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert not any(m["unknown"] for m in back["meanings"] if m["column"] == "tutor")


def test_fake_ai_meanings_carry_a_justification(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, students(), name="notas.csv").json()["id"]
    run_all(db, objects)
    found = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert found["ai_state"] == "ready", found["ai_reason"]
    assert found["meanings"] and all(m["reason"] for m in found["meanings"])


@pytest.mark.parametrize(
    ("shown", "expected"),
    [
        ("0.123456", "0.123"),
        ("12.50", "12.50"),  # tres decimales o menos: tal cual
        ("1.29999", "1.3"),  # los ceros que deja el redondeo se quitan
        ("2.0004", "2"),
        ("-0.0001", "0"),  # sin «-0»
        ("-1.2345", "-1.235"),  # mitad lejos de cero
        ("1.234,56789", "1.234,568"),
        ("999,9996", "1.000"),
        ("1.234", "1.234"),  # miles españoles: no son decimales
        ("Total 1234.5678 (ρ 0,8123) en 2024-10, v12", "Total 1234.568 (ρ 0,812) en 2024-10, v12"),
        ("id ab12.3456x", "id ab12.3456x"),  # no es una cifra
    ],
)
def test_report_shows_at_most_three_decimals(shown: str, expected: str) -> None:
    assert cap_decimals(shown) == expected


def test_pdf_text_and_axis_use_the_display_rule() -> None:
    assert pdf_text("Media 0.30000000000000004 & más") == "Media 0.3 &amp; más"
    assert axis_label(0.30000000000000004) == "0.3"
    assert axis_label(2500.0) == "2500"
