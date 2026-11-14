"""Fase 29: analista con objetivo (ADR-047).

- Estadística en Python puro contra valores de referencia conocidos.
- `explore-v4`: el objetivo por cada factor (con intervalo y prueba) y la comprobación con una
  variable de control (se mantiene / se explica por ella), con variables derivadas.
- `relevance-v3`: sin significancia no hay hallazgo; corrección de Benjamini-Hochberg.
- `business-comprehension-v5`: objetivo por reglas, por la IA o elegido por el usuario
  (heredado por la siguiente carga) y variables derivadas.
- IA obligatoria: sin IA activa no se arranca si se pide.
"""

import io
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase28_criteria import get, run_all

from dataflow.modules.comprehension.contracts import (
    DatedAttribute,
    DimensionInfo,
    MeasureInfo,
    TargetChoice,
)
from dataflow.modules.comprehension.domain import analysis_target, derived_variables
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.exploration import statistics as stats
from dataflow.modules.exploration.contracts import ExploreQuery
from dataflow.modules.exploration.engine import compute
from dataflow.platform.config import Settings

# --- Estadística ---------------------------------------------------------------------------------


def test_distributions_match_reference_values() -> None:
    assert math.isclose(stats.chi2_sf(3.841458820694124, 1), 0.05, abs_tol=1e-9)
    assert math.isclose(stats.chi2_sf(11.070497693516351, 5), 0.05, abs_tol=1e-9)
    assert math.isclose(stats.t_quantile(0.975, 9), 2.262157, abs_tol=1e-5)
    assert math.isclose(stats.t_quantile(0.975, 29), 2.045230, abs_tol=1e-5)
    low, high = stats.wilson(9, 100)
    assert math.isclose(low, 0.0481, abs_tol=1e-4) and math.isclose(high, 0.1623, abs_tol=1e-4)
    mean, low, high = stats.mean_interval([1, 2, 3, 4, 5])  # type: ignore[misc]
    assert mean == 3 and math.isclose(high - mean, 1.963243, abs_tol=1e-5)


def test_tests_and_multiple_comparisons() -> None:
    # Kruskal-Wallis de tres grupos separados: H = 9,846 (p = 0,0073).
    h, df, p, _ = stats.kruskal_wallis([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]])  # type: ignore[misc]
    assert (
        df == 2
        and math.isclose(h, 9.846154, abs_tol=1e-5)
        and math.isclose(p, 0.0072767, abs_tol=1e-6)
    )
    # 25 % frente a 5 % con 20 personas por grupo no es significativo (p ≈ 0,099).
    found = stats.chi_square([(5, 15), (1, 19), (1, 19), (1, 19), (1, 19)])
    assert found is not None and math.isclose(found[2], 0.098618, abs_tol=1e-5)
    assert stats.chi_square([(0, 10), (0, 12)]) is None  # sin variación
    assert stats.benjamini_hochberg([0.01, 0.04, 0.03, 0.2]) == pytest.approx(
        [0.04, 0.0533333, 0.0533333, 0.2]
    )
    assert stats.p_text(0.0004) == "p < 0,001" and stats.p_text(0.0321) == "p = 0,032"


# --- Objetivo y variables derivadas (reglas puras) ----------------------------------------------


def dimension(column: str, distinct: int) -> DimensionInfo:
    return DimensionInfo(column=column, distinct=distinct, groupable=True, reason="r")


def measure(column: str, monetary: bool = False) -> MeasureInfo:
    return MeasureInfo(
        column=column, additivity="additive", aggregation="sum", monetary=monetary, reason="r"
    )


def test_the_target_comes_from_the_user_the_ai_or_the_rules() -> None:
    dims = [dimension("area", 5), dimension("activo", 2), dimension("sexo", 2)]
    measures = [measure("horas"), measure("salario", monetary=True)]
    by_rules = analysis_target(dims, measures, None, None)
    assert by_rules is not None and (by_rules.column, by_rules.kind) == ("activo", "rate")
    assert by_rules.origin == "rules"
    by_ai = analysis_target(dims, measures, ("salario", "Es lo que se quiere mejorar."), None)
    assert by_ai is not None and (by_ai.column, by_ai.kind, by_ai.origin) == (
        "salario",
        "measure",
        "ai",
    )
    chosen = TargetChoice(column="sexo", value="F")
    by_user = analysis_target(dims, measures, ("salario", "m"), chosen)
    assert by_user is not None and (by_user.column, by_user.value, by_user.origin) == (
        "sexo",
        "F",
        "user",
    )
    # Una elección que ya no es válida (columna con más de dos valores) no se usa.
    invalid = analysis_target(dims, measures, None, TargetChoice(column="area"))
    assert invalid is not None and invalid.origin == "rules"
    # Sin columna de resultado, la medida principal (monetaria primero).
    plain = analysis_target([dimension("area", 5)], measures, None, None)
    assert plain is not None and (plain.column, plain.kind) == ("salario", "measure")


def test_derived_variables() -> None:
    dated = [DatedAttribute(column="ingreso", first=None, last=None, per_year=[], reason="r")]
    target = analysis_target([dimension("activo", 2)], [measure("salario")], None, None)
    found = derived_variables(
        dated,
        [measure("salario"), measure("horas"), measure("bono")],
        target,
        [("cuartiles", "bono"), ("antiguedad", "salario")],
    )
    names = [(d.name, d.origin) for d in found]
    assert names == [
        ("antigüedad de ingreso", "rules"),
        ("cuartil de salario", "rules"),
        ("cuartil de horas", "rules"),
        ("cuartil de bono", "ai"),
    ]


# --- Motor: factores y comprobaciones -----------------------------------------------------------


def parquet(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buffer)
    return buffer.getvalue()


AREAS = ["Comercial", "Finanzas", "Logística", "Marketing", "Ventas"]
REFERENCE = date(2025, 12, 31)


def roster_rows() -> list[dict[str, Any]]:
    """300 empleados, 60 por área. Los que llevan menos de un año se van mucho más (un tercio);
    Ventas tiene la mitad de su gente recién contratada (por eso parece tener más bajas) y
    Marketing tiene más bajas también entre los antiguos (30 % frente a 5 %)."""
    rows = []
    for i in range(300):
        area, k = AREAS[i // 60], i % 60
        newbie = k < (30 if area == "Ventas" else 10)
        days = 30 + (k * 11) % 300 + 3 * (i // 60) if newbie else 400 + 23 * i
        if newbie:
            left = k % 3 == 0
        else:
            left = (k % 10 < 3) if area == "Marketing" else (k % 20 == 0)
        rows.append(
            {
                "empleado_id": f"E{i:03d}",
                "area": area,
                "fecha_ingreso": (REFERENCE - timedelta(days=days)).isoformat(),
                "salario": 3000 + 37 * k,
                "activo": "No" if left else "Sí",
            }
        )
    return rows


def test_a_factor_has_intervals_and_a_test() -> None:
    content = parquet(roster_rows())
    tenure = compute(
        content,
        ExploreQuery(kind="factor", target="activo", dimensions=["antigüedad de fecha_ingreso"]),
        "e",
    )
    assert not isinstance(tenure, str) and tenure.test is not None
    first = tenure.rows[0]
    assert first.groups == ["Menos de 1 año"] and first.rows == 70
    share, low, high, cases = (Decimal(f.value or "0") for f in first.figures)
    assert cases == 26 and share == Decimal("37.14") and low < share < high
    assert tenure.test.name == "chi_square" and float(tenure.test.p_value) < 0.001
    salary = compute(
        content, ExploreQuery(kind="factor", measure="salario", dimensions=["area"]), "e"
    )
    assert not isinstance(salary, str) and salary.test is not None
    assert salary.test.name == "kruskal_wallis" and float(salary.test.p_value) > 0.05


def test_a_difference_explained_by_another_variable() -> None:
    """Ventas tiene más bajas sólo porque tiene más gente nueva: al descontar la antigüedad, su
    diferencia desaparece. Con una diferencia que es del área, se mantiene."""
    rows = []
    for i in range(200):
        area = "Ventas" if i < 100 else "Finanzas"
        newbie = i % 100 < (60 if area == "Ventas" else 10)
        rows.append(
            {
                "area": area,
                "ingreso": (REFERENCE - timedelta(days=100 if newbie else 1500 + i)).isoformat(),
                "activo": "No" if (i % 10 < (4 if newbie else 1)) else "Sí",
            }
        )
    explained = compute(
        parquet(rows),
        ExploreQuery(
            kind="stratified", target="activo", dimensions=["area", "antigüedad de ingreso"]
        ),
        "e",
    )
    assert not isinstance(explained, str) and explained.control is not None
    assert explained.control.verdict == "explained"
    holds = compute(
        parquet(roster_rows()),
        ExploreQuery(
            kind="stratified", target="activo", dimensions=["area", "antigüedad de fecha_ingreso"]
        ),
        "e",
    )
    assert not isinstance(holds, str) and holds.control is not None
    assert holds.control.verdict == "holds"
    observed = {row.groups[0]: row.figures for row in holds.rows}
    # Ventas: lo observado está por debajo de lo esperado por su composición.
    assert Decimal(observed["Ventas"][0].value or "0") < Decimal(observed["Ventas"][1].value or "0")


# --- Recorrido completo -------------------------------------------------------------------------


def roster() -> bytes:
    header = "empleado_id,area,fecha_ingreso,salario,activo"
    lines = [header] + [
        f"{r['empleado_id']},{r['area']},{r['fecha_ingreso']},{r['salario']},{r['activo']}"
        for r in roster_rows()
    ]
    return ("\n".join(lines) + "\n").encode()


def node_for(exploration: dict[str, Any], kind: str, dimensions: list[str]) -> dict[str, Any]:
    return next(
        n
        for n in exploration["nodes"]
        if n["query"].get("kind") == kind and n["query"].get("dimensions") == dimensions
    )


def test_the_analysis_explains_the_target(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, roster(), name="plantilla.csv").json()["id"]
    run_all(db, objects)
    base = f"/api/v1/versions/{version}"
    understood = get(client, f"{base}/comprehension")["comprehension"]
    assert understood["rules_version"] == "business-comprehension-v5"
    assert understood["target"]["column"] == "activo" and understood["target"]["origin"] == "rules"
    assert "activo" in understood["target_candidates"]
    names = [d["name"] for d in understood["derived"]]
    assert "antigüedad de fecha_ingreso" in names and "cuartil de salario" in names
    explored = get(client, f"{base}/exploration")["exploration"]
    assert explored["rules_version"] == "investigation-v4"
    assert explored["operation"] == "exploration.explore@4"
    results = {r["key"]: r for r in explored["results"]}
    tenure = node_for(explored, "factor", ["antigüedad de fecha_ingreso"])
    assert tenure["classification"] == "relevant"
    test = results[tenure["key"]]["test"]
    assert float(test["p_value"]) < 0.001 and float(test["q_value"]) < 0.05
    assert any(c["name"] == "significance" for c in tenure["criteria"])
    area = node_for(explored, "factor", ["area"])
    assert area["classification"] == "relevant"
    # La diferencia por área se comprueba con la antigüedad (y se mantiene por Marketing).
    check = node_for(explored, "stratified", ["area", "antigüedad de fecha_ingreso"])
    assert check["parent"] == area["id"]
    assert results[check["key"]]["control"]["verdict"] == "holds"
    assert any(c["name"] == "control" for c in area["criteria"])
    # Sin evolución: la fecha describe a cada empleado (Fase 28).
    assert not any(n["query"].get("kind") == "evolution" for n in explored["nodes"])

    # El usuario cambia el objetivo: se rehace la comprensión y la investigación.
    response = client.post(
        f"{base}/comprehension/target", json={"column": "salario"}, headers=headers
    )
    assert response.status_code == 200, response.text
    run_all(db, objects)
    understood = get(client, f"{base}/comprehension")["comprehension"]
    assert understood["target"] == {
        "column": "salario",
        "kind": "measure",
        "value": None,
        "origin": "user",
        "reason": "Elegido por ti.",
    }
    explored = get(client, f"{base}/exploration")["exploration"]
    factor = node_for(explored, "factor", ["area"])
    assert factor["query"]["measure"] == "salario"
    # Una columna que no puede ser objetivo se rechaza.
    wrong = client.post(f"{base}/comprehension/target", json={"column": "area"}, headers=headers)
    assert wrong.status_code == 422 and wrong.json()["code"] == "TARGET_INVALID"
    # La siguiente carga del mismo archivo hereda el objetivo elegido.
    again = upload(client, headers, pid, roster(), name="plantilla.csv").json()["id"]
    run_all(db, objects)
    inherited = get(client, f"/api/v1/versions/{again}/comprehension")["comprehension"]
    assert inherited["target"]["column"] == "salario"
    assert inherited["target"]["origin"] == "user"


def test_ai_can_be_required() -> None:
    Settings(ai_required=False, ai_provider="auto").require_ai()
    Settings(ai_required=True, ai_provider="fake").require_ai()
    with pytest.raises(RuntimeError, match="DATAFLOW_AI_REQUIRED"):
        Settings(ai_required=True, ai_provider="auto", ai_api_key=None).require_ai()
    with pytest.raises(RuntimeError):
        Settings(ai_required=True, ai_provider="disabled").require_ai()
