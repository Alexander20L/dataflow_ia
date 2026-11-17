"""Fase 15: plan analítico automático (automatic-plan-v1) y analytics.automatic@1.

Las cifras del dataset sintético se recalculan aquí de forma independiente (Decimal, sin el
motor) y se comparan con tolerancias explícitas.
"""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from reference_sales import HEADER, MONTHS, reference_csv, reference_rows
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.analytics.automatic import run_automatic
from dataflow.modules.analytics.contracts import AutomaticAnalysis, AutomaticScope
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.planning.public import AnalysisPlan, plan_analyses
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import analyze, profile_rows, row_periods

SCOPE = AutomaticScope(
    execution_id=UUID("00000000-0000-0000-0000-000000000015"),
    step_id="analysis",
    version_id=UUID("00000000-0000-0000-0000-000000000016"),
    table_sha256="a" * 64,
)


def run(headers: list[str], rows: list[list[str | None]]) -> tuple[AnalysisPlan, AutomaticAnalysis]:
    columns = profile_rows(headers, rows)
    profile = DatasetProfile(
        engine_version="test",
        polars_version="test",
        source_sha256="0" * 64,
        separator=",",
        row_count=len(rows),
        column_count=len(headers),
        columns=columns,
    )
    interpretation = analyze(profile, rows)
    plan = plan_analyses(interpretation, {c.name: c.unique_count for c in columns}, len(rows))
    _, periods = row_periods(interpretation.columns, rows)
    return plan, run_automatic(rows, periods, interpretation, plan, SCOPE)


def reference() -> tuple[list[list[str]], AnalysisPlan, AutomaticAnalysis]:
    rows = reference_rows()
    plan, result = run(HEADER, [list(row) for row in rows])
    return rows, plan, result


def insight(result: AutomaticAnalysis, identifier: str):  # type: ignore[no-untyped-def]
    return next(item for item in result.insights if item.id == identifier)


def figure(item, name: str):  # type: ignore[no-untyped-def]
    return next(f for f in item.figures if f.label == name)


def month_key(row: list[str]) -> str:
    return f"{row[0]}-{MONTHS.index(row[1]) + 1:02d}"


def test_reference_plan_prioritizes_time_and_products_and_explains_omissions() -> None:
    _, plan, _ = reference()
    assert plan.rules_version == "automatic-plan-v1" and plan.measure == "Revenue"
    assert [item.id for item in plan.accepted] == [
        "evolution",
        "weighted:Price_per_Unit",
        "year_over_year",
        "anomalies",
        "breakdown:Product",
        "breakdown:Region",
    ]
    omitted = {item.id: item.reason for item in plan.omitted}
    assert "Customer_Name" in omitted["breakdown:Customer"]
    assert "24 meses seguidos" in omitted["seasonality"]
    assert plan.estimated_cells == 276 * 6


def test_reference_figures_match_an_independent_recalculation() -> None:
    rows, _, result = reference()
    revenue: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        revenue[month_key(row)] += Decimal(row[8])
    # Evolución: el último mes y el máximo.
    evolution = insight(result, "evolution:summary")
    assert Decimal(figure(evolution, "Revenue en 2024-12").value) == revenue["2024-12"]
    peak = max(revenue, key=lambda k: revenue[k])
    assert peak == "2024-10"
    assert Decimal(figure(evolution, "Mes con mayor Revenue").value) == revenue[peak]
    assert [p.label for p in evolution.chart.points] == sorted(revenue)
    # Interanual: sólo los meses de 2024 con dato en 2023 (julio falta en 2024).
    comparable = [m for m in revenue if m.startswith("2024")]
    assert len(comparable) == 11 and "2024-07" not in comparable
    current = sum(revenue[m] for m in comparable)
    base = sum(revenue[f"2023{m[4:]}"] for m in comparable)
    yoy = insight(result, "year_over_year:2024")
    assert Decimal(figure(yoy, "Revenue 2024 (meses comparables)").value) == current
    assert Decimal(figure(yoy, "Revenue 2023 (mismos meses)").value) == base
    expected = (current - base) * 100 / base
    assert abs(Decimal(figure(yoy, "Variación 2024 frente a 2023").value) - expected) <= Decimal(
        "0.05"
    )
    # Participación y concentración por producto.
    by_product: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        by_product[row[4]] += Decimal(row[8])
    total = sum(by_product.values())
    products = insight(result, "breakdown:Product:summary")
    laptop = figure(products, "Participación de Laptop en Revenue")
    assert abs(Decimal(laptop.value) - by_product["Laptop"] * 100 / total) <= Decimal("0.005")
    hhi = sum((value * 100 / total) ** 2 for value in by_product.values())
    measured = Decimal(figure(products, "Índice de concentración (HHI) por Product").value)
    assert abs(measured - hhi) <= Decimal("0.5")
    assert products.statement.startswith("Laptop concentra el 62,00 % de Revenue")
    # Precio medio ponderado = Σ Revenue ÷ Σ Units_Sold.
    weighted = insight(result, "weighted:Price_per_Unit:summary")
    exact = sum(Decimal(r[8]) for r in rows) / sum(Decimal(r[6]) for r in rows)
    value = Decimal(figure(weighted, "Price_per_Unit medio ponderado").value)
    assert abs(value - exact) <= Decimal("0.005")


def test_reference_anomaly_is_associated_not_caused() -> None:
    _, _, result = reference()
    anomalies = [item for item in result.insights if item.kind == "anomalies"]
    assert [item.id for item in anomalies] == ["anomalies:2024-10"]
    statement = anomalies[0].statement
    assert "Product = Monitor" in statement and "Region = Norte" in statement
    assert "no una causa" in " ".join(anomalies[0].notes)
    assert "causa" not in statement


def test_every_figure_has_evidence_and_the_result_is_deterministic() -> None:
    _, _, first = reference()
    _, _, second = reference()
    assert first == second
    known = {item.evidence_id for item in first.evidence}
    for item in first.insights:
        assert {f.evidence_id for f in item.figures} <= known
    assert first.insights == sorted(first.insights, key=lambda i: (-i.importance, i.id))
    assert all(len(e) == 64 for e in known)


def test_abstains_when_requirements_are_not_met() -> None:
    # Un solo año y pocos meses: sin comparación interanual ni anomalías.
    rows: list[list[str | None]] = [
        ["2024", "January", "A", "10"],
        ["2024", "February", "B", "20"],
        ["2024", "March", "A", "30"],
    ]
    plan, result = run(["Year", "Month", "Product", "Revenue"], rows)
    omitted = {item.id: item.reason for item in plan.omitted}
    assert "year_over_year" in omitted and "anomalies" in omitted
    assert "No hay meses presentes" in omitted["year_over_year"]
    assert any(item.kind == "evolution" for item in result.insights)
    # Varias monedas: nada se suma ni se compara.
    rows = [
        ["2024-01-05", "Norte", "100.00", "USD"],
        ["2024-02-06", "Sur", "300.00", "PEN"],
    ]
    plan, result = run(["fecha", "region", "importe", "moneda"], rows)
    assert plan.measure is None and plan.accepted == []
    assert "medida sumable" in {item.id: item.reason for item in plan.omitted}["evolution"]
    assert result.insights == []
    # Sin eje temporal: no hay evolución.
    plan, _ = run(["Product", "Units"], [["A", "1"], ["B", "2"], ["A", "3"]])
    assert "No hay fecha" in {item.id: item.reason for item in plan.omitted}["evolution"]


def test_seasonality_with_two_full_years() -> None:
    rows: list[list[str | None]] = []
    for year in ("2023", "2024"):
        for index, month in enumerate(MONTHS):
            rows.append([year, month, "A", str(100 + (50 if month == "December" else index))])
    plan, result = run(["Year", "Month", "Product", "Revenue"], rows)
    assert "seasonality" in {item.id for item in plan.accepted}
    season = insight(result, "seasonality:summary")
    assert season.statement.startswith("El mes 12 suele estar en")


def test_breakdowns_are_bounded() -> None:
    headers = ["Region", "Canal", "Tienda", "Categoria", "Zona", "Revenue"]
    rows: list[list[str | None]] = [
        [f"R{i % 3}", f"C{i % 2}", f"T{i % 4}", f"K{i % 3}", f"Z{i % 2}", str(i + 1)]
        for i in range(12)
    ]
    plan, _ = run(headers, rows)
    accepted = [item for item in plan.accepted if item.kind == "breakdown"]
    assert len(accepted) == 4
    assert any("Se priorizaron" in item.reason for item in plan.omitted)


def test_import_publishes_automatic_analysis_with_evidence(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    while make_runner(db, objects).run_once():
        pass
    path = f"/api/v1/versions/{version['id']}/automatic-analysis"
    response = client.get(path)
    assert response.status_code == 200, response.text
    analysis = response.json()
    assert analysis["operation"] == "analytics.automatic@1"
    assert analysis["plan"]["measure"] == "Revenue"
    assert analysis["insights"][0]["id"] == "evolution:summary"
    evidence_id = analysis["insights"][0]["figures"][0]["evidence_id"]
    evidence = client.get(f"{path}/evidence/{evidence_id}")
    assert evidence.status_code == 200 and evidence.json()["evidence_id"] == evidence_id
    assert client.get(f"{path}/evidence/{'0' * 64}").json()["code"] == "EVIDENCE_NOT_FOUND"
    assert client.get(f"{path}/evidence/nope").status_code == 422
    run_view = client.get(f"/api/v1/executions/{version['execution_id']}").json()
    steps = [step["operation"] for step in run_view["plan"]["content"]["steps"]]
    assert steps[-1] == "analytics.automatic"
    account(client)
    assert client.get(path).status_code == 404
