"""Referencia dorada de analytics.query@1 (Fase 7B, etapa B1).

Capturada ANTES de ampliar el motor con analytics.query@2: el JSON exacto que escribe el
procesador (`AnalysisResult.model_dump_json()`, con el orden de sus claves) para un conjunto de
consultas representativas con IDs y ámbito fijos. La 7B no puede cambiar ningún resultado de
@1 —valores, conteos, orden de filas ni `evidence_id`—: si esta prueba falla, el cambio no es
aditivo.

Las referencias no se regeneran para hacer pasar la prueba.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from dataflow.modules.analytics.contracts import (
    BaseTable,
    EvidenceScope,
    MetricContent,
    MetricReference,
    QueryParameters,
)
from dataflow.modules.analytics.engine import Metric, run_query

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "phase7_query_v1_golden"


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


IDS = {"region": uid(101), "fecha": uid(102), "importe": uid(103), "unidades": uid(104)}
IDS["cliente"] = uid(105)
COLUMNS: list[dict[str, Any]] = [
    {"id": IDS["region"], "name": "region", "technical_type": "string", "type_parameters": {}},
    {"id": IDS["fecha"], "name": "fecha", "technical_type": "date", "type_parameters": {}},
    {
        "id": IDS["importe"],
        "name": "importe",
        "technical_type": "decimal",
        "type_parameters": {"precision": 12, "scale": 2},
    },
    {"id": IDS["unidades"], "name": "unidades", "technical_type": "integer", "type_parameters": {}},
    {"id": IDS["cliente"], "name": "cliente", "technical_type": "string", "type_parameters": {}},
]
HEADERS = [str(c["name"]) for c in COLUMNS]
D = Decimal
ROWS: list[list[Any]] = [
    ["Norte", date(2025, 12, 29), D("10.00"), 1, "a"],
    ["Norte", date(2026, 1, 4), D("0.10"), 2, "a"],
    ["Sur", date(2026, 1, 20), D("0.20"), 3, "b"],
    ["Norte", date(2026, 1, 31), D("0.20"), 4, "c"],
    ["Norte", date(2026, 2, 1), None, 5, "c"],
    [None, date(2026, 2, 3), D("1.00"), 6, "d"],
    ["Sur", None, D("2.50"), 7, "b"],
    ["Este", date(2026, 3, 15), D("-4.25"), 8, "e"],
    ["Sur", date(2026, 4, 1), D("0.13"), None, "a"],
    ["Sur", date(2026, 4, 2), D("0.12"), 9, None],
    ["Norte", date(2025, 2, 10), D("7.77"), 10, "f"],
    ["Este", date(2025, 3, 31), D("3.00"), 11, "e"],
]
TABLE = BaseTable(version_id=UUID(uid(1)), artifact_id=UUID(uid(2)), artifact_sha256="a" * 64)
SCOPE = EvidenceScope(
    execution_id=UUID(uid(3)),
    step_id="query",
    input=TABLE,
    semantic_ref={"id": uid(4), "revision": 2, "content_sha256": "c" * 64},
    query_filters=[],
    time_grain=None,
    time_range=None,
)


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
    reference = MetricReference(revision_id=UUID(uid(200 + number)), content_sha256="b" * 64)
    unit = "EUR" if aggregation in {"sum", "avg", "min", "max"} else None
    return Metric(reference, number, content, None, unit)


SUM = metric(1, "sum", "importe")
AVG = metric(2, "avg", "importe")
COUNT = metric(3, "count", "unidades")
DISTINCT = metric(4, "count_distinct", "cliente")
MIN = metric(5, "min", "importe")
MAX_NORTE = metric(
    6,
    "max",
    "importe",
    filters=[{"column_id": IDS["region"], "operator": "eq", "values": ["Norte"]}],
)
SUM_UNITS = metric(7, "sum", "unidades")

CASES: dict[str, tuple[list[Metric], dict[str, Any]]] = {
    "total": ([SUM, COUNT, DISTINCT], {}),
    "by_region": ([SUM, AVG, MIN, MAX_NORTE], {"dimensions": [IDS["region"]]}),
    "region_month": (
        [SUM, COUNT],
        {"dimensions": [IDS["region"]], "time_grain": "month"},
    ),
    "range_month": (
        [SUM, AVG],
        {
            "time_grain": "month",
            "time_range": {"start": "2026-01-10", "end": "2026-03-31"},
            "avg_scale": 2,
        },
    ),
    "week_across_years": ([SUM, SUM_UNITS], {"time_grain": "week"}),
    "quarter_two_dimensions": (
        [SUM, DISTINCT],
        {"dimensions": [IDS["region"], IDS["cliente"]], "time_grain": "quarter"},
    ),
    "year_filters": (
        [SUM, COUNT],
        {
            "dimensions": [IDS["region"]],
            "time_grain": "year",
            "filters": [
                {"column_id": IDS["region"], "operator": "in", "values": ["Norte", "Este"]},
                {"column_id": IDS["importe"], "operator": "between", "values": ["-5", "9.99"]},
            ],
        },
    ),
    "open_range_day": (
        [SUM],
        {"time_grain": "day", "time_range": {"start": "2026-03-01"}, "avg_scale": 0},
    ),
}


def capture(name: str) -> dict[str, Any]:
    metrics, parameters = CASES[name]
    params = QueryParameters.model_validate(
        {"metrics": [m.reference.model_dump(mode="json") for m in metrics], **parameters}
    )
    scope = SCOPE.model_copy(
        update={
            "query_filters": params.filters,
            "time_grain": params.time_grain,
            "time_range": params.time_range,
        }
    )
    result = run_query(HEADERS, ROWS, COLUMNS, metrics, params, scope)
    # El texto exacto del artefacto; json.loads conserva el orden de las claves.
    loaded: dict[str, Any] = json.loads(result.model_dump_json())
    return loaded


def serialized(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", sorted(CASES))
def test_query_v1_keeps_its_golden_result(name: str) -> None:
    expected = (GOLDEN / f"{name}.golden.json").read_text(encoding="utf-8")
    assert serialized(capture(name)) == expected
