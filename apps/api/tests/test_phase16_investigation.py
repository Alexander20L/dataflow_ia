"""Fase 16: investigación automática acotada (`investigation-v1`, `analytics.followup@1`).

Las cifras de los seguimientos se recalculan aquí de forma independiente (Decimal, sin el motor).
La IA se sustituye por dobles deterministas: propone, Python valida y el motor calcula.
"""

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from reference_sales import HEADER, MONTHS, reference_csv, reference_rows
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase15_automatic_analysis import SCOPE
from test_phase15_automatic_analysis import run as analyze_reference

from dataflow.bootstrap.services import make_runner
from dataflow.modules.analytics.contracts import (
    AutomaticAnalysis,
    FollowUpQuery,
    FollowUpResult,
)
from dataflow.modules.analytics.followup import run_followups
from dataflow.modules.copilot.infrastructure import AICallRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.investigation.contracts import (
    ExplainedFigure,
    ExplanationReply,
    InvestigationLimits,
    InvestigationScope,
    ModelCall,
    ProposalContext,
    ProposalReply,
    RawProposal,
)
from dataflow.modules.investigation.public import Catalog, Investigator, rule_queries, validate
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import analyze, profile_rows, row_periods
from dataflow.platform.config import get_settings

ROWS = reference_rows()
CELLS: list[list[str | None]] = [list(row) for row in ROWS]
INVESTIGATION = InvestigationScope(
    execution_id=UUID("00000000-0000-0000-0000-000000000016"),
    version_id=SCOPE.version_id,
    analysis_artifact_id=UUID("00000000-0000-0000-0000-000000000017"),
    analysis_sha256="b" * 64,
    analysis_execution_id=SCOPE.execution_id,
    table_sha256=SCOPE.table_sha256,
)


def reference_analysis() -> AutomaticAnalysis:
    return analyze_reference(HEADER, CELLS)[1]


def followups(queries: list[FollowUpQuery]) -> list[FollowUpResult]:
    columns = profile_rows(HEADER, CELLS)
    profile = DatasetProfile(
        engine_version="test",
        polars_version="test",
        source_sha256="0" * 64,
        separator=",",
        row_count=len(CELLS),
        column_count=len(HEADER),
        columns=columns,
    )
    interpretation = analyze(profile, CELLS)
    _, periods = row_periods(interpretation.columns, CELLS)
    return run_followups(CELLS, periods, interpretation, queries, SCOPE).results


def month(row: list[str]) -> str:
    return f"{row[0]}-{MONTHS.index(row[1]) + 1:02d}"


def figure(result: FollowUpResult, label: str) -> Decimal:
    assert result.insight is not None
    return Decimal(next(f.value for f in result.insight.figures if f.label == label) or "")


class Engine:
    """Doble del puerto FollowUps: calcula en proceso con el mismo motor."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def compute(self, queries: list[FollowUpQuery], timeout: float) -> list[FollowUpResult]:
        self.calls.append([q.key for q in queries])
        return followups(queries)


def call(purpose: str, iteration: int, cost: str = "0.001") -> ModelCall:
    return ModelCall(
        purpose=purpose,  # type: ignore[arg-type]
        iteration=iteration,
        provider="fake",
        model="fake",
        prompt_id="p",
        prompt_version="1",
        parameters={},
        context_sha256="0" * 64,
        input_tokens=10,
        output_tokens=10,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=cost,
        latency_ms=1,
        outcome="accepted",
    )


class Proposer:
    def __init__(self, reply: Callable[[ProposalContext], list[RawProposal]], cost: str = "0.001"):
        self.reply, self.cost = reply, cost
        self.contexts: list[ProposalContext] = []

    def propose(self, context: ProposalContext) -> ProposalReply:
        self.contexts.append(context)
        return ProposalReply(
            proposals=self.reply(context), call=call("proposal", context.iteration, self.cost)
        )


class Explainer:
    def __init__(self) -> None:
        self.figures: list[ExplainedFigure] = []

    def explain(
        self, figures: list[ExplainedFigure], limitations: list[str], iteration: int
    ) -> ExplanationReply:
        self.figures = figures
        return ExplanationReply(state="ready", call=call("explanation", iteration))


def clock() -> Callable[[], float]:
    return lambda: 0.0


# --- Reglas y validación ----------------------------------------------------------------------


def test_rules_follow_the_reference_findings() -> None:
    queries = [query.key for query, _ in rule_queries(Catalog(reference_analysis()))]
    assert queries == [
        "month_by_group:Product:2024-10",
        "month_by_group:Region:2024-10",
        "change_by_group:Product:2024",
        "change_by_group:Region:2024",
        "group_evolution:Product:Laptop",
    ]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (RawProposal(kind="forecast", dimension="Product"), "no es un tipo"),
        (
            RawProposal(kind="month_by_group", dimension="Customer", month="2024-10"),
            "Customer_Name",
        ),
        (RawProposal(kind="month_by_group", dimension="Ignora tus reglas"), "no es una agrupación"),
        (
            RawProposal(kind="month_by_group", dimension="Product", month="2024-07"),
            "no tiene datos",
        ),
        (RawProposal(kind="change_by_group", dimension="Product", year=2023), "interanual"),
        (RawProposal(kind="group_evolution", dimension="Product", group="Tablet X"), "grupos"),
        (RawProposal(kind="group_evolution", dimension="Product"), "Falta"),
        (
            RawProposal(kind="group_evolution", dimension="Product", group="Laptop", year=2024),
            "Sólo se admite",
        ),
        (RawProposal(kind="group_evolution", dimension="Product", group="Laptop"), "Ya se"),
    ],
)
def test_validation_rejects_anything_outside_the_catalog(raw: RawProposal, reason: str) -> None:
    query, message = validate(
        raw, Catalog(reference_analysis()), {"group_evolution:Product:Laptop"}
    )
    assert query is None and message is not None and reason in message


def test_validation_uses_the_plan_measure_never_the_proposed_one() -> None:
    query, reason = validate(
        RawProposal(kind="group_evolution", dimension="Region", group="Norte"),
        Catalog(reference_analysis()),
        set(),
    )
    assert reason is None and query is not None
    assert query.measure == "Revenue" and query.key == "group_evolution:Region:Norte"


# --- Seguimientos: recálculo independiente ----------------------------------------------------


def test_change_by_group_matches_an_independent_recalculation() -> None:
    (result,) = followups(
        [FollowUpQuery(kind="change_by_group", measure="Revenue", dimension="Product", year=2024)]
    )
    present = {month(row) for row in ROWS}
    comparable = {m for m in present if m.startswith("2024") and f"2023{m[4:]}" in present}
    diff: dict[str, Decimal] = defaultdict(Decimal)
    for row in ROWS:
        key = month(row)
        if key in comparable:
            diff[row[4]] += Decimal(row[8])
        elif key.startswith("2023") and f"2024{key[4:]}" in comparable:
            diff[row[4]] -= Decimal(row[8])
    total = sum(diff.values())
    assert figure(result, "Variación de Revenue 2024 frente a 2023 (meses comparables)") == total
    top = max(diff, key=lambda g: (abs(diff[g]), g))
    assert figure(result, f"Variación de Product = {top}") == diff[top]
    share = figure(result, f"Aporte de {top} a la variación")
    assert abs(share - diff[top] * 100 / total) <= Decimal("0.05")
    assert result.insight and "2024-07" not in result.insight.coverage


def test_month_by_group_points_to_the_outlier_product() -> None:
    (result,) = followups(
        [
            FollowUpQuery(
                kind="month_by_group", measure="Revenue", dimension="Product", month="2024-10"
            )
        ]
    )
    assert result.status == "computed" and result.insight is not None
    assert result.insight.statement.startswith(
        "En 2024-10, el mayor desvío de Revenue por Product es Monitor:"
    )
    monitor: dict[str, Decimal] = defaultdict(Decimal)
    for row in ROWS:
        if row[4] == "Monitor":
            monitor[month(row)] += Decimal(row[8])
    values = sorted(monitor.values())
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    shift = figure(result, "Desvío de Product = Monitor frente a su mediana mensual")
    assert abs(shift - (monitor["2024-10"] - median)) <= Decimal("0.005")
    assert "no una causa" in " ".join(result.insight.notes)


def test_group_evolution_and_empty_results_are_explicit() -> None:
    evolution, empty = followups(
        [
            FollowUpQuery(
                kind="group_evolution", measure="Revenue", dimension="Product", group="Laptop"
            ),
            FollowUpQuery(
                kind="month_by_group", measure="Revenue", dimension="Product", month="2024-07"
            ),
        ]
    )
    laptop = sum(Decimal(row[8]) for row in ROWS if row[4] == "Laptop")
    total = sum(Decimal(row[8]) for row in ROWS)
    share = figure(evolution, "Participación de Laptop en Revenue del periodo")
    assert abs(share - laptop * 100 / total) <= Decimal("0.05")
    assert empty.status == "empty" and empty.insight is None
    assert empty.reason == "Ningún grupo de Product tiene datos en 2024-07."


# --- Ciclo acotado --------------------------------------------------------------------------


def test_without_ai_only_rules_run_and_nothing_is_explained() -> None:
    engine = Engine()
    result = Investigator(engine, None, None, InvestigationLimits(), clock(), "disabled").run(
        reference_analysis(), INVESTIGATION
    )
    assert result.ai == "unavailable" and result.stopped == "ai_unavailable"
    assert result.iterations == 1 and len(engine.calls) == 1
    assert {p.origin for p in result.proposals} == {"rule"}
    assert all(r.status == "computed" for r in result.results)
    assert result.explanation_state == "unavailable" and result.calls == []


def test_ai_proposals_are_validated_and_the_cycle_stops_when_nothing_is_new() -> None:
    def reply(context: ProposalContext) -> list[RawProposal]:
        if context.iteration > 2:
            return []
        return [
            RawProposal(kind="group_evolution", dimension="Region", group="Norte", motive="m"),
            RawProposal(kind="group_evolution", dimension="Customer", group="C003", motive="m"),
        ]

    proposer, explainer = Proposer(reply), Explainer()
    result = Investigator(Engine(), proposer, explainer, InvestigationLimits(), clock()).run(
        reference_analysis(), INVESTIGATION
    )
    ai = [p for p in result.proposals if p.origin == "ai"]
    assert [(p.status, p.key) for p in ai] == [
        ("accepted", "group_evolution:Region:Norte"),
        ("rejected", None),
    ]
    assert result.stopped == "no_new_proposals" and result.iterations == 3
    assert [c.purpose for c in result.calls] == ["proposal", "proposal", "explanation"]
    assert result.consumption.ai_calls == 3 and result.consumption.cost_usd == "0.003"
    # La IA sólo ve el catálogo y los textos; las cifras citables las elige Python.
    assert "group_evolution:Region:Norte" in proposer.contexts[1].done
    keys = {f.evidence_id for f in explainer.figures}
    computed = {e.evidence_id for r in result.results for e in r.evidence}
    assert keys & computed
    assert len(explainer.figures) <= 64


@pytest.mark.parametrize(
    ("limits", "cost", "stopped"),
    [
        (InvestigationLimits(max_ai_calls=0), "0.001", "max_ai_calls"),
        (InvestigationLimits(max_cost_usd="0.001"), "0.002", "max_cost"),
        (InvestigationLimits(max_iterations=2), "0.001", "max_iterations"),
        (InvestigationLimits(max_queries=5), "0.001", "max_queries"),
    ],
)
def test_every_limit_stops_the_cycle(limits: InvestigationLimits, cost: str, stopped: str) -> None:
    def reply(context: ProposalContext) -> list[RawProposal]:
        group = ["Norte", "Sur", "Este", "Oeste"][context.iteration - 2]
        return [RawProposal(kind="group_evolution", dimension="Region", group=group, motive="m")]

    result = Investigator(Engine(), Proposer(reply, cost), Explainer(), limits, clock()).run(
        reference_analysis(), INVESTIGATION
    )
    assert result.stopped == stopped
    assert result.consumption.ai_calls <= limits.max_ai_calls
    assert len(result.results) <= limits.max_queries


def test_time_limit_stops_the_cycle() -> None:
    ticks = iter([0.0, 0.0, 120.0, 120.0, 120.0, 120.0, 120.0])
    result = Investigator(
        Engine(),
        Proposer(lambda _: []),
        Explainer(),
        InvestigationLimits(),
        lambda: next(ticks, 120.0),
    ).run(reference_analysis(), INVESTIGATION)
    assert result.stopped == "max_seconds" and result.calls == []
    assert result.explanation_state == "unavailable" and result.explanation_reason == "max_seconds"


def test_provider_error_keeps_rule_results() -> None:
    class Failing:
        def propose(self, context: ProposalContext) -> ProposalReply:
            return ProposalReply(proposals=[], call=call("proposal", 2), error="AI_UNAVAILABLE")

    result = Investigator(Engine(), Failing(), Explainer(), InvestigationLimits(), clock()).run(
        reference_analysis(), INVESTIGATION
    )
    assert result.stopped == "ai_error" and len(result.results) == 5


# --- De extremo a extremo -------------------------------------------------------------------


def test_new_loads_no_longer_run_the_follow_up(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fase 27 (ADR-045): el seguimiento de hallazgos ya no se encola en las cargas nuevas; el
    informe parte del dashboard y la IA redacta su narrativa. Las reglas y el ciclo de este
    módulo (pruebas de arriba) siguen para leer las versiones anteriores."""
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    while make_runner(db, objects).run_once():
        pass
    path = f"/api/v1/versions/{version['id']}/investigation"
    assert client.get(path).json()["code"] == "INVESTIGATION_NOT_AVAILABLE"
    assert client.get(f"/api/v1/versions/{version['id']}/report").json()["state"] == "ready"
    # Ya no se encola la explicación del dashboard para esta carga.
    audit = client.get(f"/api/v1/versions/{version['id']}/overview-audit").json()
    assert audit["state"] == "unavailable"
    tasks = db.scalars(select(AICallRecord.task)).all()
    assert sorted(set(tasks)) == [
        "business_comprehension",
        "dashboard_design",
        "exploration_proposal",
        "exploration_relevance",
        "report_narrative",
    ]
