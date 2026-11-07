"""Fase 11E: analytics.query@3 (motor, sin base de datos).

`sum_product` (Σ medida × segunda medida por fila, exacta, escala = suma de escalas) y la medida
semi-aditiva `last_snapshot` (último corte de cada periodo, común a todos los grupos; nunca se
suman cortes de fechas distintas). Con las métricas de @2, @3 calcula lo mismo que @2; @1 y @2
rechazan las métricas nuevas.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_analytics_comparisons import params, scope_for
from test_analytics_query_v1_golden import CASES, COLUMNS, HEADERS, ROWS, TABLE

from dataflow.modules.analytics.application import addressed_cells, content_sha256
from dataflow.modules.analytics.contracts import (
    MetricContent,
    MetricReference,
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
    product_unit,
)
from dataflow.modules.analytics.engine import (
    Metric,
    evidence_reference,
    run_query,
    run_query_v2,
    run_query_v3,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

D = Decimal


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


INV = {"producto": uid(201), "bodega": uid(202), "corte": uid(203)}
INV |= {"cantidad": uid(204), "costo": uid(205)}
INV_COLUMNS: list[dict[str, Any]] = [
    {"id": INV["producto"], "name": "producto", "technical_type": "string", "type_parameters": {}},
    {"id": INV["bodega"], "name": "bodega", "technical_type": "string", "type_parameters": {}},
    {"id": INV["corte"], "name": "corte", "technical_type": "date", "type_parameters": {}},
    {"id": INV["cantidad"], "name": "cantidad", "technical_type": "integer", "type_parameters": {}},
    {
        "id": INV["costo"],
        "name": "costo",
        "technical_type": "decimal",
        "type_parameters": {"precision": 12, "scale": 3},
    },
]
INV_HEADERS = [str(c["name"]) for c in INV_COLUMNS]
JAN15, JAN31, FEB28 = date(2026, 1, 15), date(2026, 1, 31), date(2026, 2, 28)
STOCK: list[list[Any]] = [
    ["A", "B1", JAN15, 10, D("2.500")],
    ["B", "B1", JAN15, 4, D("1.250")],
    ["D", "B1", JAN15, 3, D("1.000")],  # sólo en el primer corte de enero
    ["A", "B1", JAN31, 8, D("2.500")],
    ["B", "B2", JAN31, 6, D("1.300")],
    ["C", "B1", JAN31, None, D("9.000")],  # cantidad nula: excluida y contada
    ["A", "B1", FEB28, 5, D("2.600")],
    ["A", "B1", None, 100, D("1.000")],  # sin fecha: no pertenece a ningún corte
]


def inventory_metric(number: int, aggregation: str, **extra: Any) -> Metric:
    content = MetricContent.model_validate(
        {
            "label": f"{aggregation} {number}",
            "measure_column_id": INV["cantidad"],
            "aggregation": aggregation,
            "time_column_id": INV["corte"],
            "base_table": TABLE.model_dump(mode="json"),
            **extra,
        }
    )
    reference = MetricReference(
        revision_id=UUID(uid(400 + number)), content_sha256=content_sha256(content)
    )
    return Metric(reference, 1, content)


QTY_LAST = inventory_metric(1, "sum", semi_additive="last_snapshot")
VALUE_LAST = inventory_metric(
    2, "sum_product", second_measure_column_id=INV["costo"], semi_additive="last_snapshot"
)
VALUE = inventory_metric(3, "sum_product", second_measure_column_id=INV["costo"])
SQUARES = inventory_metric(4, "sum_product", second_measure_column_id=INV["cantidad"])
COST_SQUARED = inventory_metric(
    5, "sum_product", measure_column_id=INV["costo"], second_measure_column_id=INV["costo"]
)


def query3(
    metrics: list[Metric],
    rows: list[list[Any]] = STOCK,
    headers: list[str] = INV_HEADERS,
    columns: list[dict[str, Any]] = INV_COLUMNS,
    **parameters: Any,
) -> Any:
    p = params(QueryParametersV3, metrics, **parameters)
    return run_query_v3(headers, rows, columns, metrics, p, scope_for(p))


def values(result: Any, key: str = "m0") -> list[tuple[Any, ...]]:
    return [(*r.labels.values(), r.values[key]) for r in result.rows]


# --- sum_product --------------------------------------------------------------------------


def test_sum_product_is_exact_with_the_sum_of_scales() -> None:
    result = query3([VALUE, SQUARES, COST_SQUARED])
    # 25 + 5 + 3 + 20 + 7.8 + 13 + 100 (la fila sin fecha cuenta: no es un corte).
    assert result.rows[0].values == {"m0": "173.800", "m1": "10250", "m2": "105.512500"}
    scales = [(m.aggregation, m.scale, m.second_measure_column) for m in result.metrics]
    assert scales == [
        ("sum_product", 3, "costo"),  # entero × decimal(3)
        ("sum_product", None, "cantidad"),  # entero × entero: entero
        ("sum_product", 6, "costo"),  # decimal(3) × decimal(3)
    ]
    counts = result.metrics[0].counts
    # La fila de C tiene cantidad nula: un nulo en cualquiera de las medidas la excluye.
    assert (counts.input_rows, counts.excluded_by_nulls, counts.included_rows) == (8, 1, 7)
    assert result.metrics[2].counts.excluded_by_nulls == 0  # costo × costo no tiene nulos


def test_sum_product_null_in_the_second_measure_is_excluded_and_counted() -> None:
    rows = [["A", "B1", JAN15, 2, None], ["A", "B1", JAN15, 3, D("1.500")]]
    result = query3([VALUE], rows)
    assert result.rows[0].values["m0"] == "4.500"
    assert result.metrics[0].counts.excluded_by_nulls == 1


BIG_COLUMNS: list[dict[str, Any]] = [
    {"id": uid(301), "name": "a", "technical_type": "decimal", "type_parameters": {"scale": 0}},
    {"id": uid(302), "name": "b", "technical_type": "integer", "type_parameters": {}},
]


def big_metric() -> Metric:
    content = MetricContent.model_validate(
        {
            "label": "Producto grande",
            "measure_column_id": uid(301),
            "aggregation": "sum_product",
            "second_measure_column_id": uid(302),
            "base_table": TABLE.model_dump(mode="json"),
        }
    )
    return Metric(MetricReference(revision_id=UUID(uid(499)), content_sha256="e" * 64), 1, content)


def test_sum_product_beyond_python_default_precision_is_exact() -> None:
    # 30 dígitos × 3 (más de los 28 del contexto por defecto de Python).
    value = D("123456789012345678901234567890")
    result = query3([big_metric()], [[value, 3], [value, 1]], ["a", "b"], BIG_COLUMNS)
    assert result.rows[0].values["m0"] == "493827156049382715604938271560"


def test_sum_product_above_38_digits_is_an_explicit_error() -> None:
    huge = D(10) ** 37
    with pytest.raises(ApplicationError) as error:
        query3([big_metric()], [[huge, 10**3]], ["a", "b"], BIG_COLUMNS)
    assert error.value.code == "RESULT_PRECISION_EXCEEDED"


# --- last_snapshot ------------------------------------------------------------------------


def test_last_snapshot_takes_the_last_cut_of_each_period() -> None:
    result = query3([QTY_LAST, VALUE_LAST], time_grain="month")
    assert [(*r.labels.values(), r.values["m0"], r.values["m1"]) for r in result.rows] == [
        ("2026-01", "14", "27.800"),  # 31 de enero: 8 + 6 (el 15 de enero no se suma)
        ("2026-02", "5", "13.000"),
    ]
    assert [r.snapshots for r in result.rows] == [
        {"m0": "2026-01-31", "m1": "2026-01-31"},
        {"m0": "2026-02-28", "m1": "2026-02-28"},
    ]
    qty = result.metrics[0]
    assert qty.semi_additive == "last_snapshot"
    assert qty.counts.model_dump() == {
        "input_rows": 8,
        "excluded_by_filters": 0,
        "excluded_by_nulls": 2,  # cantidad nula y fila sin fecha
        "included_rows": 6,
    }
    assert qty.snapshot is not None and qty.snapshot.superseded_rows == 3  # filas del 15 de enero
    # Sin agrupar por tiempo: un único corte, el último de todo el resultado.
    whole = query3([QTY_LAST, VALUE_LAST])
    assert whole.rows[0].values == {"m0": "5", "m1": "13.000"}
    assert whole.rows[0].snapshots == {"m0": "2026-02-28", "m1": "2026-02-28"}


def test_last_snapshot_cut_is_common_to_the_groups_of_a_period() -> None:
    """Los grupos se suman dentro del mismo corte; un grupo sin filas en el corte vale nulo
    (nunca 0) y la suma de los grupos coincide con el total sin dimensiones."""
    by_product = query3([QTY_LAST], time_grain="month", dimensions=[INV["producto"]])
    assert values(by_product) == [
        ("A", "2026-01", "8"),
        ("A", "2026-02", "5"),
        ("B", "2026-01", "6"),
        ("D", "2026-01", None),  # sólo estaba en el corte del 15: sin filas en el último
    ]
    by_store = query3([QTY_LAST], time_grain="month", dimensions=[INV["bodega"]])
    assert values(by_store) == [
        ("B1", "2026-01", "8"),
        ("B1", "2026-02", "5"),
        ("B2", "2026-01", "6"),
    ]
    total = query3([QTY_LAST], time_grain="month")
    for result in (by_product, by_store):
        for period, expected in (("2026-01", "14"), ("2026-02", "5")):
            summed = sum(
                (
                    D(r.values["m0"])
                    for r in result.rows
                    if r.labels["period"] == period and r.values["m0"] is not None
                ),
                D(0),
            )
            assert str(summed) == expected
    assert [r.values["m0"] for r in total.rows] == ["14", "5"]


def test_last_snapshot_never_sums_dates_even_with_filters_and_range() -> None:
    result = query3(
        [QTY_LAST],
        time_range={"start": "2026-01-01", "end": "2026-01-20"},
        filters=[{"column_id": INV["producto"], "operator": "neq", "values": ["D"]}],
    )
    # Dentro del rango, el último corte es el 15 de enero: 10 + 4 (D filtrado), nunca 10 + 8.
    assert result.rows[0].values["m0"] == "14"
    assert result.rows[0].snapshots == {"m0": "2026-01-15"}


def test_last_snapshot_with_comparisons_uses_the_last_cut_of_the_base_period() -> None:
    result = query3(
        [QTY_LAST],
        time_grain="month",
        time_range={"start": "2026-02-01", "end": "2026-02-28"},
        comparisons=["previous_period"],
    )
    cell = result.rows[0].comparisons["m0"]["previous_period"]
    assert (result.rows[0].values["m0"], cell.base, cell.change, cell.change_pct) == (
        "5",
        "14",
        "-9",
        "-64.29",
    )
    snapshot = result.metrics[0].snapshot
    assert snapshot is not None
    assert snapshot.base_superseded_rows == {"previous_period": 3}


def test_share_of_total_accepts_sum_product_in_v3() -> None:
    result = query3(
        [VALUE_LAST],
        time_grain="month",
        time_range={"start": "2026-01-01", "end": "2026-01-31"},
        dimensions=[INV["producto"]],
        share_of_total=[str(VALUE_LAST.reference.revision_id)],
    )
    shares = [(r.labels["d0"], r.values["m0"], r.share["m0"].value) for r in result.rows]
    assert shares == [("A", "20.000", "71.94"), ("B", "7.800", "28.06"), ("D", None, None)]
    assert result.shares[0].total == "27.800"


def test_v3_cells_keep_the_value_evidence_formula_and_resolve() -> None:
    result = query3([VALUE_LAST], time_grain="month", dimensions=[INV["producto"]])
    for row in result.rows:
        assert row.evidence["m0"] == evidence_reference(result.scope, VALUE_LAST, row.key)[0]
        assert [c.name for c in addressed_cells(result, row)] == ["value"]


# --- Compatibilidad --------------------------------------------------------------------------

V3_ONLY_DEFINITION = {"second_measure_column_id", "second_measure_column", "semi_additive"}


def without_v3(dump: dict[str, Any]) -> dict[str, Any]:
    dump = {k: v for k, v in dump.items() if k not in {"operation", "schema_version"}}
    dump["metrics"] = [
        {k: v for k, v in m.items() if k not in V3_ONLY_DEFINITION | {"snapshot"}}
        for m in dump["metrics"]
    ]
    dump["rows"] = [{k: v for k, v in r.items() if k != "snapshots"} for r in dump["rows"]]
    return dump


@pytest.mark.parametrize("name", sorted(CASES))
def test_v3_with_v2_metrics_computes_the_same_as_v2(name: str) -> None:
    metrics, parameters = CASES[name]
    p2 = params(QueryParametersV2, metrics, **parameters)
    p3 = params(QueryParametersV3, metrics, **parameters)
    v2 = run_query_v2(HEADERS, ROWS, COLUMNS, metrics, p2, scope_for(p2))
    v3 = run_query_v3(HEADERS, ROWS, COLUMNS, metrics, p3, scope_for(p3))
    assert v3.operation == "analytics.query@3"
    assert without_v3(v3.model_dump(mode="json")) == without_v3(v2.model_dump(mode="json"))
    assert all(m.snapshot is None and m.semi_additive is None for m in v3.metrics)


def test_v1_and_v2_reject_metrics_that_only_v3_computes() -> None:
    for model, runner in ((QueryParameters, run_query), (QueryParametersV2, run_query_v2)):
        for metric in (VALUE, QTY_LAST):
            p = params(model, [metric])
            with pytest.raises(ApplicationError) as error:
                runner(INV_HEADERS, STOCK, INV_COLUMNS, [metric], p, scope_for(p))  # type: ignore[operator]
            assert error.value.code == "METRIC_UNSUPPORTED"


BASE = {
    "label": "Inventario",
    "measure_column_id": INV["cantidad"],
    "base_table": TABLE.model_dump(mode="json"),
}


@pytest.mark.parametrize(
    "extra",
    [
        {"aggregation": "sum_product"},  # sin segunda medida
        {"aggregation": "sum", "second_measure_column_id": INV["costo"]},
        {"aggregation": "avg", "semi_additive": "last_snapshot", "time_column_id": INV["corte"]},
        {"aggregation": "count", "semi_additive": "last_snapshot", "time_column_id": INV["corte"]},
        {"aggregation": "sum", "semi_additive": "last_snapshot"},  # sin fecha de corte
    ],
)
def test_metric_draft_rejects_inconsistent_v3_fields(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MetricContent.model_validate({**BASE, **extra})


def test_metrics_saved_before_11e_keep_their_hash() -> None:
    """Los campos nuevos quedan fuera del hash cuando no se usan: el contenido sometido a hash
    de una métrica anterior es exactamente el de antes."""
    content = MetricContent.model_validate({**BASE, "aggregation": "sum"})
    before = {k: v for k, v in content.model_dump(mode="json").items()}
    before.pop("second_measure_column_id")
    before.pop("semi_additive")
    assert content_sha256(content) == digest("analytics_metric", before)
    assert set(content.hashed()) == {
        "label",
        "description",
        "measure_column_id",
        "aggregation",
        "filters",
        "time_column_id",
        "null_policy",
        "schema_version",
        "base_table",
    }
    used = MetricContent.model_validate(
        {**BASE, "aggregation": "sum_product", "second_measure_column_id": INV["costo"]}
    )
    assert used.hashed()["second_measure_column_id"] == INV["costo"]
    assert "semi_additive" not in used.hashed()
    assert content.requires_query_v3 is False
    assert used.requires_query_v3 is True


def test_product_unit() -> None:
    assert product_unit(("kg", None), (None, "COP")) == (None, "COP")
    assert product_unit((None, "COP"), ("kg", None)) == (None, "COP")
    assert product_unit(("kg", None), ("m", None)) == ("kg×m", None)
    assert product_unit(("kg", None), (None, None)) == ("kg", None)
    assert product_unit((None, None), (None, None)) == (None, None)
    assert product_unit((None, "COP"), (None, "USD")) is None
