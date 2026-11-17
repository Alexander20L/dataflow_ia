"""Fase 7B · B1: comparaciones de analytics.query@2 (motor, sin base de datos).

Periodo anterior y mismo periodo del año anterior por grupo temporal. El periodo consultado se
calcula igual que en @1; la base es una segunda pasada sin el filtro de periodo, limitada a los
periodos base necesarios. Un periodo sin datos da nulo con indicador, nunca 0.
"""

import random
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_analytics_query_v1_golden import CASES, COLUMNS, HEADERS, IDS, ROWS, SCOPE, TABLE

from dataflow.modules.analytics.contracts import (
    MetricContent,
    MetricReference,
    QueryParameters,
    QueryParametersV2,
)
from dataflow.modules.analytics.engine import (
    Metric,
    cell_reference,
    change_of,
    evidence_reference,
    run_query,
    run_query_v2,
)
from dataflow.modules.analytics.periods import ends_period, shift, starts_period

D = Decimal


def metric(number: int, aggregation: str, column: str, **extra: Any) -> Metric:
    content = MetricContent.model_validate(
        {
            "label": f"{aggregation} {column}",
            "measure_column_id": IDS[column],
            "aggregation": aggregation,
            "time_column_id": IDS["fecha"],
            "base_table": TABLE.model_dump(mode="json"),
            **extra,
        }
    )
    reference = MetricReference(
        revision_id=UUID(f"00000000-0000-4000-8000-{300 + number:012d}"),
        content_sha256="d" * 64,
    )
    return Metric(reference, 1, content)


SUM = metric(1, "sum", "importe")
AVG = metric(2, "avg", "importe")


def row(region: str | None, day: date | None, amount: str | None, client: str = "a") -> list[Any]:
    return [region, day, None if amount is None else D(amount), 1, client]


def params(model: type[QueryParameters], metrics: list[Metric], **parameters: Any) -> Any:
    return model.model_validate(
        {"metrics": [m.reference.model_dump(mode="json") for m in metrics], **parameters}
    )


def scope_for(parameters: QueryParameters) -> Any:
    return SCOPE.model_copy(
        update={
            "query_filters": parameters.filters,
            "time_grain": parameters.time_grain,
            "time_range": parameters.time_range,
        }
    )


def query2(metrics: list[Metric], rows: list[list[Any]], **parameters: Any) -> Any:
    p = params(QueryParametersV2, metrics, **parameters)
    return run_query_v2(HEADERS, rows, COLUMNS, metrics, p, scope_for(p))


def cells(result: Any, kind: str, key: str = "m0") -> list[tuple[Any, ...]]:
    return [
        (
            *row.labels.values(),
            row.values[key],
            row.comparisons[key][kind].base_label,
            row.comparisons[key][kind].base,
            row.comparisons[key][kind].base_status,
            row.comparisons[key][kind].change,
            row.comparisons[key][kind].change_pct,
            row.comparisons[key][kind].change_status,
        )
        for row in result.rows
    ]


@pytest.mark.parametrize("name", sorted(CASES))
def test_v2_without_options_matches_v1(name: str) -> None:
    """Sin opciones nuevas, @2 da las mismas cifras, conteos, orden y evidence_id que @1."""
    metrics, parameters = CASES[name]
    p1 = params(QueryParameters, metrics, **parameters)
    p2 = params(QueryParametersV2, metrics, **parameters)
    v1 = run_query(HEADERS, ROWS, COLUMNS, metrics, p1, scope_for(p1))
    v2 = run_query_v2(HEADERS, ROWS, COLUMNS, metrics, p2, scope_for(p2))
    assert v2.operation == "analytics.query@2" and v2.comparisons == []
    assert v2.shares == [] and v2.ranking is None
    assert v2.dimensions == v1.dimensions and v2.row_count == v1.row_count
    assert [m.model_dump(exclude={"base_counts"}) for m in v2.metrics] == [
        m.model_dump() for m in v1.metrics
    ]
    assert all(m.base_counts == {} for m in v2.metrics)
    assert [r.model_dump(exclude={"comparisons", "share", "rank"}) for r in v2.rows] == [
        r.model_dump() for r in v1.rows
    ]
    assert all(r.comparisons == {} and r.share == {} and r.rank is None for r in v2.rows)


PREVIOUS_ROWS = [
    row("Norte", date(2026, 1, 15), "10.00"),
    row("Norte", date(2026, 2, 10), "15.00"),
    row("Norte", date(2026, 3, 5), "12.00"),
    row("Sur", date(2026, 2, 20), "4.00"),
    row("Sur", date(2026, 3, 1), None),  # medida nula en el periodo consultado
    row("Sur", date(2025, 12, 31), "9.00"),  # fuera de los periodos base necesarios
    row("Este", date(2026, 3, 9), "3.00"),  # sin febrero: sin datos en la base
    row("Norte", None, "1.00"),  # sin fecha
]


def test_previous_period_uses_rows_outside_the_queried_range() -> None:
    result = query2(
        [SUM],
        PREVIOUS_ROWS,
        dimensions=[IDS["region"]],
        time_grain="month",
        time_range={"start": "2026-02-01", "end": "2026-03-31"},
        comparisons=["previous_period"],
    )
    assert cells(result, "previous_period") == [
        ("Este", "2026-03", "3.00", "2026-02", None, "no_base_data", None, None, "base_missing"),
        (
            "Norte",
            "2026-02",
            "15.00",
            "2026-01",
            "10.00",
            "available",
            "5.00",
            "50.00",
            "available",
        ),
        (
            "Norte",
            "2026-03",
            "12.00",
            "2026-02",
            "15.00",
            "available",
            "-3.00",
            "-20.00",
            "available",
        ),
        ("Sur", "2026-02", "4.00", "2026-01", None, "no_base_data", None, None, "base_missing"),
    ]
    definition = result.metrics[0]
    # El periodo consultado cuenta igual que en @1: el rango excluye enero, diciembre y la
    # fila sin fecha (filtros); la medida nula de Sur, como nulo.
    assert definition.counts.model_dump() == {
        "input_rows": 8,
        "excluded_by_filters": 3,
        "excluded_by_nulls": 1,
        "included_rows": 4,
    }
    # La base sólo acepta enero y febrero (los periodos base necesarios).
    assert definition.base_counts["previous_period"].model_dump() == {
        "input_rows": 8,
        "excluded_by_filters": 0,
        "outside_base_periods": 5,
        "excluded_by_nulls": 0,
        "included_rows": 3,
    }
    v1 = run_query(
        HEADERS,
        PREVIOUS_ROWS,
        COLUMNS,
        [SUM],
        params(
            QueryParameters,
            [SUM],
            dimensions=[IDS["region"]],
            time_grain="month",
            time_range={"start": "2026-02-01", "end": "2026-03-31"},
        ),
        SCOPE,
    )
    assert [r.values for r in v1.rows] == [r.values for r in result.rows]
    assert v1.metrics[0].counts == definition.counts


def test_base_counts_add_up_and_respect_query_and_metric_filters() -> None:
    norte = metric(
        9,
        "sum",
        "importe",
        filters=[{"column_id": IDS["cliente"], "operator": "neq", "values": ["z"]}],
    )
    rows = [
        row("Norte", date(2026, 1, 3), "2.00"),
        row("Norte", date(2026, 1, 4), "7.00", "z"),  # excluida por el filtro de la métrica
        row("Sur", date(2026, 1, 5), "8.00"),  # excluida por el filtro de la consulta
        row("Norte", date(2026, 1, 6), None),  # nula en la base
        row("Norte", date(2026, 2, 3), "6.00"),
    ]
    result = query2(
        [norte],
        rows,
        time_grain="month",
        time_range={"start": "2026-02-01", "end": "2026-02-28"},
        filters=[{"column_id": IDS["region"], "operator": "eq", "values": ["Norte"]}],
        comparisons=["previous_period"],
    )
    assert cells(result, "previous_period") == [
        ("2026-02", "6.00", "2026-01", "2.00", "available", "4.00", "200.00", "available")
    ]
    counts = result.metrics[0].base_counts["previous_period"]
    assert (counts.excluded_by_filters, counts.outside_base_periods) == (2, 1)
    assert (counts.excluded_by_nulls, counts.included_rows) == (1, 1)
    assert (
        counts.excluded_by_filters
        + counts.outside_base_periods
        + counts.excluded_by_nulls
        + counts.included_rows
        == counts.input_rows
        == 5
    )


def test_missing_base_is_null_not_zero_and_counts_follow_group_existence() -> None:
    count_x = metric(
        10,
        "count",
        "cliente",
        filters=[{"column_id": IDS["cliente"], "operator": "eq", "values": ["x"]}],
    )
    rows = [
        row("Norte", date(2026, 1, 10), "2.00", "a"),
        row("Norte", date(2026, 2, 10), "3.00", "x"),
        row("Sur", date(2026, 2, 11), "1.00", "x"),
    ]
    result = query2(
        [SUM, count_x],
        rows,
        dimensions=[IDS["region"]],
        time_grain="month",
        comparisons=["previous_period"],
    )
    assert cells(result, "previous_period", "m1") == [
        # Diciembre no existe como grupo: nulo con indicador, también para el conteo.
        ("Norte", "2026-01", "0", "2025-12", None, "no_base_data", None, None, "base_missing"),
        # Enero existe (la suma tiene filas): el conteo vale 0, como en @1; sin porcentaje.
        ("Norte", "2026-02", "1", "2026-01", "0", "available", "1", None, "base_zero"),
        ("Sur", "2026-02", "1", "2026-01", None, "no_base_data", None, None, "base_missing"),
    ]
    assert [r.comparisons["m0"]["previous_period"].base for r in result.rows] == [
        None,
        "2.00",
        None,
    ]


def test_same_period_last_year_counterparts_and_missing_period() -> None:
    days = [
        row("Norte", date(2028, 2, 29), "5.00"),
        row("Norte", date(2027, 2, 28), "4.00"),
        row("Norte", date(2027, 3, 1), "2.00"),
        row("Norte", date(2028, 3, 1), "3.00"),
        row("Norte", None, "9.00"),
    ]
    result = query2([SUM], days, time_grain="day", comparisons=["same_period_last_year"])
    assert cells(result, "same_period_last_year") == [
        ("2027-02-28", "4.00", "2026-02-28", None, "no_base_data", None, None, "base_missing"),
        ("2027-03-01", "2.00", "2026-03-01", None, "no_base_data", None, None, "base_missing"),
        # 29 de febrero: sin equivalente; nunca se sustituye por el 28.
        ("2028-02-29", "5.00", None, None, "no_counterpart", None, None, "base_missing"),
        ("2028-03-01", "3.00", "2027-03-01", "2.00", "available", "1.00", "50.00", "available"),
        ("(sin valor)", "9.00", None, None, "missing_period", None, None, "base_missing"),
    ]
    weeks = [
        row("Norte", date(2020, 12, 28), "1.00"),  # 2020-W53: 2019 no tiene semana 53
        row("Norte", date(2026, 1, 1), "4.00"),  # 2026-W01 (empieza el 2025-12-29)
        row("Norte", date(2025, 1, 2), "2.00"),  # 2025-W01 (empieza el 2024-12-30)
    ]
    weekly = query2([SUM], weeks, time_grain="week", comparisons=["same_period_last_year"])
    assert cells(weekly, "same_period_last_year") == [
        ("2020-W53", "1.00", None, None, "no_counterpart", None, None, "base_missing"),
        ("2025-W01", "2.00", "2024-W01", None, "no_base_data", None, None, "base_missing"),
        ("2026-W01", "4.00", "2025-W01", "2.00", "available", "2.00", "100.00", "available"),
    ]
    assert weekly.rows[2].comparisons["m0"]["same_period_last_year"].base_period == {
        "grain": "week",
        "start": "2024-12-30",
    }


def test_both_comparisons_with_quarters_and_years() -> None:
    rows = [
        row("Norte", date(2025, 4, 1), "1.00"),
        row("Norte", date(2025, 7, 1), "2.00"),
        row("Norte", date(2026, 4, 30), "4.00"),
        row("Norte", date(2026, 1, 15), "3.00"),
    ]
    result = query2(
        [SUM],
        rows,
        time_grain="quarter",
        time_range={"start": "2026-04-01", "end": "2026-06-30"},
        comparisons=["previous_period", "same_period_last_year"],
    )
    assert cells(result, "previous_period") == [
        ("2026-Q2", "4.00", "2026-Q1", "3.00", "available", "1.00", "33.33", "available")
    ]
    assert cells(result, "same_period_last_year") == [
        ("2026-Q2", "4.00", "2025-Q2", "1.00", "available", "3.00", "300.00", "available")
    ]
    yearly = query2([SUM], rows, time_grain="year", comparisons=["previous_period"])
    assert cells(yearly, "previous_period")[1] == (
        "2026",
        "7.00",
        "2025",
        "3.00",
        "available",
        "4.00",
        "133.33",
        "available",
    )


def test_change_arithmetic_is_exact_half_even_and_relative_to_absolute_base() -> None:
    assert change_of("4.00", "3.00", 2, 2, "x") == ("1.00", "33.33", "available")
    # Base negativa: el porcentaje se calcula sobre |base| y conserva el sentido del cambio.
    assert change_of("1.00", "-2.00", 2, 2, "x") == ("3.00", "150.00", "available")
    assert change_of("9", "8", None, 0, "x") == ("1", "12", "available")  # 12.5 → 12 (HALF_EVEN)
    assert change_of("11", "8", None, 0, "x") == ("3", "38", "available")  # 37.5 → 38
    assert change_of("5", "0", None, 2, "x") == ("5", None, "base_zero")
    assert change_of(None, "1.00", 2, 2, "x") == (None, None, "current_missing")
    assert change_of("1.00", None, 2, 2, "x") == (None, None, "base_missing")
    # La media compara las cifras mostradas (ya cuantizadas con avg_scale).
    rows = [
        row("Norte", date(2026, 1, 1), "0.10"),
        row("Norte", date(2026, 1, 2), "0.20"),
        row("Norte", date(2026, 1, 3), "0.20"),
        row("Norte", date(2026, 2, 1), "0.25"),
    ]
    result = query2([AVG], rows, time_grain="month", avg_scale=2, comparisons=["previous_period"])
    assert cells(result, "previous_period")[1] == (
        "2026-02",
        "0.25",
        "2026-01",
        "0.17",
        "available",
        "0.08",
        "47.06",
        "available",
    )


@pytest.mark.parametrize(
    ("grain", "start", "end", "message"),
    [
        ("month", "2026-01-10", None, "empezar el primer día de un mes"),
        ("month", None, "2026-03-30", "terminar el último día de un mes"),
        ("week", "2026-01-01", None, "semana ISO"),  # jueves
        ("quarter", "2026-02-01", "2026-03-31", "trimestre"),
        ("year", "2026-01-01", "2026-12-30", "año"),
        ("month", "2026-02-30", None, "no es una fecha válida"),
    ],
)
def test_comparisons_require_periods_aligned_to_the_grain(
    grain: str, start: str | None, end: str | None, message: str
) -> None:
    bounds = {k: v for k, v in {"start": start, "end": end}.items() if v}
    with pytest.raises(ValidationError) as error:
        params(
            QueryParametersV2,
            [SUM],
            time_grain=grain,
            time_range=bounds,
            comparisons=["previous_period"],
        )
    assert message in str(error.value)


def test_comparison_parameter_rules() -> None:
    aligned = {
        "time_grain": "month",
        "time_range": {"start": "2026-02-01", "end": "2026-02-28"},
        "comparisons": ["previous_period"],
    }
    assert params(QueryParametersV2, [SUM], **aligned).comparisons == ["previous_period"]
    week = {"time_grain": "week", "time_range": {"start": "2025-12-29", "end": "2026-01-11"}}
    assert params(QueryParametersV2, [SUM], comparisons=["previous_period"], **week)
    # Sin comparaciones, un periodo parcial sigue permitido (igual que en @1).
    assert params(QueryParametersV2, [SUM], time_range={"start": "2026-01-10"}, time_grain="month")
    with pytest.raises(ValidationError, match="agrupa por tiempo"):
        params(QueryParametersV2, [SUM], comparisons=["previous_period"])
    with pytest.raises(ValidationError, match="sólo puede aparecer una vez"):
        params(
            QueryParametersV2,
            [SUM],
            time_grain="month",
            comparisons=["previous_period", "previous_period"],
        )
    with pytest.raises(ValidationError):
        params(QueryParameters, [SUM], time_grain="month", comparisons=["previous_period"])


def test_comparison_cells_are_addressable_without_changing_value_evidence() -> None:
    p = params(
        QueryParametersV2,
        [SUM],
        dimensions=[IDS["region"]],
        time_grain="month",
        comparisons=["previous_period", "same_period_last_year"],
    )
    scope = scope_for(p)
    result = run_query_v2(HEADERS, PREVIOUS_ROWS, COLUMNS, [SUM], p, scope)
    first = result.rows[0]
    # La dirección de `value` es la misma fórmula de @1.
    assert first.evidence["m0"] == evidence_reference(scope, SUM, first.key)[0]
    identifiers = [first.evidence["m0"]] + [
        identifier
        for kind in ("previous_period", "same_period_last_year")
        for identifier in first.comparisons["m0"][kind].evidence.values()
    ]
    assert len(set(identifiers)) == 7
    cell = first.comparisons["m0"]["previous_period"]
    identifier, payload = cell_reference(
        scope,
        SUM,
        first.key,
        "previous_period",
        {"comparison": "previous_period", "base_period": cell.base_period},
    )
    assert identifier == cell.evidence["base"]
    assert payload["cell"] == "previous_period" and payload["row_key"] == first.key
    again = run_query_v2(HEADERS, PREVIOUS_ROWS, COLUMNS, [SUM], p, scope)
    assert again.model_dump() == result.model_dump()
    other_scale = run_query_v2(
        HEADERS, PREVIOUS_ROWS, COLUMNS, [SUM], p.model_copy(update={"change_scale": 3}), scope
    )
    before = first.comparisons["m0"]["previous_period"].evidence
    after = other_scale.rows[0].comparisons["m0"]["previous_period"].evidence
    assert before["base"] == after["base"] and before["change"] == after["change"]
    assert before["change_pct"] != after["change_pct"]


def test_comparisons_are_deterministic_with_shuffled_rows() -> None:
    parameters = {
        "dimensions": [IDS["region"]],
        "time_grain": "month",
        "comparisons": ["previous_period", "same_period_last_year"],
    }
    first = query2([SUM, AVG], PREVIOUS_ROWS + ROWS, **parameters)
    shuffled = (PREVIOUS_ROWS + ROWS)[:]
    random.Random(11).shuffle(shuffled)
    assert query2([SUM, AVG], shuffled, **parameters).model_dump() == first.model_dump()


@pytest.mark.parametrize(
    ("start", "grain", "kind", "expected"),
    [
        (date(2026, 1, 1), "month", "previous_period", date(2025, 12, 1)),
        (date(2026, 3, 1), "month", "previous_period", date(2026, 2, 1)),
        (date(2026, 1, 1), "quarter", "previous_period", date(2025, 10, 1)),
        (date(2026, 1, 1), "year", "previous_period", date(2025, 1, 1)),
        (date(2025, 12, 29), "week", "previous_period", date(2025, 12, 22)),
        (date(2026, 3, 1), "day", "previous_period", date(2026, 2, 28)),
        (date(2025, 12, 29), "week", "same_period_last_year", date(2024, 12, 30)),
        (date(2020, 12, 28), "week", "same_period_last_year", None),
        (date(2024, 2, 29), "day", "same_period_last_year", None),
        (date(2026, 4, 1), "quarter", "same_period_last_year", date(2025, 4, 1)),
        (date(1, 1, 1), "day", "previous_period", None),
        (date(1, 1, 1), "month", "previous_period", None),
        (date(1, 1, 1), "year", "same_period_last_year", None),
    ],
)
def test_period_shifts(start: date, grain: Any, kind: Any, expected: date | None) -> None:
    assert shift(start, grain, kind) == expected


def test_period_alignment_helpers() -> None:
    assert starts_period(date(2026, 1, 1), "quarter") and not starts_period(
        date(2026, 2, 1), "quarter"
    )
    assert ends_period(date(2024, 2, 29), "month") and not ends_period(date(2025, 2, 27), "month")
    assert ends_period(date(2026, 1, 4), "week")  # domingo
    assert ends_period(date(9999, 12, 31), "year") and ends_period(date(9999, 12, 31), "day")
