"""Fase 20: exploración guiada. Consultas del lenguaje cerrado `explore-v1` propuestas por reglas e
IA, validadas por Python, calculadas sobre todas las filas y juzgadas por su relevancia."""

import csv
import io
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.comprehension.contracts import (
    Association,
    Comprehension,
    ComprehensionScope,
)
from dataflow.modules.comprehension.domain import relationships, scales
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.exploration.contracts import ExploreQuery, RawQuery
from dataflow.modules.exploration.domain import Catalog, rule_queries, validate
from dataflow.modules.exploration.engine import compute
from dataflow.platform.config import get_settings


def comprehension(verdicts: dict[str, str] | None = None) -> Comprehension:
    association = Association(
        columns=("Revenue", "Region"),
        measure="eta",
        value="0.6000",
        strength="strong",
        rows=40,
        method="m",
    )
    return Comprehension(
        scope=ComprehensionScope(
            execution_id=uuid4(),
            version_id=uuid4(),
            profile_sha256="p" * 64,
            table_sha256="t" * 64,
        ),
        ai_state="unavailable",
        scales=scales(
            [
                ("Revenue", "measure"),
                ("Price", "measure"),
                ("Units", "measure"),
                ("Region", "dimension"),
                ("Product", "dimension"),
                ("Id", "identifier"),
            ],
            {"Region": ["N", "S"], "Product": ["A", "B"]},
        ),
        associations=[association],
        matrix_columns=["Revenue", "Region"],
        relationships=relationships([], [association], {}, [], verdicts or {}),  # type: ignore[arg-type]
        limitations=[],
    )


def catalog(verdicts: dict[str, str] | None = None) -> Catalog:
    return Catalog(comprehension(verdicts), {"Revenue", "Units"})


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (RawQuery(kind="pivot", dimensions=["Region"]), "no es un tipo"),
        (
            RawQuery(kind="aggregate", measure="Price", dimensions=["Region"], aggregation="sum"),
            "no es aditiva",
        ),
        (RawQuery(kind="crosstab", dimensions=["Region"]), "entre 2 y 2"),
        (
            RawQuery(kind="ratio", measure="Revenue", measure_b="Price"),
            "dos medidas aditivas",
        ),
        (RawQuery(kind="aggregate", dimensions=["Id"], aggregation="count"), "no es una dimensión"),
        (
            RawQuery(
                kind="aggregate",
                dimensions=["Region"],
                aggregation="count",
                filter_column="Region",
                filter_value="N",
            ),
            "otra dimensión",
        ),
        (
            RawQuery(kind="aggregate", measure="Inventada", dimensions=["Region"]),
            "no es una medida",
        ),
    ],
)
def test_invalid_proposals_are_rejected_with_a_reason(raw: RawQuery, reason: str) -> None:
    query, why = validate(raw, catalog(), set())
    assert query is None and why is not None and reason in why


def test_valid_proposals_become_queries_once() -> None:
    raw = RawQuery(kind="aggregate", measure="Revenue", dimensions=["Region"])
    query, why = validate(raw, catalog(), set())
    assert why is None and query is not None and query.aggregation == "sum"
    again, reason = validate(raw, catalog(), {query.key})
    assert again is None and reason == "Ya se exploró."
    top, _ = validate(
        RawQuery(kind="top", measure="Price", dimensions=["Product"], aggregation="mean"),
        catalog(),
        set(),
    )
    assert top is not None and top.limit == 10


def test_rule_queries_follow_confirmed_relationships_and_skip_rejected_ones() -> None:
    found = rule_queries(comprehension(), catalog())
    assert [(q.kind, q.measure, q.dimensions, q.aggregation) for q, _ in found] == [
        ("aggregate", "Revenue", ["Region"], "sum")
    ]
    key = "association:Region|Revenue"
    excluded = catalog({key: "not_relevant"})
    assert rule_queries(comprehension({key: "not_relevant"}), excluded) == []
    rejected, reason = validate(
        RawQuery(kind="aggregate", measure="Revenue", dimensions=["Region"]), excluded, set()
    )
    assert rejected is None and reason and "No relevante" in reason


def table(rows: int = 40) -> bytes:
    buffer = io.BytesIO()
    pl.DataFrame(
        {
            "Region": ["N" if i % 2 else "S" for i in range(rows)],
            "Product": ["A" if i % 4 < 2 else "B" for i in range(rows)],
            "Revenue": [f"{i}.25" for i in range(rows)],
            "Units": [str(i + 1) for i in range(rows)],
            "Price": ["1.5", "2", "2.5", "3"] * (rows // 4),
        }
    ).write_parquet(buffer)
    return buffer.getvalue()


def test_engine_figures_are_exact_and_declare_their_rounding() -> None:
    content = table()
    summed = compute(
        content,
        ExploreQuery(kind="aggregate", measure="Revenue", dimensions=["Region"], aggregation="sum"),
        "x",
    )
    assert not isinstance(summed, str)
    by_group = {r.groups[0]: r.figures[0].value for r in summed.rows}
    expected = defaultdict(Decimal)
    for i in range(40):
        expected["N" if i % 2 else "S"] += Decimal(f"{i}.25")
    assert {k: Decimal(v or "0") for k, v in by_group.items()} == expected
    mean = compute(
        content,
        ExploreQuery(kind="aggregate", measure="Price", dimensions=["Product"], aggregation="mean"),
        "x",
    )
    assert not isinstance(mean, str) and "6 decimales" in mean.method
    ratio = compute(content, ExploreQuery(kind="ratio", measure="Revenue", measure_b="Units"), "x")
    assert not isinstance(ratio, str) and ratio.rows[0].groups == []
    top = compute(
        content,
        ExploreQuery(
            kind="top", measure="Revenue", dimensions=["Product"], aggregation="sum", limit=1
        ),
        "x",
    )
    assert not isinstance(top, str) and len(top.rows) == 1 and top.rows[0].groups == ["B"]
    correlation = compute(
        content,
        ExploreQuery(
            kind="correlation_by_group", measure="Revenue", measure_b="Units", dimensions=["Region"]
        ),
        "x",
    )
    assert not isinstance(correlation, str)
    assert {r.figures[0].value for r in correlation.rows} == {"1"}
    crosstab = compute(
        content,
        ExploreQuery(kind="crosstab", dimensions=["Region", "Product"], aggregation="count"),
        "x",
    )
    assert not isinstance(crosstab, str) and sum(r.rows for r in crosstab.rows) == 40
    missing = compute(
        content,
        ExploreQuery(
            kind="aggregate",
            dimensions=["Region"],
            aggregation="count",
            filter_column="Product",
            filter_value="Z",
        ),
        "x",
    )
    assert missing == "Ningún registro tiene Product = Z."
    # Cada cifra tiene su evidencia estable.
    again = compute(content, summed.query, "x")
    assert not isinstance(again, str)
    assert [f.evidence_id for r in again.rows for f in r.figures] == [
        f.evidence_id for r in summed.rows for f in r.figures
    ]


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def revenue_by(column: str) -> dict[str, str]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in csv.DictReader(io.StringIO(reference_csv().decode("utf-8-sig"))):
        totals[row[column]] += Decimal(row["Revenue"])
    return {k: format(v.normalize() if v == v.to_integral() else v, "f") for k, v in totals.items()}


def test_upload_is_explored_with_the_fake_ai(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}/exploration"
    run_all(db, objects)
    view = client.get(base).json()
    assert view["state"] == "ready", view
    result = view["exploration"]
    assert result["ai_state"] == "ready"
    origins = {(p["origin"], p["status"]) for p in result["proposals"]}
    assert {("rule", "accepted"), ("ai", "accepted"), ("ai", "rejected")} <= origins
    reasons = [p["reason"] for p in result["proposals"] if p["status"] == "rejected"]
    assert any("no es aditiva" in r for r in reasons)
    assert any("Columna inventada" in r for r in reasons)
    judged = [r for r in result["results"] if r["judged_by"] == "ai"]
    assert judged and judged[0]["relevant"] is True
    assert any(r["relevant"] is False for r in judged)
    # Las cifras son las del motor sobre todas las filas.
    summed = next(
        (
            r
            for r in result["results"]
            if r["query"]["kind"] == "aggregate"
            and r["query"]["measure"] == "Revenue"
            and r["query"]["aggregation"] == "sum"
            and len(r["query"]["dimensions"]) == 1
        ),
        None,
    )
    if summed is not None:
        dimension = summed["query"]["dimensions"][0]
        assert {
            row["groups"][0]: row["figures"][0]["value"] for row in summed["rows"]
        } == revenue_by(dimension)
    crosstab = next(r for r in result["results"] if r["query"]["kind"] == "crosstab")
    rows = len(list(csv.DictReader(io.StringIO(reference_csv().decode("utf-8-sig")))))
    assert sum(int(row["figures"][0]["value"]) for row in crosstab["rows"]) == rows
    stages = client.get(f"/api/v1/versions/{version['id']}/progress").json()["stages"]
    assert [s["id"] for s in stages][2] == "exploration" and stages[2]["state"] == "done"
    account(client)
    assert client.get(base).status_code == 404


def test_without_ai_rules_explore_confirmed_relationships(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    result = client.get(f"/api/v1/versions/{version['id']}/exploration").json()["exploration"]
    assert result["ai_state"] == "unavailable"
    assert result["results"] and all(r["judged_by"] == "rules" for r in result["results"])
    assert {p["origin"] for p in result["proposals"]} == {"rule"}


def test_relationships_marked_not_relevant_are_not_explored_next_time(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    first = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    found = client.get(f"/api/v1/versions/{first['id']}/comprehension").json()["comprehension"]
    explored = client.get(f"/api/v1/versions/{first['id']}/exploration").json()["exploration"]
    assert explored["results"]
    target = next(
        r
        for r in found["relationships"]
        if r["status"] == "confirmed" and r["kind"] == "association"
    )
    client.post(
        f"/api/v1/versions/{first['id']}/comprehension/feedback",
        json={"relationship_key": target["key"], "verdict": "not_relevant"},
        headers=headers,
    )
    second = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    again = client.get(f"/api/v1/versions/{second['id']}/exploration").json()["exploration"]
    assert target["key"] in again["excluded"]
    pair = set(target["columns"])
    for proposal in again["proposals"]:
        used = {
            *proposal["query"].get("dimensions", []),
            proposal["query"].get("measure"),
            proposal["query"].get("measure_b"),
        }
        assert not (pair <= used and proposal["status"] == "accepted")


def test_report_shows_relevant_explorations_with_exact_figures() -> None:
    from datetime import UTC, datetime

    from test_phase16_investigation import reference_analysis
    from test_phase17_delivery import investigation, source

    from dataflow.modules.delivery.public import build_report, render_pdf
    from dataflow.modules.exploration.contracts import (
        Exploration,
        ExplorationLimits,
        ExplorationScope,
    )

    computed = compute(
        table(),
        ExploreQuery(kind="aggregate", measure="Revenue", dimensions=["Region"], aggregation="sum"),
        "x",
    )
    assert not isinstance(computed, str)
    exploration = Exploration(
        scope=ExplorationScope(
            execution_id=uuid4(),
            version_id=uuid4(),
            comprehension_sha256="c" * 64,
            table_sha256="t" * 64,
        ),
        limits=ExplorationLimits(),
        ai_state="ready",
        proposals=[],
        results=[
            computed.model_copy(
                update={"relevant": True, "judged_by": "ai", "reason": "Reparto desigual."}
            )
        ],
        limitations=[],
    )
    analysis = reference_analysis()
    result = investigation(analysis)
    document = build_report(
        source(analysis, result),
        analysis,
        result,
        None,
        datetime(2026, 11, 10, tzinfo=UTC),
        None,
        None,
        exploration,
    )
    section = next(s for s in document.sections if s.id == "exploration")
    block = section.blocks[0]
    assert block.title == "Suma de Revenue por Region" and block.badge == "Juzgada por la IA"
    assert block.table is not None and block.table.rows[0][0] in {"N", "S"}
    assert render_pdf(document).startswith(b"%PDF")
