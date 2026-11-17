"""Fase 26 (ADR-044): pestaña Dashboard con `dashboard-design-v2`.

Criterios de la especificación: visualizaciones temporales cuando hay periodo, comparaciones
adecuadas para categorías, distribuciones y relaciones para medidas, gráficos legibles con
pocas o muchas categorías, indicadores verificables (unidad sólo declarada, comparación sólo con
base válida), filtros que recalculan exactamente lo que depende de ellos, origen de cada
gráfico, personalización que no destruye la versión automática y ningún gráfico inventado
cuando no hay hallazgos suficientes.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase25_investigation import comprehension, table

from dataflow.bootstrap.services import make_runner
from dataflow.modules.comprehension.contracts import Association, Comprehension, MeasureInfo
from dataflow.modules.curation.contracts import (
    CustomSection,
    CustomWidget,
    DashboardCustomization,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.contracts import DashboardFilterRequest, FilterOptions
from dataflow.modules.delivery.dashboard import (
    build_indicators,
    catalog_v2,
    check_filters,
    current_layout,
    dashboard_plan,
    filter_options,
    layout_errors,
    partial_notice,
    reference_label,
    result_item,
    rules_design_v2,
    sufficiency_notice,
)
from dataflow.modules.exploration.contracts import (
    Exploration,
    ExplorationLimits,
    ExplorationScope,
    ExploreQuery,
    ExploreResult,
)
from dataflow.modules.exploration.engine import compute, subset
from dataflow.platform.config import get_settings

PERIOD = ("year_month", ["Year", "Month"])


def empty_exploration(stopped: str | None = None) -> Exploration:
    return Exploration(
        rules_version="investigation-v2",
        operation="exploration.explore@2",
        scope=ExplorationScope(
            execution_id=uuid4(), version_id=uuid4(), comprehension_sha256="c", table_sha256="t"
        ),
        limits=ExplorationLimits(),
        ai_state="unavailable",
        proposals=[],
        results=[],
        limitations=[],
        stopped=stopped,  # type: ignore[arg-type]
    )


def computed(found: Comprehension, content: bytes) -> dict[str, ExploreResult]:
    period = PERIOD if found.period else None
    results: dict[str, ExploreResult] = {}
    for query in dashboard_plan(found).queries():
        result = compute(content, query, "d", period)
        if isinstance(result, ExploreResult):
            results[query.key] = result
    return results


def with_association(found: Comprehension) -> Comprehension:
    return found.model_copy(
        update={
            "associations": [
                Association(
                    columns=("Revenue", "Units"),
                    measure="spearman",
                    value="0.5",
                    strength="moderate",
                    rows=48,
                    method="Spearman",
                )
            ]
        }
    )


# --- Visualizaciones adaptadas -------------------------------------------------------------------


def test_temporal_categorical_and_numeric_datasets_get_fitting_visualizations() -> None:
    found = with_association(comprehension())
    content = table()
    results = computed(found, content)
    plan = dashboard_plan(found)
    indicators = build_indicators(found, plan, results, 48, "2024-01 a 2024-08", [])
    items = catalog_v2([], {}, empty_exploration(), list(results.values()), indicators, 48, [])
    kinds = {item.kind: item for item in items}
    # Temporal: la evolución mensual va en líneas, en orden cronológico.
    assert "line" in kinds["evolution"].widgets
    evolution = results[plan.evolution.key]  # type: ignore[union-attr]
    assert [r.groups[0] for r in evolution.rows] == [f"2024-0{m}" for m in range(1, 9)]
    # Numérico: histograma de cada medida y dispersión de las asociadas.
    assert "histogram" in kinds["distribution"].widgets
    assert kinds["scatter"].widgets == ["scatter", "table"]
    histogram = results[plan.distributions[0].key]
    assert sum(r.rows for r in histogram.rows) == 48  # todos los valores, en algún intervalo
    # Sin periodo no hay evolución ni comparación: no se inventan análisis temporales.
    flat = comprehension(period=False)
    flat_plan = dashboard_plan(flat)
    assert flat_plan.evolution is None and flat_plan.changes == {}
    flat_indicators = build_indicators(
        flat, flat_plan, computed(flat, content), 48, "Todo el dataset", []
    )
    assert all(i.comparison is None for i in flat_indicators)
    assert not any(i.name.startswith("Mes con") for i in flat_indicators)
    # Las secciones van por importancia: indicadores, evolución y distribuciones.
    sections = rules_design_v2([], items, indicators)
    assert [s.title for s in sections] == [
        "Indicadores clave",
        "Evolución",
        "Distribuciones y relaciones",
    ]


def test_few_and_many_categories_stay_readable() -> None:
    rows = {"Grupo": [f"G{i:02d}" for i in range(80)], "Valor": [str(i + 1) for i in range(80)]}
    buffer = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buffer)
    content = buffer.getvalue()
    many = compute(
        content,
        ExploreQuery(kind="aggregate", measure="Valor", aggregation="sum", dimensions=["Grupo"]),
        "x",
    )
    assert isinstance(many, ExploreResult)
    item = result_item(many)
    # 80 categorías: barras y tabla, nunca un circular saturado.
    assert "pie" not in item.widgets and "bar" in item.widgets and item.groups == 80
    small = pl.DataFrame({"Grupo": ["A", "B", "C"], "Valor": ["1", "2", "3"]})
    buffer = io.BytesIO()
    small.write_parquet(buffer)
    three = compute(
        buffer.getvalue(),
        ExploreQuery(kind="aggregate", measure="Valor", aggregation="sum", dimensions=["Grupo"]),
        "x",
    )
    assert isinstance(three, ExploreResult)
    assert "pie" in result_item(three).widgets


# --- Indicadores -------------------------------------------------------------------------------


def test_indicators_are_verifiable_and_do_not_invent_units() -> None:
    found = comprehension()
    content = table()
    results = computed(found, content)
    plan = dashboard_plan(found)
    indicators = build_indicators(found, plan, results, 48, "2024-01 a 2024-08", [])
    by_name = {i.name: i for i in indicators}
    # Cada cifra es la de una evidencia del motor.
    evidence = {
        f.evidence_id: f.value for r in results.values() for row in r.rows for f in row.figures
    }
    for indicator in indicators:
        assert evidence[indicator.evidence_id] == indicator.value
        assert indicator.trace.method and indicator.trace.rows is not None
        assert indicator.reference == "2024-01 a 2024-08"
    revenue = by_name["Suma de Revenue"]
    expected = sum(
        Decimal(v) for v in pl.read_parquet(io.BytesIO(content)).get_column("Revenue").to_list()
    )
    assert Decimal(revenue.value or "0") == expected
    # Revenue es monetaria pero sin unidad declarada: no se inventa una moneda.
    assert revenue.unit is None
    # La comparación es la del último mes frente al anterior, con sus cifras.
    assert revenue.comparison is not None and revenue.comparison.label == "2024-08 frente a 2024-07"
    change = Decimal(revenue.comparison.current or "0") - Decimal(
        revenue.comparison.previous or "0"
    )
    assert Decimal(revenue.comparison.change or "0") == change
    # El Sur suma más por el valor atípico de agosto (5000).
    assert by_name["Region con mayor suma de Revenue"].highlight == "Sur"
    assert by_name["Mes con mayor suma de Revenue"].highlight == "2024-08"
    # Con la unidad declarada en la comprensión, se muestra.
    declared = found.model_copy(
        update={
            "measures": [
                MeasureInfo(
                    column="Revenue",
                    additivity="additive",
                    aggregation="sum",
                    unit="PEN",
                    monetary=True,
                    reason="",
                )
            ]
        }
    )
    plan = dashboard_plan(declared)
    again = build_indicators(declared, plan, computed(declared, content), 48, "x", [])
    assert next(i for i in again if i.name == "Suma de Revenue").unit == "PEN"


def test_without_enough_findings_nothing_is_invented_and_partial_is_flagged() -> None:
    assert sufficiency_notice([]) is not None
    found = comprehension()
    results = computed(found, table())
    plan = dashboard_plan(found)
    indicators = build_indicators(found, plan, results, 48, "x", [])
    items = catalog_v2([], {}, empty_exploration(), list(results.values()), indicators, 48, [])
    assert {i.origin for i in items} == {"computed"}
    assert "No hay hallazgos suficientes" in (sufficiency_notice(items) or "")
    assert partial_notice(empty_exploration("paused")) is not None
    assert partial_notice(empty_exploration("completed")) is None


# --- Filtros ------------------------------------------------------------------------------------


def test_filters_recompute_exactly_on_the_subset() -> None:
    content = table()
    filtered, rows, total = subset(content, PERIOD, "2024-07", "2024-08", {"Region": ["Norte"]})
    assert (rows, total) == (6, 48)
    query = ExploreQuery(kind="aggregate", measure="Revenue", aggregation="sum")
    result = compute(filtered, query, "f", PERIOD)
    assert isinstance(result, ExploreResult)
    # Norte, julio y agosto: 100 + 40·6 + i y 100 + 40·7 + i, i = 0..2.
    expected = sum(100 + 40 * m + i for m in (6, 7) for i in range(3))
    assert result.rows[0].figures[0].value == str(expected)
    options = filter_options(
        comprehension(), dashboard_plan(comprehension()), computed(comprehension(), content)
    )
    assert options.months[0] == "2024-01" and options.dimensions[0].column == "Region"
    request = DashboardFilterRequest(period_from="2024-07", period_to="2024-08")
    assert check_filters(request, options) is None
    assert reference_label(request, options.months) == "2024-07 a 2024-08"
    assert check_filters(
        DashboardFilterRequest(period_from="2024-08", period_to="2024-01"), options
    )
    assert check_filters(DashboardFilterRequest(period_from="2024-01"), FilterOptions())


# --- Personalización ------------------------------------------------------------------------------


def test_custom_layout_is_validated_and_survives_a_new_dashboard() -> None:
    found = comprehension()
    results = computed(found, table())
    plan = dashboard_plan(found)
    indicators = build_indicators(found, plan, results, 48, "x", [])
    items = catalog_v2([], {}, empty_exploration(), list(results.values()), indicators, 48, [])
    kpi = indicators[1]
    evolution = next(i for i in items if i.kind == "evolution")
    good = [
        CustomSection(
            title="Lo que miro",
            widgets=[
                CustomWidget(item=kpi.item, type="kpi", evidence_id=kpi.evidence_id, title="Mío"),
                CustomWidget(item=evolution.id, type="line"),
            ],
        )
    ]
    assert layout_errors(good, items) == []
    bad = [
        CustomSection(
            title="Mal",
            widgets=[
                CustomWidget(item="computed:inventado", type="bar"),
                CustomWidget(item=evolution.id, type="pie"),
                CustomWidget(item=kpi.item, type="kpi", evidence_id="otra"),
            ],
        )
    ]
    assert len(layout_errors(bad, items)) == 3
    custom = DashboardCustomization(
        revision=1,
        dashboard_execution_id=uuid4(),
        sections=good + bad,
        created_at=datetime(2026, 11, 12, tzinfo=UTC),
    )
    kept, dropped = current_layout(custom, items)
    assert kept is not None and [s.title for s in kept.sections] == ["Lo que miro"]
    assert dropped == 3


# --- Recorrido por la API --------------------------------------------------------------------


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def test_upload_gets_a_traceable_dashboard_with_filters_and_custom_version(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{version['id']}"
    run_all(db, objects)
    view = client.get(f"{base}/dashboard").json()
    assert view["state"] == "ready", view
    designed = view["dashboard"]
    assert designed["rules_version"] == "dashboard-design-v2"
    assert designed["operation"] == "delivery.dashboard@2"
    rows = len(list(csv.DictReader(io.StringIO(reference_csv().decode("utf-8-sig")))))
    assert designed["total_rows"] == rows
    # Cada elemento tiene un origen identificable.
    for item in designed["items"]:
        trace = item["trace"]
        assert (
            trace
            and trace["method"]
            and trace["source"]
            in {
                "investigation",
                "analysis",
                "dashboard",
            }
        )
        if item["origin"] == "exploration":
            assert trace["investigation"] and trace["question"]
    indicators = designed["indicators"]
    assert indicators and indicators[0]["name"] == "Registros"
    assert indicators[0]["value"] == str(rows)
    options = designed["filters"]
    assert options["months"] and options["dimensions"]

    # Filtros: periodo y una categoría; los elementos de la investigación y del dashboard se
    # recalculan, los hallazgos del análisis automático dicen que muestran el dataset completo.
    dimension = options["dimensions"][0]
    request = {
        "period_from": options["months"][-3],
        "period_to": options["months"][-1],
        "categories": [{"column": dimension["column"], "values": dimension["values"][:1]}],
    }
    filtered = client.post(f"{base}/dashboard/filter", json=request, headers=headers)
    assert filtered.status_code == 200, filtered.json()
    result = filtered.json()
    assert 0 < result["rows"] < rows and result["total_rows"] == rows
    assert len(result["filters"]) == 2
    count = next(i for i in result["indicators"] if i["name"] == "Registros")
    assert count["value"] == str(result["rows"])
    assert count["trace"]["filters"] == result["filters"]
    by_item = {i["item"]: i for i in result["items"]}
    assert set(by_item) == {i["id"] for i in designed["items"]}
    for item in designed["items"]:
        found = by_item[item["id"]]
        if item["origin"] == "insight":
            assert found["result"] is None and "dataset completo" in found["reason"]
        else:
            assert found["result"] is not None or found["reason"]
    invalid = client.post(
        f"{base}/dashboard/filter",
        json={"categories": [{"column": "No existe", "values": ["x"]}]},
        headers=headers,
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "DASHBOARD_FILTER_INVALID"

    # Personalización: se guarda como revisión y la automática no cambia.
    kpi = indicators[0]
    layout = {
        "expected_revision": 0,
        "sections": [
            {
                "title": "Lo que miro",
                "widgets": [
                    {
                        "item": kpi["item"],
                        "type": "kpi",
                        "evidence_id": kpi["evidence_id"],
                        "title": "Filas del mes",
                    }
                ],
            }
        ],
    }
    # La versión automática tal cual (con todas sus secciones) también se puede guardar.
    whole = {
        "expected_revision": 0,
        "sections": [
            {
                "title": section["title"],
                "widgets": [
                    {
                        "item": w["item"],
                        "type": w["type"],
                        "evidence_id": w.get("evidence_id"),
                        "title": w["title"],
                    }
                    for w in section["widgets"]
                ],
            }
            for section in view["arrangement"]["sections"]
        ],
    }
    assert sum(len(s["widgets"]) for s in whole["sections"]) > 0
    first = client.post(f"{base}/dashboard/custom", json=whole, headers=headers)
    assert first.status_code == 200, first.json()
    assert first.json()["custom"]["revision"] == 1
    layout["expected_revision"] = 1
    saved = client.post(f"{base}/dashboard/custom", json=layout, headers=headers)
    assert saved.status_code == 200, saved.json()
    custom = saved.json()
    assert custom["custom"]["revision"] == 2
    assert custom["dashboard"]["sections"] == designed["sections"]
    stale = client.post(f"{base}/dashboard/custom", json=layout, headers=headers)
    assert stale.status_code == 409 and stale.json()["code"] == "DASHBOARD_REVISION_CONFLICT"
    layout["expected_revision"] = 2
    layout["sections"][0]["widgets"][0]["type"] = "pie"  # type: ignore[index]
    wrong = client.post(f"{base}/dashboard/custom", json=layout, headers=headers)
    assert wrong.status_code == 422 and wrong.json()["code"] == "DASHBOARD_LAYOUT_INVALID"
    again = client.get(f"{base}/dashboard").json()
    assert again["custom"]["sections"][0]["widgets"][0]["title"] == "Filas del mes"
    assert again["dashboard"] == designed
    account(client)
    assert client.get(f"{base}/dashboard").status_code == 404
