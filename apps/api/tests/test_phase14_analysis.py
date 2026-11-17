"""Fase 14A: interpretación analítica (automatic-interpretation-v2), dashboard por medidas
(automatic-overview-v3) y calidad con análisis afectados (automatic-quality-v1).

Aceptación con el dataset sintético `reference_sales` y casos donde lo correcto es abstenerse.
"""

from decimal import Decimal

from fastapi.testclient import TestClient
from reference_sales import HEADER, reference_csv, reference_rows
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.quality.public import assess
from dataflow.modules.understanding.contracts import (
    AnalyticalInterpretation,
    DatasetProfile,
    profile_json,
)
from dataflow.modules.understanding.public import (
    analytical_overview,
    analyze,
    automatic_overview,
    interpret,
    profile_rows,
)


def profile_of(headers: list[str], rows: list[list[str | None]]) -> DatasetProfile:
    return DatasetProfile(
        engine_version="test",
        polars_version="test",
        source_sha256="0" * 64,
        separator=",",
        row_count=len(rows),
        column_count=len(headers),
        columns=profile_rows(headers, rows),
    )


def interpret_rows(
    headers: list[str], rows: list[list[str | None]]
) -> tuple[DatasetProfile, AnalyticalInterpretation]:
    profile = profile_of(headers, rows)
    return profile, analyze(profile, rows)


def reference() -> tuple[DatasetProfile, AnalyticalInterpretation, list[list[str | None]]]:
    rows: list[list[str | None]] = [list(row) for row in reference_rows()]
    profile, analysis = interpret_rows(HEADER, rows)
    return profile, analysis, rows


def test_reference_interpretation_recognizes_period_context_and_relationships() -> None:
    _, analysis, rows = reference()
    roles = {column.name: column for column in analysis.columns}
    assert analysis.context == "sales"
    assert roles["Year"].role == "time" and roles["Year"].time_part == "year"
    assert roles["Month"].role == "time" and roles["Month"].time_part == "month"
    assert roles["Customer"].role == "identifier"
    assert {roles[name].role for name in ["Customer_Name", "Product", "Region"]} == {"dimension"}
    assert roles["Units_Sold"].additivity == "additive"
    assert roles["Units_Sold"].unit_label == "unidades"
    assert roles["Price_per_Unit"].additivity == "non_additive"
    assert roles["Revenue"].additivity == "additive" and roles["Revenue"].monetary
    # La moneda no figura en los datos: no se inventa.
    assert roles["Revenue"].currency == "unknown" and roles["Revenue"].currency_code is None
    assert analysis.time is not None
    assert analysis.time.kind == "year_month"
    assert (analysis.time.first, analysis.time.last) == ("2023-01", "2024-12")
    assert analysis.time.missing == ["2024-07"] and analysis.time.periods == 23
    assert analysis.time.years == ["2023", "2024"]
    assert analysis.keys[0].columns == ["Year", "Month", "Customer", "Product"]
    assert analysis.keys[0].unique
    [relationship] = analysis.relationships
    assert relationship.target == "Revenue"
    assert relationship.factors == ["Units_Sold", "Price_per_Unit"]
    assert relationship.matching_rows == relationship.compared_rows == len(rows)
    conflict = next(d for d in analysis.dependencies if d.conflicting_values)
    assert (conflict.determinant, conflict.dependent) == ("Customer", "Customer_Name")
    assert conflict.examples == ["C003: Ana T. / Ana Torres"]
    assert conflict.sample_row_numbers
    assert all(rows[n - 1][3] == "Ana T." for n in conflict.sample_row_numbers)
    [limited] = analysis.limited_analyses
    assert limited.columns == ["Customer", "Customer_Name"]
    assert "Revenue por Product." in analysis.available_analyses
    assert analyze(reference()[0], rows) == analysis  # determinista


def test_reference_dashboard_uses_measures_chronology_and_omits_ambiguous_customers() -> None:
    profile, analysis, rows = reference()
    overview = analytical_overview(profile, rows, analysis)
    assert overview.algorithm == "automatic-overview-v3"
    labels = [kpi.label for kpi in overview.kpis]
    # Año y mes nunca se promedian; el precio no se suma.
    assert not any("Year" in label or "Month" in label for label in labels)
    assert "Total de Price_per_Unit" not in labels
    revenue_total = sum(Decimal(row[8]) for row in reference_rows())
    total = next(kpi for kpi in overview.kpis if kpi.label == "Total de Revenue")
    assert Decimal(total.value) == revenue_total
    assert "Promedio simple de Price_per_Unit (sin ponderar)" in labels
    months = next(chart for chart in overview.charts if chart.id == "time_months")
    assert months.title == "Revenue por mes" and months.measure == "Revenue"
    assert [point.label for point in months.points] == sorted(p.label for p in months.points)
    assert months.points[0].label == "2023-01" and "2024-07" not in {
        point.label for point in months.points
    }
    assert sum(Decimal(point.amount or "0") for point in months.points) == revenue_total
    years = next(chart for chart in overview.charts if chart.id == "time_years")
    assert [point.label for point in years.points] == ["2023", "2024"]
    titles = [chart.title for chart in overview.charts]
    assert "Revenue por Product" in titles
    assert not any("Customer" in title for title in titles)
    assert any("Customer_Name" in text for text in overview.limitations)
    assert any("sin moneda" in text for text in overview.limitations)
    # Frecuencia y volumen no se confunden: el valor es el número de registros del grupo.
    product = next(chart for chart in overview.charts if chart.title == "Revenue por Product")
    assert sum(point.value for point in product.points) == len(rows)


def test_reference_quality_limits_customers_without_blocking_products() -> None:
    _, analysis, rows = reference()
    quality = assess(analysis, rows)
    checks = {finding.check: finding for finding in quality.findings}
    customer = checks["AQ-002"]
    assert customer.severity == "blocking"
    assert customer.columns == ["Customer", "Customer_Name"]
    assert customer.affected_analyses == ["Análisis por Customer o Customer_Name"]
    assert customer.affected_rows == 46
    assert checks["AQ-003"].severity == "warning" and "2024-07" in checks["AQ-003"].evidence[0]
    outliers = [f for f in quality.findings if f.check == "AQ-007"]
    units = next(f for f in outliers if f.columns == ["Units_Sold"])
    assert units.severity == "info" and units.affected_rows == 1
    assert rows[units.sample_row_numbers[0] - 1][6] == "400"
    assert "AQ-006" not in checks  # Revenue = Units × Price en todas las filas
    assert not any("Product" in a for f in quality.findings for a in f.affected_analyses)
    assert quality.blocking == 1


def test_abstains_without_evidence() -> None:
    # Sin nombres reconocibles: ninguna medida se suma ni se promedia como importe.
    _, analysis = interpret_rows(["codigo", "valor"], [["A1", "5"], ["A2", "7"], ["A3", "9"]])
    roles = {c.name: c for c in analysis.columns}
    assert roles["codigo"].role == "identifier"
    assert roles["valor"].additivity == "unknown" and not roles["valor"].monetary
    assert analysis.context == "generic" and analysis.time is None
    profile = profile_of(["codigo", "valor"], [["A1", "5"], ["A2", "7"], ["A3", "9"]])
    overview = analytical_overview(profile, [["A1", "5"], ["A2", "7"], ["A3", "9"]], analysis)
    assert not any(kpi.label.startswith("Total") for kpi in overview.kpis)
    assert any("eje temporal" in text for text in analysis.limitations)


def test_mixed_currencies_block_monetary_totals() -> None:
    rows: list[list[str | None]] = [
        ["2024-01-05", "Norte", "100.00", "USD"],
        ["2024-01-06", "Sur", "300.00", "PEN"],
        ["2024-02-01", "Norte", "50.00", "USD"],
    ]
    headers = ["fecha", "region", "importe", "moneda"]
    profile, analysis = interpret_rows(headers, rows)
    importe = next(c for c in analysis.columns if c.name == "importe")
    assert importe.currency == "ambiguous"
    overview = analytical_overview(profile, rows, analysis)
    assert not any(kpi.label.startswith("Total de importe") for kpi in overview.kpis)
    quality = assess(analysis, rows)
    assert any(f.check == "AQ-008" and f.severity == "blocking" for f in quality.findings)


def test_single_currency_is_known_and_dates_build_the_time_axis() -> None:
    rows: list[list[str | None]] = [
        ["2024-01-05", "10.00", "PEN"],
        ["2024-03-06", "30.00", "PEN"],
    ]
    _, analysis = interpret_rows(["fecha", "ventas", "moneda"], rows)
    ventas = next(c for c in analysis.columns if c.name == "ventas")
    assert (ventas.currency, ventas.currency_code) == ("known", "PEN")
    assert analysis.time is not None and analysis.time.kind == "date"
    assert analysis.time.missing == ["2024-02"]
    assert analysis.context == "sales"


def test_spanish_months_stock_and_negative_quantities() -> None:
    rows: list[list[str | None]] = [
        ["2024", "Enero", "P1", "10", "4"],
        ["2024", "Febrero", "P1", "8", "-2"],
        ["2024", "Marzo", "P1", "6", "3"],
    ]
    headers = ["Año", "Mes", "Producto", "Stock", "Cantidad"]
    _, analysis = interpret_rows(headers, rows)
    roles = {c.name: c for c in analysis.columns}
    assert roles["Año"].time_part == "year" and roles["Mes"].time_part == "month"
    assert roles["Stock"].additivity == "semi_additive"
    assert analysis.time is not None and analysis.time.missing == []
    quality = assess(analysis, rows)
    negative = next(f for f in quality.findings if f.check == "AQ-006")
    assert negative.columns == ["Cantidad"] and negative.sample_row_numbers == [2]


def test_unparsed_periods_and_broken_relationships_are_reported() -> None:
    rows: list[list[str | None]] = [
        ["2024", "January", "2", "10.00", "20.00"],
        ["2024", "February", "3", "10.00", "30.00"],
        ["2024", "March", "4", "10.00", "40.00"],
        ["2024", "April", "5", "10.00", "50.00"],
        ["2024", "May", "6", "10.00", "60.00"],
        ["2024", "June", "7", "10.00", "70.00"],
        ["2024", "July", "8", "10.00", "80.00"],
        ["2024", "August", "9", "10.00", "90.00"],
        ["2024", "September", "10", "10.00", "100.00"],
        ["2024", "October", "11", "10.00", "110.00"],
        ["2024", "November", "12", "10.00", "120.00"],
        ["2024", "December", "13", "10.00", "130.00"],
        ["2024", "December", "14", "10.00", "130.00"],
        ["2024", "December", "15", "10.00", "150.00"],
        ["2024", "December", "16", "10.00", "160.00"],
        ["2024", "December", "17", "10.00", "170.00"],
        ["2024", "December", "18", "10.00", "180.00"],
        ["2024", "December", "19", "10.00", "190.00"],
        ["2024", "December", "20", "10.00", "200.00"],
        ["2024", "December", "21", "10.00", "210.00"],
        ["2024", "December", "22", "10.00", "220.00"],
    ]
    headers = ["Year", "Month", "Units", "Price", "Revenue"]
    _, analysis = interpret_rows(headers, rows)
    [relationship] = analysis.relationships
    assert relationship.compared_rows - relationship.matching_rows == 1
    assert relationship.exception_sample_rows == [13]
    quality = assess(analysis, rows)
    broken = next(f for f in quality.findings if f.check == "AQ-006")
    assert broken.sample_row_numbers == [13]


def test_previous_versions_keep_their_serialization() -> None:
    rows = [["Norte", "10"], ["Sur", "20"], ["Norte", "30"]]
    profile = profile_of(["region", "importe"], rows)
    profile.overview = automatic_overview(profile, rows, [("string", {})] * 2, interpret(profile))
    v3 = profile_json(profile, 3)
    assert '"analysis"' not in v3 and '"amount"' not in v3 and '"measure"' not in v3
    assert '"interpretation"' in v3
    v2 = profile_json(profile, 2)
    assert '"interpretation"' not in v2 and '"analysis"' not in v2
    report = QualityReport(
        row_count=1,
        cell_count=1,
        missing_cells=0,
        duplicate_rows=0,
        whitespace_cells=0,
        completeness_percent=100.0,
        issues=[],
    )
    assert '"analytical"' not in report.serialized(1)


def test_reference_import_publishes_analysis_and_quality_findings(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    while make_runner(db, objects).run_once():
        pass
    diagnostic = client.get(f"/api/v1/versions/{version['id']}/diagnostic").json()
    overview = diagnostic["profile"]["overview"]
    assert overview["algorithm"] == "automatic-overview-v3"
    assert overview["analysis"]["context"] == "sales"
    assert overview["analysis"]["time"]["missing"] == ["2024-07"]
    analytical = diagnostic["quality"]["analytical"]
    assert analytical["rules_version"] == "automatic-quality-v1"
    assert any(
        finding["check"] == "AQ-002" and finding["severity"] == "blocking"
        for finding in analytical["findings"]
    )
    run = client.get(f"/api/v1/executions/{version['execution_id']}").json()
    steps = {(step["operation"], step["version"]) for step in run["plan"]["content"]["steps"]}
    assert ("understanding.profile", 4) in steps and ("quality.evaluate", 3) in steps


def test_rows_without_a_full_period_are_reported_not_guessed() -> None:
    rows: list[list[str | None]] = [
        ["2024", "1", "10"],
        ["2024", None, "20"],
        ["2024", "3", "30"],
    ]
    _, analysis = interpret_rows(["year", "month", "units"], rows)
    assert analysis.time is not None
    assert analysis.time.unparsed_rows == 1 and analysis.time.unparsed_sample_rows == [2]
    quality = assess(analysis, rows)
    unparsed = next(f for f in quality.findings if f.check == "AQ-005")
    assert unparsed.sample_row_numbers == [2]
    assert unparsed.affected_analyses == ["Evolución mensual", "Comparación entre periodos"]
