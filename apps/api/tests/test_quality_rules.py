"""Fase 6B · B1: dominio y evaluación de csv-quality-v2."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from dataflow.modules.quality.domain import required_types, validate_rules
from dataflow.modules.quality.public import evaluate_quality
from dataflow.modules.quality.rules_contracts import Rule, RulesetDraft, RulesetReference
from dataflow.modules.quality.rules_engine import evaluate_rules

IDS = {name: uuid4() for name in ["id", "fecha", "region", "importe", "unidades", "codigo"]}
COLUMNS: list[dict[str, Any]] = [
    {"id": str(IDS["id"]), "name": "id", "technical_type": "string", "type_parameters": {}},
    {"id": str(IDS["fecha"]), "name": "fecha", "technical_type": "date", "type_parameters": {}},
    {"id": str(IDS["region"]), "name": "region", "technical_type": "string", "type_parameters": {}},
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
    {"id": str(IDS["codigo"]), "name": "codigo", "technical_type": "string", "type_parameters": {}},
]
HEADERS = [str(c["name"]) for c in COLUMNS]
ROWS: list[list[Any]] = [
    ["001", date(2026, 1, 1), "Norte", Decimal("100.50"), 2, "12"],
    ["002", date(2026, 1, 2), "Sur", None, 1, "1,5"],
    ["003", date(2026, 1, 3), "Oeste", Decimal("80.00"), 3, " 7"],
    ["001", date(2026, 1, 1), "Norte", Decimal("100.50"), 2, "12"],
    [None, date(2025, 12, 31), " ", Decimal("-5.00"), 0, None],
]
REF = RulesetReference(id=uuid4(), revision=1, content_sha256="a" * 64)
RULES = TypeAdapter(list[Rule])


def rules(*items: dict[str, Any]) -> list[Any]:
    return RULES.validate_python(list(items))


def test_user_rules_are_separated_from_technical_completeness() -> None:
    report = evaluate_rules(
        HEADERS,
        ROWS,
        COLUMNS,
        rules(
            {"id": "importe_obligatorio", "kind": "required", "column_id": str(IDS["importe"])},
            {"id": "clave", "kind": "unique_key", "column_ids": [str(IDS["id"])]},
            {
                "id": "importe_positivo",
                "kind": "range",
                "column_id": str(IDS["importe"]),
                "minimum": "0",
                "severity": "high",
            },
            {
                "id": "fecha_2026",
                "kind": "range",
                "column_id": str(IDS["fecha"]),
                "minimum": "2026-01-01",
                "maximum": "2026-12-31",
            },
            {
                "id": "regiones",
                "kind": "allowed_values",
                "column_id": str(IDS["region"]),
                "values": ["Norte", "Sur", "Este"],
            },
            {
                "id": "unidades_validas",
                "kind": "allowed_values",
                "column_id": str(IDS["unidades"]),
                "values": ["1", "2", "3"],
            },
            {
                "id": "codigo_entero",
                "kind": "convertible",
                "column_id": str(IDS["codigo"]),
                "type": "integer",
            },
            {"id": "sin_fallos", "kind": "required", "column_id": str(IDS["fecha"])},
        ),
        REF,
    )
    technical = evaluate_quality(HEADERS, ROWS, [str(c["technical_type"]) for c in COLUMNS])
    # La parte técnica es exactamente csv-quality-v1: las reglas no la alteran.
    assert report.technical.completeness_percent == technical.completeness_percent
    assert [i.id for i in report.issues if i.origin == "technical"] == [
        i.id for i in technical.issues
    ]
    user = {
        i.rule_id: (i.affected_rows, i.sample_row_numbers)
        for i in report.issues
        if i.origin == "user"
    }
    assert user == {
        "importe_obligatorio": (1, [2]),
        "clave": (2, [4, 5]),  # repetida (4) y nula (5)
        "importe_positivo": (1, [5]),
        "fecha_2026": (1, [5]),
        "regiones": (2, [3, 5]),  # «Oeste» y « »; el nulo no cuenta
        "unidades_validas": (1, [5]),  # 0 como cadena canónica «0»
        "codigo_entero": (2, [2, 3]),  # «1,5» y « 7» (espacios); nulo ignorado
    }
    assert (report.user.rules_evaluated, report.user.rules_failed) == (8, 7)
    assert next(i for i in report.issues if i.rule_id == "importe_positivo").severity == "high"
    assert report.ruleset == REF and report.rule_version == "csv-quality-v2"


def test_validation_against_table_schema() -> None:
    other = uuid4()
    problems = validate_rules(
        rules(
            {"id": "a", "kind": "range", "column_id": str(IDS["region"]), "minimum": "1"},
            {"id": "b", "kind": "convertible", "column_id": str(IDS["importe"]), "type": "integer"},
            {"id": "c", "kind": "required", "column_id": str(other)},
            {"id": "d", "kind": "range", "column_id": str(IDS["importe"]), "minimum": "1e5"},
            {
                "id": "e",
                "kind": "range",
                "column_id": str(IDS["fecha"]),
                "minimum": "2026-12-31",
                "maximum": "2026-01-01",
            },
            {"id": "f", "kind": "allowed_values", "column_id": str(IDS["fecha"]), "values": ["x"]},
            {"id": "ok", "kind": "range", "column_id": str(IDS["unidades"]), "maximum": "10"},
        ),
        COLUMNS,
    )
    assert [(p.rule_id, p.code) for p in problems] == [
        ("a", "COLUMN_TYPE_MISMATCH"),
        ("b", "COLUMN_TYPE_MISMATCH"),
        ("c", "UNKNOWN_COLUMN"),
        ("d", "INVALID_BOUND"),
        ("e", "INVALID_BOUND"),
        ("f", "COLUMN_TYPE_MISMATCH"),
    ]


def test_required_types_intersect_per_column() -> None:
    column = str(IDS["unidades"])
    result = required_types(
        rules(
            {"id": "r", "kind": "required", "column_id": column},
            {"id": "v", "kind": "allowed_values", "column_id": column, "values": ["1"]},
            {"id": "n", "kind": "range", "column_id": column, "minimum": "0"},
        )
    )
    assert result == {UUID(column): frozenset({"integer"})}


@pytest.mark.parametrize(
    "draft",
    [
        {"name": "x", "rules": [{"id": "Mal", "kind": "required", "column_id": str(uuid4())}]},
        {"name": "x", "rules": [{"id": "a", "kind": "required", "column_id": str(uuid4())}] * 2},
        {"name": "x", "rules": [{"id": "a", "kind": "range", "column_id": str(uuid4())}]},
        {
            "name": "x",
            "rules": [
                {"id": "a", "kind": "convertible", "column_id": str(uuid4()), "type": "decimal"}
            ],
        },
        {
            "name": "x",
            "rules": [{"id": "a", "kind": "unique_key", "column_ids": [], "source": "user"}],
        },
        {
            "name": "x",
            "rules": [
                {
                    "id": "a",
                    "kind": "unique_key",
                    "column_ids": [str(uuid4())],
                    "source": "semantic_key",
                }
            ],
        },
        {
            "name": "x",
            "rules": [
                {
                    "id": "a",
                    "kind": "allowed_values",
                    "column_id": str(uuid4()),
                    "values": ["a", "a"],
                }
            ],
        },
        {"name": "", "rules": []},
    ],
)
def test_invalid_drafts(draft: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RulesetDraft.model_validate(draft)
