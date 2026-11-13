"""Fase 25 (ADR-043): investigación con plan, árbol, evidencias, clasificación y control.

Cubre los criterios de la pestaña Investigación: plan pertinente, sin análisis temporales si no
hay fechas, operaciones apropiadas para las medidas, hipótesis inválidas descartadas,
investigaciones secundarias, cálculo sobre todos los datos, evidencia rastreable, límites de
recursos y errores de ejecución registrados; y el control del usuario por la API.
"""

import csv
import io
from collections import defaultdict
from decimal import Decimal
from itertools import count
from uuid import uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.comprehension.contracts import (
    Comprehension,
    ComprehensionScope,
    MeasureInfo,
    Period,
)
from dataflow.modules.comprehension.domain import scales
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.exploration.contracts import (
    ExplorationLimits,
    ExploreQuery,
    ExploreResult,
    InvestigationNode,
    RawQuery,
)
from dataflow.modules.exploration.domain import Catalog, validate
from dataflow.modules.exploration.engine import compute
from dataflow.modules.exploration.investigator import (
    Investigator,
    JudgeReply,
    Verdict,
    plan_nodes,
)
from dataflow.modules.exploration.plan import Draft, evaluate, rule_plan
from dataflow.platform.config import get_settings

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August"]


def table() -> bytes:
    """Ocho meses: el Norte crece fuerte, el Sur se mantiene; un valor atípico en agosto."""
    rows: dict[str, list[object]] = {k: [] for k in ("Year", "Month", "Region", "Revenue", "Units")}
    for index, month in enumerate(MONTHS):
        for region, base, step in (("Norte", 100, 40), ("Sur", 100, 0)):
            for item in range(3):
                revenue = base + step * index + item
                if month == "August" and region == "Sur" and item == 2:
                    revenue = 5000
                rows["Year"].append("2024")
                rows["Month"].append(month)
                rows["Region"].append(region)
                rows["Revenue"].append(str(revenue))
                rows["Units"].append(str(1 + item))
    buffer = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buffer)
    return buffer.getvalue()


def comprehension(period: bool = True) -> Comprehension:
    return Comprehension(
        scope=ComprehensionScope(
            execution_id=uuid4(), version_id=uuid4(), profile_sha256="p" * 64, table_sha256="t" * 64
        ),
        ai_state="unavailable",
        scales=scales(
            [("Revenue", "measure"), ("Units", "measure"), ("Region", "dimension")],
            {"Region": ["Norte", "Sur"]},
        ),
        associations=[],
        matrix_columns=[],
        relationships=[],
        limitations=[],
        measures=[
            MeasureInfo(
                column="Revenue", additivity="additive", aggregation="sum", monetary=True, reason=""
            ),
            MeasureInfo(column="Units", additivity="additive", aggregation="sum", reason=""),
        ],
        period=Period(
            kind="year_month",
            columns=["Year", "Month"],
            first="2024-01",
            last="2024-08",
            periods=8,
            missing=0,
            note="",
        )
        if period
        else None,
    )


def catalog(period: bool = True) -> Catalog:
    return Catalog(comprehension(period), {"Revenue", "Units"})


def investigator(
    found: Catalog,
    limits: ExplorationLimits | None = None,
    clock: object = None,
    control: object = None,
    judge: object = None,
    computer: object = None,
) -> Investigator:
    content = table()
    return Investigator(
        found,
        computer or (lambda query: compute(content, query, "x", found.period)),  # type: ignore[arg-type]
        48,
        limits or ExplorationLimits(),
        clock or (lambda: 0.0),  # type: ignore[arg-type]
        control or (lambda: None),  # type: ignore[arg-type]
        judge,  # type: ignore[arg-type]
        uuid4(),
    )


# --- Plan ----------------------------------------------------------------------------------------


def test_plan_is_pertinent_and_complete() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    kinds = [n.query["kind"] for n in nodes]
    assert kinds[:2] == ["evolution", "period_change"]
    assert "top" in kinds and "outliers" in kinds
    change = nodes[1]
    assert change.depends_on == [nodes[0].id]  # depende de la evolución
    for item in nodes:
        assert item.question and item.motive and item.hypothesis and item.expected
        assert item.columns and item.method and item.priority in {1, 2, 3}
        assert item.status == "pending" and item.key
    # Medida aditiva: se suma (no se promedia).
    top = next(n for n in nodes if n.query["kind"] == "top")
    assert top.query["aggregation"] == "sum" and top.query["measure"] == "Revenue"


def test_without_dates_no_temporal_analysis_is_invented() -> None:
    found = catalog(period=False)
    assert "evolution" not in found.kinds()
    kinds = {d.raw.kind for d in rule_plan(comprehension(False), found)}
    assert not kinds & {"evolution", "period_change"}
    query, reason = validate(RawQuery(kind="evolution", measure="Revenue"), found, set())
    assert query is None and reason and "no se inventan análisis temporales" in reason


def test_invalid_hypothesis_is_discarded_with_its_reason() -> None:
    found = catalog()
    draft = Draft(
        RawQuery(kind="aggregate", measure="Inventada", dimensions=["Region"]),
        "ai",
        "¿Pregunta?",
        "Motivo",
        "Hipótesis",
        "Esperado",
    )
    nodes, _ = plan_nodes([draft], found, 20)
    assert nodes[0].status == "rejected" and nodes[0].classification == "discarded"
    assert nodes[0].reason and "no es una medida" in nodes[0].reason
    assert (nodes[0].decision_reason or "").startswith("Hipótesis descartada")


# --- Ejecución, árbol y evidencia -----------------------------------------------------------------


def test_tree_deepens_on_interesting_results_with_full_data_and_evidence() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    outcome = investigator(found).run(nodes, {})
    assert outcome.stopped == "completed"
    by_kind = {n.query["kind"]: n for n in outcome.nodes if n.parent is None}
    evolution = by_kind["evolution"]
    assert evolution.classification == "relevant" and evolution.decision == "deepen"
    children = [n for n in outcome.nodes if n.parent == evolution.id]
    assert children and children[0].id == f"{evolution.id}.1"
    assert children[0].query["kind"] == "period_change"
    # Todas las filas: la serie mensual suma los ingresos de cada mes.
    series = outcome.results[evolution.key or ""]
    expected: dict[str, Decimal] = defaultdict(Decimal)
    frame = pl.read_parquet(io.BytesIO(table()))
    for month, revenue in zip(frame["Month"], frame["Revenue"], strict=True):
        expected[f"2024-{MONTHS.index(month) + 1:02d}"] += Decimal(revenue)
    assert {r.groups[0]: Decimal(r.figures[0].value or "0") for r in series.rows} == expected
    assert [r.groups[0] for r in series.rows] == sorted(expected)  # orden cronológico
    for item in outcome.nodes:
        if item.status != "computed" or item.key is None:
            continue
        result = outcome.results[item.key]
        assert item.rows_considered == result.covered_rows and item.total_rows == 48
        assert item.criteria and item.criteria[0].name == "magnitude"
        assert all(f.evidence_id for r in result.rows for f in r.figures)
        assert item.decision in {"deepen", "finish"} and item.decision_reason
    # Los periodos comparados y sus importes quedan en la evidencia.
    change = outcome.results[by_kind["period_change"].key or ""]
    assert change.rows[0].figures[0].label == "Suma de Revenue (2024-03 a 2024-05)"
    assert change.rows[0].figures[1].label == "Suma de Revenue (2024-06 a 2024-08)"


def test_outliers_and_period_change_are_exact() -> None:
    found = catalog()
    content = table()
    outliers = compute(content, ExploreQuery(kind="outliers", measure="Revenue"), "x", found.period)
    assert isinstance(outliers, ExploreResult)
    figures = {f.label: f.value for f in outliers.rows[0].figures}
    assert figures["Atípicos"] == "1" and outliers.rows[0].rows == 48
    change = compute(
        content,
        ExploreQuery(kind="period_change", measure="Revenue", aggregation="sum", limit=4),
        "x",
        found.period,
    )
    assert isinstance(change, ExploreResult)
    values = [f.value for f in change.rows[0].figures]
    frame = pl.read_parquet(io.BytesIO(content))
    months = [MONTHS.index(m) for m in frame["Month"]]
    first = sum(Decimal(v) for v, m in zip(frame["Revenue"], months, strict=True) if m < 4)
    last = sum(Decimal(v) for v, m in zip(frame["Revenue"], months, strict=True) if m >= 4)
    assert values[:3] == [str(first), str(last), str(last - first)]


def test_classification_uses_magnitude_quality_and_size() -> None:
    query = ExploreQuery(
        kind="aggregate", measure="Revenue", dimensions=["Region"], aggregation="mean"
    )
    result = compute(table(), query, "x")
    assert isinstance(result, ExploreResult)
    classification, criteria, limitations = evaluate(query, result, 48)
    assert classification in {"relevant", "secondary"}
    assert [c.name for c in criteria] == ["magnitude", "quality", "consistency", "evidence"]
    # Con menos de la mitad de los registros, la calidad rebaja la clase.
    lowered, _, notes = evaluate(query, result, 200)
    order = ["relevant", "secondary", "descriptive", "discarded"]
    assert order.index(lowered) > order.index(classification)
    assert any("Se excluyeron 152 registros" in note for note in notes)


def test_ai_can_only_lower_a_result_and_its_children_are_validated() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    calls = count()

    def judge(items: list[tuple[InvestigationNode, ExploreResult]]) -> JudgeReply:
        next(calls)
        return JudgeReply(
            {
                item.id: Verdict(
                    False,
                    "Sin interés para el negocio.",
                    [RawQuery(kind="aggregate", measure="Inventada", dimensions=["Region"])],
                )
                for item, _ in items
            },
            Decimal("0.001"),
            True,
        )

    outcome = investigator(found, judge=judge).run(nodes, {})
    evolution = next(n for n in outcome.nodes if n.query["kind"] == "evolution")
    assert evolution.classification == "secondary"  # relevante por reglas, rebajado por la IA
    assert evolution.interpretation == "Sin interés para el negocio."
    rejected = [n for n in outcome.nodes if n.origin == "ai" and n.status == "rejected"]
    assert rejected and all(n.classification == "discarded" for n in rejected)
    assert outcome.ai_calls == next(calls)


# --- Límites, errores y reanudación ---------------------------------------------------------------


def test_resource_limits_stop_the_process_cleanly_and_it_resumes() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    ticks = iter([0.0, 0.0, 0.0, 100.0])
    first = investigator(
        found, ExplorationLimits(max_seconds=5), clock=lambda: next(ticks, 100.0)
    ).run(nodes, {})
    assert first.stopped == "max_seconds"
    assert any(n.status == "pending" for n in first.nodes)
    assert any("se pueden reanudar" in text for text in first.limitations)
    done = {n.id for n in first.nodes if n.status == "computed"}
    again = investigator(found).run(first.nodes, dict(first.results))
    assert again.stopped == "completed"
    assert all(n.status != "pending" for n in again.nodes)
    kept = {n.id: n.execution_id for n in first.nodes if n.id in done}
    assert all(n.execution_id == kept[n.id] for n in again.nodes if n.id in done)
    # Límite de investigaciones: el plan se recorta y lo dice.
    trimmed, notes = plan_nodes(rule_plan(comprehension(), found), found, 2)
    assert sum(1 for n in trimmed if n.status != "rejected") == 2 and notes
    limited = investigator(found, ExplorationLimits(max_nodes=3)).run(trimmed, {})
    assert limited.stopped == "max_nodes"


def test_execution_error_is_recorded_and_the_rest_continues() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    content = table()

    def computer(query: ExploreQuery) -> ExploreResult | str:
        if query.kind == "outliers":
            raise RuntimeError("fallo")
        return compute(content, query, "x", found.period)

    outcome = investigator(found, computer=computer).run(nodes, {})
    failed = [n for n in outcome.nodes if n.status == "failed"]
    assert failed and "Error de ejecución" in (failed[0].reason or "")
    assert any(n.status == "computed" for n in outcome.nodes)


def test_pause_and_cancel_stop_before_the_next_investigation() -> None:
    found = catalog()
    nodes, _ = plan_nodes(rule_plan(comprehension(), found), found, 20)
    paused = investigator(found, control=lambda: "pause").run(nodes, {})
    assert paused.stopped == "paused" and all(n.status == "pending" for n in paused.nodes)
    cancelled = investigator(found, control=lambda: "cancel").run(nodes, {})
    assert cancelled.stopped == "cancelled"


# --- API: recorrido completo y control del usuario --------------------------------------------


def run_until_exploration_queued(db: Session, objects: LocalObjects, version: str) -> None:
    runner = make_runner(db, objects)
    for _ in range(20):
        found = db.scalars(
            select(ExecutionRecord).where(
                ExecutionRecord.version_id == version, ExecutionRecord.kind == "exploration"
            )
        ).first()
        if found is not None:
            return
        if not runner.run_once():
            break
    raise AssertionError("La investigación no llegó a la cola.")


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def test_upload_is_investigated_with_plan_tree_and_evidence(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    view = client.get(f"/api/v1/versions/{version['id']}/exploration").json()
    result = view["exploration"]
    assert result["rules_version"] == "investigation-v2" and result["stopped"] in {
        "completed",
        "max_nodes",
    }
    assert result["trigger"] == "load" and view["resumable"] is False
    nodes = result["nodes"]
    assert {n["query"]["kind"] for n in nodes} >= {"evolution", "top", "outliers"}
    assert any(n["origin"] == "ai" for n in nodes)
    assert any(n["parent"] for n in nodes)  # investigaciones secundarias
    rows = len(list(csv.DictReader(io.StringIO(reference_csv().decode("utf-8-sig")))))
    keys = {r["key"] for r in result["results"]}
    for item in nodes:
        if item["status"] == "computed" and item["key"]:
            assert item["key"] in keys and item["total_rows"] == rows
            assert item["execution_id"] == view["execution_id"]
    consumption = result["consumption"]
    assert consumption["ai_calls"] >= 1 and consumption["nodes"] >= 4


def test_user_controls_the_investigation(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}/exploration"
    run_until_exploration_queued(db, objects, version["id"])
    paused = client.post(f"{base}/control", json={"action": "pause"}, headers=headers)
    assert paused.status_code == 200 and paused.json()["control"] == "pause"
    first_id = paused.json()["execution_id"]
    run_all(db, objects)
    view = client.get(base).json()
    assert view["exploration"]["stopped"] == "paused" and view["resumable"] is True
    assert all(n["status"] == "pending" for n in view["exploration"]["nodes"])
    # Terminada: no se puede pausar.
    late = client.post(f"{base}/control", json={"action": "pause"}, headers=headers)
    assert late.status_code == 409 and late.json()["code"] == "INVESTIGATION_FINISHED"
    resumed = client.post(f"{base}/control", json={"action": "resume"}, headers=headers)
    assert resumed.status_code == 200 and resumed.json()["state"] == "queued"
    run_all(db, objects)
    done = client.get(base).json()
    assert done["exploration"]["stopped"] in {"completed", "max_nodes"}
    assert done["exploration"]["resumed_from"] == first_id
    assert done["exploration"]["trigger"] == "resume"
    again = client.post(f"{base}/control", json={"action": "resume"}, headers=headers)
    assert again.status_code == 409 and again.json()["code"] == "INVESTIGATION_NOT_RESUMABLE"
    # Volver a investigar y cancelar: se detiene sin poder reanudarse.
    restarted = client.post(f"{base}/control", json={"action": "restart"}, headers=headers)
    assert restarted.status_code == 200
    busy = client.post(f"{base}/control", json={"action": "restart"}, headers=headers)
    assert busy.status_code == 409 and busy.json()["code"] == "INVESTIGATION_RUNNING"
    client.post(f"{base}/control", json={"action": "cancel"}, headers=headers)
    run_all(db, objects)
    cancelled = client.get(base).json()
    assert cancelled["exploration"]["stopped"] == "cancelled" and cancelled["resumable"] is False
    history = client.get(f"{base}/history").json()["items"]
    assert [h["trigger"] for h in history] == ["restart", "resume", "load"]
    stops = [h["stopped"] for h in history]
    assert stops[0] == "cancelled" and stops[2] == "paused"
    assert stops[1] in {"completed", "max_nodes"}
    # Una investigación anterior del historial se puede consultar.
    old = client.get(base, params={"execution_id": first_id}).json()
    assert old["exploration"]["stopped"] == "paused"
    account(client)
    assert client.get(f"{base}/history").status_code == 404
