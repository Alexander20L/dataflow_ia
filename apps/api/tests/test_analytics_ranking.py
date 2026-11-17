"""Fase 7B · B2: ranking y participación de analytics.query@2 (motor, sin base de datos).

Top N por periodo (o de todo el resultado) con posiciones 1, 2, 3 sin empates compartidos,
desempate estable por las dimensiones e indicador `tied_with_previous`; participación sobre el
total ANTES del recorte, redondeada por separado con tolerancia declarada; presupuesto de filas
después del top N.
"""

import random
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError
from test_analytics_comparisons import AVG, SUM, metric, params, query2, row, scope_for
from test_analytics_query_v1_golden import COLUMNS, HEADERS, IDS

from dataflow.modules.analytics.contracts import QueryParametersV2
from dataflow.modules.analytics.engine import cell_reference, evidence_reference, run_query_v2
from dataflow.platform.errors import ApplicationError

JAN, FEB = date(2026, 1, 10), date(2026, 2, 10)
SALES = [
    row("Norte", JAN, "30.00", "a"),
    row("Sur", JAN, "50.00", "b"),
    row("Este", JAN, "30.00", "x"),
    row("Oeste", JAN, "20.00", "c"),
    row(None, JAN, "10.00", "d"),  # región sin valor: es un grupo y se ordena como cualquiera
    row("Centro", JAN, None, "e"),  # sólo medida nula: el grupo no existe
    row("Norte", FEB, "5.00", "x"),
    row("Sur", FEB, "5.00", "f"),
]
BY_REGION = {"dimensions": [IDS["region"]]}


def ranking(by: Any = SUM, top_n: int = 3, direction: str = "desc") -> dict[str, Any]:
    return {
        "metric_revision_id": str(by.reference.revision_id),
        "top_n": top_n,
        "direction": direction,
    }


def ranks(result: Any) -> list[tuple[Any, ...]]:
    return [
        (*r.labels.values(), r.values["m0"], r.rank.position, r.rank.tied_with_previous)
        for r in result.rows
    ]


def test_top_n_over_the_whole_result_hides_the_rest() -> None:
    result = query2([SUM], SALES, ranking=ranking(top_n=3), **BY_REGION)
    assert ranks(result) == [
        ("Sur", "55.00", 1, False),
        ("Norte", "35.00", 2, False),
        ("Este", "30.00", 3, False),
    ]
    summary = result.ranking
    assert (summary.metric, summary.direction, summary.top_n, summary.hidden_groups) == (
        "m0",
        "desc",
        3,
        2,
    )
    assert [p.model_dump() for p in summary.partitions] == [
        {"period": None, "groups": 5, "ranked": 5, "shown": 3, "hidden": 2}
    ]
    assert result.row_count == 3


def test_ties_get_distinct_positions_by_dimension_and_are_flagged() -> None:
    result = query2([SUM], SALES, ranking=ranking(top_n=4), time_grain="month", **BY_REGION)
    assert ranks(result) == [
        # Enero: Este y Norte valen 30.00; Este va antes por la dimensión y Norte se marca.
        ("Sur", "2026-01", "50.00", 1, False),
        ("Este", "2026-01", "30.00", 2, False),
        ("Norte", "2026-01", "30.00", 3, True),
        ("Oeste", "2026-01", "20.00", 4, False),
        # Febrero: partición propia.
        ("Norte", "2026-02", "5.00", 1, False),
        ("Sur", "2026-02", "5.00", 2, True),
    ]
    assert [(p.period, p.shown, p.hidden) for p in result.ranking.partitions] == [
        ({"grain": "month", "start": "2026-01-01"}, 4, 1),
        ({"grain": "month", "start": "2026-02-01"}, 2, 0),
    ]
    ascending = query2(
        [SUM], SALES, ranking=ranking(top_n=2, direction="asc"), time_grain="month", **BY_REGION
    )
    assert ranks(ascending) == [
        ("(sin valor)", "2026-01", "10.00", 1, False),
        ("Oeste", "2026-01", "20.00", 2, False),
        ("Norte", "2026-02", "5.00", 1, False),
        ("Sur", "2026-02", "5.00", 2, True),
    ]


def test_groups_without_a_value_have_no_position_and_are_counted_as_hidden() -> None:
    only_x = metric(
        20,
        "max",
        "importe",
        filters=[{"column_id": IDS["cliente"], "operator": "eq", "values": ["x"]}],
    )
    result = query2([only_x, SUM], SALES, ranking=ranking(only_x, top_n=10), **BY_REGION)
    # Sólo Este y Norte tienen filas de «x»; el resto no tiene valor: sin posición y oculto.
    assert [(r.labels["d0"], r.values["m0"], r.rank.position) for r in result.rows] == [
        ("Este", "30.00", 1),
        ("Norte", "5.00", 2),
    ]
    assert result.ranking.metric == "m0"
    assert [p.model_dump() for p in result.ranking.partitions] == [
        {"period": None, "groups": 5, "ranked": 2, "shown": 2, "hidden": 3}
    ]
    assert result.ranking.hidden_groups == 3


def test_rank_evidence_includes_the_tie_flag() -> None:
    p = params(QueryParametersV2, [SUM], ranking=ranking(top_n=4), time_grain="month", **BY_REGION)
    scope = scope_for(p)
    result = run_query_v2(HEADERS, SALES, COLUMNS, [SUM], p, scope)
    tied = result.rows[2]
    assert tied.rank.tied_with_previous
    identifier, payload = cell_reference(
        scope,
        SUM,
        tied.key,
        "rank",
        {"direction": "desc", "top_n": 4, "tied_with_previous": True},
    )
    assert identifier == tied.rank.evidence
    assert payload["cell"] == "rank" and payload["detail"]["tied_with_previous"] is True
    assert payload["metric"] == SUM.reference.model_dump(mode="json")
    # La evidencia de `value` sigue siendo la de @1, y cada celda tiene su propia dirección.
    assert tied.evidence["m0"] == evidence_reference(scope, SUM, tied.key)[0]
    assert (
        len({r.rank.evidence for r in result.rows} | {r.evidence["m0"] for r in result.rows}) == 12
    )


def test_share_of_total_per_period_uses_the_total_before_the_cut() -> None:
    result = query2(
        [SUM],
        SALES,
        ranking=ranking(top_n=2),
        share_of_total=[str(SUM.reference.revision_id)],
        time_grain="month",
        **BY_REGION,
    )
    assert [
        (*r.labels.values(), r.values["m0"], r.share["m0"].value, r.share["m0"].status)
        for r in result.rows
    ] == [
        # Total de enero: 140.00 (incluye Oeste y el grupo sin valor, ocultos por el top 2).
        ("Sur", "2026-01", "50.00", "35.71", "available"),
        ("Este", "2026-01", "30.00", "21.43", "available"),
        ("Norte", "2026-02", "5.00", "50.00", "available"),
        ("Sur", "2026-02", "5.00", "50.00", "available"),
    ]
    assert [t.model_dump() for t in result.shares] == [
        {
            "metric": "m0",
            "period": {"grain": "month", "start": "2026-01-01"},
            "total": "140.00",
            "groups": 5,
            "tolerance": "0.025",
            "mixed_signs": False,
        },
        {
            "metric": "m0",
            "period": {"grain": "month", "start": "2026-02-01"},
            "total": "10.00",
            "groups": 2,
            "tolerance": "0.010",
            "mixed_signs": False,
        },
    ]


def test_share_rounding_tolerance_counts_and_scale() -> None:
    thirds = [row(r, JAN, "1.00") for r in ["A", "B", "C"]]
    count = metric(21, "count", "cliente")
    result = query2(
        [SUM, count],
        thirds,
        share_of_total=[str(SUM.reference.revision_id), str(count.reference.revision_id)],
        **BY_REGION,
    )
    shares = [r.share["m0"].value for r in result.rows]
    # Cada porcentaje se redondea por separado: 99.99, dentro de la tolerancia declarada.
    assert shares == ["33.33", "33.33", "33.33"]
    assert result.shares[0].tolerance == "0.015" and result.shares[1].total == "3"
    assert [r.share["m1"].value for r in result.rows] == ["33.33", "33.33", "33.33"]
    fine = query2(
        [SUM], thirds, share_of_total=[str(SUM.reference.revision_id)], share_scale=0, **BY_REGION
    )
    assert [r.share["m0"].value for r in fine.rows] == ["33", "33", "33"]
    assert fine.shares[0].tolerance == "1.5"
    halves = [row("A", JAN, "1.00"), row("B", JAN, "7.00")]  # 12.5 → 12 y 87.5 → 88 (HALF_EVEN)
    even = query2(
        [SUM], halves, share_of_total=[str(SUM.reference.revision_id)], share_scale=0, **BY_REGION
    )
    assert [r.share["m0"].value for r in even.rows] == ["12", "88"]


def test_share_with_zero_total_negative_values_and_missing_values() -> None:
    zero = [row("A", JAN, "5.00"), row("B", JAN, "-5.00")]
    result = query2([SUM], zero, share_of_total=[str(SUM.reference.revision_id)], **BY_REGION)
    assert [(r.share["m0"].value, r.share["m0"].status) for r in result.rows] == [
        (None, "total_zero"),
        (None, "total_zero"),
    ]
    assert result.shares[0].mixed_signs and result.shares[0].total == "0.00"
    mixed = [row("A", JAN, "10.00"), row("B", JAN, "-2.00")]
    signed = query2([SUM], mixed, share_of_total=[str(SUM.reference.revision_id)], **BY_REGION)
    assert [r.share["m0"].value for r in signed.rows] == ["125.00", "-25.00"]
    only_x = metric(
        22,
        "sum",
        "importe",
        filters=[{"column_id": IDS["cliente"], "operator": "eq", "values": ["x"]}],
    )
    partial = query2(
        [only_x, SUM], SALES, share_of_total=[str(only_x.reference.revision_id)], **BY_REGION
    )
    by_region = {r.labels["d0"]: (r.share["m0"].value, r.share["m0"].status) for r in partial.rows}
    assert by_region["Este"] == ("85.71", "available")  # 30 / 35
    assert by_region["Sur"] == (None, "value_missing")
    assert all("m1" not in r.share for r in partial.rows)


def test_share_only_for_additive_metrics() -> None:
    with pytest.raises(ApplicationError) as error:
        query2([AVG], SALES, share_of_total=[str(AVG.reference.revision_id)], **BY_REGION)
    assert error.value.code == "SHARE_NOT_ADDITIVE"
    distinct = metric(23, "count_distinct", "cliente")
    with pytest.raises(ApplicationError):
        query2([distinct], SALES, share_of_total=[str(distinct.reference.revision_id)])


def test_ranking_and_share_parameter_rules() -> None:
    with pytest.raises(ValidationError, match="al menos una dimensión"):
        params(QueryParametersV2, [SUM], ranking=ranking())
    with pytest.raises(ValidationError, match="métricas de la consulta"):
        params(QueryParametersV2, [SUM], share_of_total=[str(AVG.reference.revision_id)])
    with pytest.raises(ValidationError, match="una de las métricas"):
        params(QueryParametersV2, [SUM], ranking=ranking(AVG), **BY_REGION)
    with pytest.raises(ValidationError, match="sólo puede aparecer una vez"):
        params(
            QueryParametersV2,
            [SUM],
            share_of_total=[str(SUM.reference.revision_id)] * 2,
        )
    for bad in (0, 1001):
        with pytest.raises(ValidationError):
            params(QueryParametersV2, [SUM], ranking=ranking(top_n=bad), **BY_REGION)
    with pytest.raises(ValidationError):
        params(QueryParametersV2, [SUM], share_scale=13)


def test_budget_applies_after_the_top_n() -> None:
    # Cinco grupos y límite de 3 filas: sin ranking no cabe; con top 3, sí.
    with pytest.raises(ApplicationError) as error:
        query2([SUM], SALES, max_result_rows=3, **BY_REGION)
    assert error.value.code == "RESULT_TOO_LARGE" and "5 filas" in error.value.message
    assert (
        query2([SUM], SALES, max_result_rows=3, ranking=ranking(top_n=3), **BY_REGION).row_count
        == 3
    )
    with pytest.raises(ApplicationError) as after:
        query2([SUM], SALES, max_result_rows=3, ranking=ranking(top_n=4), **BY_REGION)
    assert after.value.code == "RESULT_TOO_LARGE" and "4 filas tras el top N" in after.value.message


def test_ranking_share_and_comparisons_together_are_deterministic() -> None:
    parameters: dict[str, Any] = {
        "ranking": ranking(top_n=2),
        "share_of_total": [str(SUM.reference.revision_id)],
        "time_grain": "month",
        "comparisons": ["previous_period"],
        **BY_REGION,
    }
    first = query2([SUM, AVG], SALES, **parameters)
    feb = [r for r in first.rows if r.labels["period"] == "2026-02"]
    assert [
        (r.labels["d0"], r.comparisons["m0"]["previous_period"].base, r.share["m0"].value)
        for r in feb
    ] == [("Norte", "30.00", "50.00"), ("Sur", "50.00", "50.00")]
    shuffled = SALES[:]
    random.Random(5).shuffle(shuffled)
    assert query2([SUM, AVG], shuffled, **parameters).model_dump() == first.model_dump()
    ids = [r.share["m0"].evidence for r in first.rows] + [r.rank.evidence for r in first.rows]
    assert len(set(ids)) == len(ids)
