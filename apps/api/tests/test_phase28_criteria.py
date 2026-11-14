"""Fase 28: criterio analítico (ADR-046).

- `date-role-v1`: una fecha que describe al registro (fecha de ingreso) no es una línea de tiempo;
  una serie con una fila por mes, sí.
- `relevance-v2`: en promedios, medianas y tasas, un grupo o mes con menos de 10 registros no
  cuenta para clasificar; una suma o un conteo, sí.
- `explore-v3`: tasa de una columna de dos valores y registros por año; el plan no repite
  consultas equivalentes; el dashboard muestra la tasa como indicador.
- `dataset-inspection-v3`: escalas de valoración y más cantidades no negativas.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase21_dashboard import reference_csv

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.exploration.contracts import (
    ExploreFigure,
    ExploreQuery,
    ExploreResult,
    ExploreRow,
    RawQuery,
)
from dataflow.modules.exploration.plan import magnitude, minimum_for, signature
from dataflow.modules.inspection.domain import domain_kind, rating_scale
from dataflow.platform.timing import date_role

# --- Reglas puras -------------------------------------------------------------------------------


def test_a_date_describes_the_record_or_records_events() -> None:
    # Un padrón (clave por persona) con uno o ningún ingreso por mes: atributo.
    assert date_role(True, [1, 1, 2, 1, 1]) == "attribute"
    # Ventas: muchas filas por mes, aunque haya una clave por pedido.
    assert date_role(True, [40, 52, 38]) == "events"
    # Sin clave de entidad (p. ej. una serie con una fila por mes, cuya clave es el periodo).
    assert date_role(False, [1, 1, 1]) == "events"
    assert date_role(True, []) == "events"


def test_rating_scales_and_more_non_negative_quantities() -> None:
    assert domain_kind("evaluacion_desempeno")[0] == "rating"  # type: ignore[index]
    assert domain_kind("puntaje")[0] == "rating"  # type: ignore[index]
    assert domain_kind("dias_ausencia_anio")[0] == "non_negative"  # type: ignore[index]
    assert domain_kind("nota_final") is None  # una nota de 0 a 20 no es una valoración 1–5
    assert rating_scale(2.3, 5.0) == (1, 5) and rating_scale(0, 4) == (0, 5)
    assert rating_scale(1, 9) == (1, 10) and rating_scale(0, 20) is None


def result(query: ExploreQuery, rows: list[tuple[str, int, str]]) -> ExploreResult:
    return ExploreResult(
        key=query.key,
        query=query,
        title="t",
        method="m",
        columns=["g", "v", "Filas"],
        rows=[
            ExploreRow(
                groups=[g], rows=n, figures=[ExploreFigure(label="v", value=v, evidence_id="e")]
            )
            for g, n, v in rows
        ],
        total_groups=len(rows),
        truncated=False,
        covered_rows=sum(n for _, n, _ in rows),
    )


def test_estimates_need_ten_records_per_group_but_totals_do_not() -> None:
    mean = ExploreQuery(
        kind="aggregate", measure="salario", dimensions=["cargo"], aggregation="mean"
    )
    assert minimum_for(mean) == 10
    small = result(mean, [("Analista", 5, "8238"), ("Jefe", 4, "6772"), ("Asistente", 8, "7457")])
    assert magnitude(mean, small)[0] == "inconclusive"
    enough = result(mean, [("TI", 28, "7624"), ("Logística", 29, "3010")])
    assert magnitude(mean, enough)[0] == "relevant"
    # Una serie de promedios con un registro por mes no es una tendencia.
    trend = ExploreQuery(kind="evolution", measure="salario", aggregation="mean")
    months = result(trend, [(f"2024-{m:02d}", 1, str(1000 * m)) for m in range(1, 7)])
    assert magnitude(trend, months)[0] == "inconclusive"
    # Una suma por mes es un total exacto: cuenta aunque el mes tenga pocas filas.
    total = ExploreQuery(kind="evolution", measure="ventas", aggregation="sum")
    assert minimum_for(total) == 0
    sums = result(total, [(f"2024-{m:02d}", 3, str(100 * m)) for m in range(1, 7)])
    assert magnitude(total, sums)[0] == "relevant"


def test_rates_are_classified_by_points_of_difference() -> None:
    by_area = ExploreQuery(kind="rate", target="activo", dimensions=["area"])
    wide = result(by_area, [("A", 20, "25.00"), ("B", 20, "5.00")])
    wide = wide.model_copy(update={"columns": ["area", "Proporción de «No» (%)", "Casos", "Filas"]})
    classification, text = magnitude(by_area, wide)
    assert classification == "relevant" and "20.00 puntos" in text
    close = wide.model_copy(
        update={
            "rows": [
                r.model_copy(
                    update={"figures": [f.model_copy(update={"value": "6"}) for f in r.figures]}
                )
                for r in wide.rows
            ]
        }
    )
    assert magnitude(by_area, close)[0] == "discarded"
    tiny = result(by_area, [("A", 3, "66.67"), ("B", 4, "0.00")])
    assert magnitude(by_area, tiny)[0] == "inconclusive"


def test_a_ranking_and_an_aggregation_of_the_same_figures_are_one_query() -> None:
    top = RawQuery(kind="top", measure="salario", dimensions=["area"], aggregation="mean", limit=10)
    aggregate = RawQuery(
        kind="aggregate", measure="salario", dimensions=["area"], aggregation="mean"
    )
    assert signature(top) == signature(aggregate)
    other = RawQuery(kind="aggregate", measure="salario", dimensions=["cargo"], aggregation="mean")
    assert signature(top) != signature(other)


# --- Cifras conocidas ---------------------------------------------------------------------------


def employees() -> bytes:
    """100 empleados en 5 áreas de 20; en el área A causan baja 5 (25 %), en las demás 1 (5 %).
    Una fecha de ingreso cada 37 días (casi un ingreso por mes) y una evaluación de 1 a 5."""
    lines = ["empleado_id,area,cargo,fecha_ingreso,salario,evaluacion,dias_ausencia,activo"]
    start = date(2015, 1, 15)
    for i in range(100):
        area = "ABCDE"[i // 20]
        inactive = (i % 20) < (5 if area == "A" else 1)
        lines.append(
            f"E{i:03d},{area},{['Analista', 'Asistente', 'Jefe', 'Supervisor'][i % 4]},"
            f"{(start + timedelta(days=37 * i)).isoformat()},{3000 + 400 * (i % 5) + 7 * i},"
            f"{1 + (i % 9) / 2:.1f},{i % 6},{'No' if inactive else 'Sí'}"
        )
    return ("\n".join(lines) + "\n").encode()


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def get(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_roster_is_not_a_time_series_and_its_rates_are_analysed(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, employees(), name="empleados.csv").json()["id"]
    run_all(db, objects)
    base = f"/api/v1/versions/{version}"
    # Comprensión: sin periodo; la fecha de ingreso describe al empleado.
    understood = get(client, f"{base}/comprehension")["comprehension"]
    assert understood["rules_version"] == "business-comprehension-v5"
    assert understood["period"] is None
    [dated] = understood["dated_attributes"]
    assert dated["column"] == "fecha_ingreso" and sum(n for _, n in dated["per_year"]) == 100
    # Dataset: sin «meses sin registros», con la fecha marcada y la escala reconocida.
    inspection = get(client, f"{base}/inspection")["inspection"]
    assert inspection["scope"]["rules"] == "dataset-inspection-v3"
    assert not any("AQ-003" in f["kind"] for f in inspection["findings"])
    found = {c["name"]: c for c in inspection["columns"]}
    assert found["fecha_ingreso"]["date_role"] == "attribute"
    assert found["evaluacion"]["domain"]["kind"] == "rating"
    assert (found["evaluacion"]["domain"]["lower"], found["evaluacion"]["domain"]["upper"]) == (
        "1",
        "5",
    )
    assert found["dias_ausencia"]["domain"]["kind"] == "non_negative"
    # Investigación: ni evolución ni cambio de periodo; tasa y cohorte con cifras exactas.
    explored = get(client, f"{base}/exploration")["exploration"]
    assert explored["rules_version"] == "investigation-v4"
    kinds = [n["query"]["kind"] for n in explored["nodes"]]
    assert "evolution" not in kinds and "period_change" not in kinds
    results = {r["key"]: r for r in explored["results"]}
    nodes = {n["key"]: n for n in explored["nodes"] if n.get("key")}
    total = next(
        r for r in results.values() if r["query"]["kind"] == "rate" and not r["query"]["dimensions"]
    )
    assert Decimal(total["rows"][0]["figures"][0]["value"]) == 9  # 9 bajas de 100
    assert "«No»" in total["title"]
    by_area = next(
        r
        for r in results.values()
        # Fase 29: con objetivo (activo), su tasa por área es un factor con su prueba.
        if r["query"]["kind"] == "factor" and r["query"]["dimensions"] == ["area"]
    )
    rates = {row["groups"][0]: Decimal(row["figures"][0]["value"]) for row in by_area["rows"]}
    assert rates == {
        "A": Decimal("25.00"),
        "B": Decimal("5.00"),
        "C": Decimal("5.00"),
        "D": Decimal("5.00"),
        "E": Decimal("5.00"),
    }
    # 25 % frente a 5 % con 20 personas por área no es estadísticamente significativo
    # (p ≈ 0,099): desde la Fase 29 (`relevance-v3`) no es un hallazgo sino «no concluyente».
    assert nodes[by_area["key"]]["classification"] == "inconclusive"
    assert float(by_area["test"]["p_value"]) > 0.05
    cohort = next(r for r in results.values() if r["query"]["kind"] == "cohort")
    assert sum(row["rows"] for row in cohort["rows"]) == 100
    assert [row["groups"][0] for row in cohort["rows"]] == sorted(
        row["groups"][0] for row in cohort["rows"]
    )
    # Sin consultas repetidas: un ranking y una agregación de las mismas cifras no se duplican.
    signatures = [
        (
            q["measure"] if "measure" in q else None,
            tuple(q.get("dimensions", [])),
            q.get("aggregation"),
            q.get("target"),
        )
        for q in (
            n["query"]
            for n in explored["nodes"]
            if n["query"]["kind"] in {"aggregate", "top"} and not n.get("parent")
        )
    ]
    assert len(signatures) == len(set(signatures))
    # Dashboard: la tasa como indicador, en %, y ninguno sobre un «mes».
    dashboard = get(client, f"{base}/dashboard")["dashboard"]
    indicators = {i["name"]: i for i in dashboard["indicators"]}
    rate = next(i for name, i in indicators.items() if name.startswith("Proporción de «No»"))
    assert Decimal(rate["value"]) == 9 and rate["unit"] == "%"
    assert not any(name.startswith("Mes con") for name in indicators)


def test_a_monthly_sales_series_is_still_a_time_series(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    understood = get(client, f"/api/v1/versions/{version['id']}/comprehension")["comprehension"]
    assert understood["period"] is not None and understood["dated_attributes"] == []
    explored = get(client, f"/api/v1/versions/{version['id']}/exploration")["exploration"]
    assert "evolution" in {n["query"]["kind"] for n in explored["nodes"]}
