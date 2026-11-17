"""Fase 7A · A1: motor de analytics.query@1 (sin base de datos)."""

import random
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from dataflow.modules.analytics.contracts import (
    BaseTable,
    EvidenceScope,
    MetricContent,
    MetricReference,
    QueryParameters,
)
from dataflow.modules.analytics.domain import metric_problems, period
from dataflow.modules.analytics.engine import Metric, evidence_reference, run_query
from dataflow.platform.errors import ApplicationError

IDS = {n: uuid4() for n in ["region", "fecha", "importe", "unidades", "cliente"]}
COLUMNS: list[dict[str, Any]] = [
    {"id": str(IDS["region"]), "name": "region", "technical_type": "string", "type_parameters": {}},
    {"id": str(IDS["fecha"]), "name": "fecha", "technical_type": "date", "type_parameters": {}},
    {
        "id": str(IDS["importe"]),
        "name": "importe",
        "technical_type": "decimal",
        "type_parameters": {"scale": 2},
    },
    {
        "id": str(IDS["unidades"]),
        "name": "unidades",
        "technical_type": "integer",
        "type_parameters": {},
    },
    {
        "id": str(IDS["cliente"]),
        "name": "cliente",
        "technical_type": "string",
        "type_parameters": {},
    },
]
HEADERS = [str(c["name"]) for c in COLUMNS]
D = Decimal
ROWS: list[list[Any]] = [
    ["Norte", date(2026, 1, 5), D("0.10"), 1, "a"],
    ["Sur", date(2026, 1, 20), D("0.20"), 2, "b"],
    ["Norte", date(2026, 1, 31), D("0.20"), 3, "a"],
    ["Norte", date(2026, 2, 1), None, 4, "c"],  # importe nulo
    [None, date(2026, 2, 3), D("1.00"), 5, "d"],  # región nula: grupo «(sin valor)»
    ["Sur", None, D("2.50"), 6, "b"],  # fecha nula
]
TABLE = BaseTable(version_id=uuid4(), artifact_id=uuid4(), artifact_sha256="a" * 64)
SCOPE = EvidenceScope(
    execution_id=UUID("00000000-0000-4000-8000-000000000007"),
    step_id="query",
    input=TABLE,
    semantic_ref=None,
    query_filters=[],
    time_grain=None,
    time_range=None,
)


def metric(aggregation: str = "sum", column: str = "importe", **extra: Any) -> Metric:
    content = MetricContent.model_validate(
        {
            "label": f"{aggregation} {column}",
            "measure_column_id": str(IDS[column]),
            "aggregation": aggregation,
            "time_column_id": str(IDS["fecha"]),
            "base_table": TABLE.model_dump(mode="json"),
            **extra,
        }
    )
    return Metric(MetricReference(revision_id=uuid4(), content_sha256="b" * 64), 1, content)


def query(metrics: list[Metric], rows: list[list[Any]] = ROWS, **parameters: Any) -> Any:
    params = QueryParameters.model_validate(
        {
            "metrics": [m.reference.model_dump(mode="json") for m in metrics],
            **parameters,
        }
    )
    scope = SCOPE.model_copy(
        update={"time_grain": params.time_grain, "time_range": params.time_range}
    )
    return run_query(HEADERS, rows, COLUMNS, metrics, params, scope)


def table(result: Any) -> list[tuple[Any, ...]]:
    return [(*row.labels.values(), *row.values.values()) for row in result.rows]


def test_exact_decimal_sums_null_groups_and_counts() -> None:
    result = query([metric("sum")], dimensions=[str(IDS["region"])])
    # 0.10 + 0.20 = 0.30 exacto; la región nula es su propio grupo y va al final.
    assert table(result) == [("Norte", "0.30"), ("Sur", "2.70"), ("(sin valor)", "1.00")]
    counts = result.metrics[0].counts
    assert counts.model_dump() == {
        "input_rows": 6,
        "excluded_by_filters": 0,
        "excluded_by_nulls": 1,
        "included_rows": 5,
    }
    missing = result.rows[2].key["dimensions"][0]["value"]
    assert missing == {"missing": True}  # marca explícita, no una cadena


def test_avg_is_exact_and_half_even_at_the_declared_scale() -> None:
    rows = [["Norte", date(2026, 1, 1), D(v), 1, "a"] for v in ["0.10", "0.20", "0.20"]]
    assert table(query([metric("avg")], rows))[0] == ("0.1667",)
    assert table(query([metric("avg")], rows, avg_scale=2))[0] == ("0.17",)
    tie = [["Norte", date(2026, 1, 1), D(v), 1, "a"] for v in ["0.12", "0.13"]]
    # 0.125 → 0.12 (HALF_EVEN), no 0.13; Polars devolvería un float inexacto.
    assert table(query([metric("avg")], tie, avg_scale=2))[0] == ("0.12",)
    big = [["Norte", date(2026, 1, 1), D("0.00"), 2**62, "a"]] * 4
    assert table(query([metric("sum", "unidades")], big))[0] == (str(2**64),)


def test_counts_min_max_and_groups_without_rows() -> None:
    result = query(
        [
            metric("count_distinct", "cliente"),
            metric("count", "importe"),
            metric("min", "importe"),
            metric(
                "max",
                "importe",
                filters=[{"column_id": str(IDS["region"]), "operator": "eq", "values": ["Sur"]}],
            ),
        ],
        dimensions=[str(IDS["region"])],
    )
    assert table(result) == [
        ("Norte", "2", "2", "0.10", None),  # sin filas de «Sur» para max: None, no 0
        ("Sur", "1", "2", "0.20", "2.50"),
        ("(sin valor)", "1", "1", "1.00", None),
    ]
    assert result.metrics[3].counts.excluded_by_filters == 4


def test_time_grain_range_and_null_dates() -> None:
    result = query([metric("sum")], dimensions=[str(IDS["region"])], time_grain="month")
    assert table(result) == [
        ("Norte", "2026-01", "0.30"),
        ("Sur", "2026-01", "0.20"),
        ("Sur", "(sin valor)", "2.50"),
        ("(sin valor)", "2026-02", "1.00"),
    ]
    ranged = query(
        [metric("sum")],
        time_grain="month",
        time_range={"start": "2026-01-10", "end": "2026-02-28"},
    )
    assert table(ranged) == [("2026-01", "0.40"), ("2026-02", "1.00")]
    counts = ranged.metrics[0].counts
    # Fuera de rango (incluida la fecha nula) cuenta como filtrado; el importe nulo, como nulo.
    assert (counts.excluded_by_filters, counts.excluded_by_nulls) == (2, 1)


@pytest.mark.parametrize(
    ("day", "grain", "label", "start"),
    [
        (date(2025, 12, 29), "week", "2026-W01", date(2025, 12, 29)),
        (date(2026, 1, 4), "week", "2026-W01", date(2025, 12, 29)),
        (date(2021, 1, 3), "week", "2020-W53", date(2020, 12, 28)),
        (date(2024, 12, 30), "week", "2025-W01", date(2024, 12, 30)),
        (date(2025, 12, 31), "quarter", "2025-Q4", date(2025, 10, 1)),
        (date(2026, 1, 1), "quarter", "2026-Q1", date(2026, 1, 1)),
        (date(2026, 2, 28), "month", "2026-02", date(2026, 2, 1)),
        (date(2024, 2, 29), "year", "2024", date(2024, 1, 1)),
        (date(1, 1, 1), "day", "0001-01-01", date(1, 1, 1)),
    ],
)
def test_iso_periods_at_year_boundaries(day: date, grain: Any, label: str, start: date) -> None:
    assert period(day, grain) == (start, label)


def test_weeks_spanning_years_are_one_group() -> None:
    rows = [
        ["Norte", date(2025, 12, 29), D("1.00"), 1, "a"],
        ["Norte", date(2026, 1, 4), D("2.00"), 1, "a"],
        ["Norte", date(2026, 1, 5), D("4.00"), 1, "a"],
    ]
    assert table(query([metric("sum")], rows, time_grain="week")) == [
        ("2026-W01", "3.00"),
        ("2026-W02", "4.00"),
    ]


def test_result_is_deterministic_and_order_is_stable() -> None:
    metrics = [metric("sum"), metric("count", "cliente")]
    first = query(metrics, dimensions=[str(IDS["region"]), str(IDS["cliente"])], time_grain="month")
    shuffled = ROWS[:]
    random.Random(7).shuffle(shuffled)
    second = query(
        metrics, shuffled, dimensions=[str(IDS["region"]), str(IDS["cliente"])], time_grain="month"
    )
    assert second.model_dump() == first.model_dump()


def test_budget_and_time_column_errors() -> None:
    with pytest.raises(ApplicationError) as error:
        query([metric("sum")], dimensions=[str(IDS["unidades"])], max_result_rows=4)
    assert error.value.code == "RESULT_TOO_LARGE" and "5 filas" in error.value.message
    other = metric("sum", time_column_id=None)
    with pytest.raises(ApplicationError) as mismatch:
        query([metric("sum"), other], time_grain="month")
    assert mismatch.value.code == "TIME_COLUMN_MISMATCH"
    huge = [["Norte", date(2026, 1, 1), D("9" * 36), 1, "a"]] * 1000
    with pytest.raises(ApplicationError) as precision:
        query([metric("sum")], huge)
    assert precision.value.code == "RESULT_PRECISION_EXCEEDED"


def test_evidence_keys_use_canonical_cells() -> None:
    """Las dimensiones de la clave usan la celda canónica de la Fase 6: 10.5 y 10.50 (escala 2)
    son el mismo valor y generan el mismo evidence_id; el grupo sin valor lleva una marca
    explícita que no se confunde con el texto «(sin valor)»."""
    m = metric("sum")
    decimal_dim = [{"column_id": str(IDS["importe"]), "value": "10.50"}]

    def key(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
        return {"dimensions": dimensions, "period": None}

    by_dimension = query([metric("count", "cliente")], dimensions=[str(IDS["importe"])])
    keys = [row.key["dimensions"][0]["value"] for row in by_dimension.rows]
    assert "0.10" in keys and {"missing": True} in keys
    rows = [["Norte", date(2026, 1, 1), D(v), 1, "a"] for v in ["10.5", "10.50"]]
    one = query([metric("count", "cliente")], rows, dimensions=[str(IDS["importe"])])
    assert [r.key["dimensions"][0]["value"] for r in one.rows] == ["10.50"]  # un solo grupo
    assert (
        evidence_reference(SCOPE, m, key(decimal_dim))[0]
        == evidence_reference(
            SCOPE, m, key([{"column_id": str(IDS["importe"]), "value": "10.50"}])
        )[0]
    )
    text = [
        ["(sin valor)", date(2026, 1, 1), D("1.00"), 1, "a"],
        [None, date(2026, 1, 1), D("2.00"), 1, "a"],
    ]
    split = query([m], text, dimensions=[str(IDS["region"])])
    assert [r.values["m0"] for r in split.rows] == ["1.00", "2.00"]
    assert len({r.evidence["m0"] for r in split.rows}) == 2
    assert split.rows[0].key["dimensions"][0]["value"] == "(sin valor)"
    assert split.rows[1].key["dimensions"][0]["value"] == {"missing": True}
    # Mismo cálculo, mismo evidence_id; otra ejecución, otro.
    again = query([m], text, dimensions=[str(IDS["region"])])
    assert [r.evidence for r in again.rows] == [r.evidence for r in split.rows]
    other_scope = SCOPE.model_copy(update={"execution_id": uuid4()})
    assert (
        evidence_reference(other_scope, m, key(decimal_dim))[0]
        != evidence_reference(SCOPE, m, key(decimal_dim))[0]
    )


def test_metric_validation_against_schema() -> None:
    def problems(**draft: Any) -> list[str]:
        content = MetricContent.model_validate(
            {"label": "x", "base_table": TABLE.model_dump(mode="json"), **draft}
        )
        return [p.code for p in metric_problems(content, COLUMNS)]

    assert problems(measure_column_id=str(IDS["importe"]), aggregation="sum") == []
    assert problems(measure_column_id=str(IDS["cliente"]), aggregation="sum") == [
        "COLUMN_TYPE_MISMATCH"
    ]
    assert problems(measure_column_id=str(IDS["cliente"]), aggregation="count_distinct") == []
    assert problems(
        measure_column_id=str(IDS["importe"]), aggregation="sum", time_column_id=str(IDS["region"])
    ) == ["COLUMN_TYPE_MISMATCH"]
    assert problems(
        measure_column_id=str(IDS["importe"]),
        aggregation="sum",
        filters=[{"column_id": str(IDS["importe"]), "operator": "gt", "values": ["1,5"]}],
    ) == ["INVALID_FILTER_VALUE"]
    assert problems(
        measure_column_id=str(IDS["importe"]),
        aggregation="sum",
        filters=[{"column_id": str(IDS["region"]), "operator": "gt", "values": ["a"]}],
    ) == ["COLUMN_TYPE_MISMATCH"]
    assert problems(measure_column_id=str(uuid4()), aggregation="count") == ["UNKNOWN_COLUMN"]
