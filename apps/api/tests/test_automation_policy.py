"""Fase 11B: evaluación pura de la política de automatización."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dataflow.modules.automation.contracts import (
    ColumnEffect,
    EffectFacts,
    PlannedStep,
    PolicyContent,
    PreviewFacts,
)
from dataflow.modules.automation.domain import evaluate

NAMES = {"c-id": "id", "c-imp": "importe", "c-reg": "region"}


def policy(**overrides: Any) -> PolicyContent:
    base: dict[str, Any] = {
        "enabled": True,
        "allowed_operations": ["cleaning.trim_whitespace", "cleaning.normalize_null_tokens"],
        "column_scopes": [
            {"operation": "cleaning.trim_whitespace", "columns": ["*"]},
            {"operation": "cleaning.normalize_null_tokens", "columns": ["region"]},
        ],
        "null_tokens_by_column": [{"column": "region", "tokens": ["NA", "-"]}],
    }
    return PolicyContent.model_validate({**base, **overrides})


def effect(**overrides: Any) -> EffectFacts:
    values: dict[str, Any] = {
        "input_rows": 100,
        "output_rows": 100,
        "excluded_rows": 0,
        "created_nulls": 0,
        "rounded_cells": 0,
        "columns": [ColumnEffect("c-imp", 3, 0)],
    }
    return EffectFacts(**{**values, **overrides})


def facts(steps: list[PlannedStep], fx: EffectFacts | None = None, **extra: Any) -> PreviewFacts:
    values: dict[str, Any] = {
        "execution_id": uuid4(),
        "project_id": uuid4(),
        "state": "succeeded",
        "plan_valid": True,
        "steps": steps,
        "column_names": NAMES,
        "effect_sha256": "e" * 64,
        "effect": effect() if fx is None else fx,
    }
    return PreviewFacts(**{**values, **extra})


TRIM = PlannedStep("trim", "cleaning.trim_whitespace", {"column_ids": ["c-imp"]})
TOKENS = PlannedStep(
    "null_tokens_1", "cleaning.normalize_null_tokens", {"column_ids": ["c-reg"], "tokens": ["NA"]}
)
DROP = PlannedStep(
    "drop_nulls",
    "cleaning.filter_rows",
    {"column_ids": ["c-imp"], "predicate": "is_null", "match": "any"},
)


def codes(result: Any) -> list[str]:
    return [r.code for r in result.reasons]


def test_defaults_are_disabled_and_authorize_nothing() -> None:
    content = PolicyContent()
    assert (content.enabled, content.allowed_operations, content.column_scopes) == (False, [], [])
    assert content.max_excluded_rows_pct == 0 and content.max_rounded_cells == 0
    assert codes(evaluate(None, facts([TRIM]))) == ["POLICY_MISSING"]
    assert codes(evaluate(content, facts([TRIM]))) == ["POLICY_DISABLED"]
    enabled = PolicyContent(enabled=True)
    assert codes(evaluate(enabled, facts([TRIM]))) == ["OPERATION_NOT_AUTHORIZED"]


def test_authorized_operations_within_scope_are_approved() -> None:
    result = evaluate(policy(), facts([TOKENS, TRIM]))
    assert result.decision == "approved" and result.reasons == []


def test_operation_without_scope_or_outside_scope_is_blocked() -> None:
    no_scope = policy(
        allowed_operations=["cleaning.trim_whitespace"], column_scopes=[], null_tokens_by_column=[]
    )
    assert codes(evaluate(no_scope, facts([TRIM]))) == ["COLUMN_NOT_AUTHORIZED"]
    narrow = policy(
        column_scopes=[
            {"operation": "cleaning.trim_whitespace", "columns": ["region"]},
            {"operation": "cleaning.normalize_null_tokens", "columns": ["region"]},
        ]
    )
    result = evaluate(narrow, facts([TRIM]))
    assert codes(result) == ["COLUMN_NOT_AUTHORIZED"] and result.reasons[0].column == "importe"


def test_unauthorized_operation_and_tokens() -> None:
    assert codes(evaluate(policy(), facts([DROP]))) == ["OPERATION_NOT_AUTHORIZED"]
    other = PlannedStep(
        "null_tokens_1",
        "cleaning.normalize_null_tokens",
        {"column_ids": ["c-reg"], "tokens": ["NA", "N/A"]},
    )
    assert codes(evaluate(policy(), facts([other]))) == ["TOKENS_NOT_AUTHORIZED"]


def test_identifier_conversion_is_never_automatic() -> None:
    cast = PlannedStep(
        "cast_1",
        "cleaning.cast",
        {"column_id": "c-id", "type": "integer", "confirm_identifier_conversion": True},
    )
    content = policy(
        allowed_operations=["cleaning.cast"],
        column_scopes=[{"operation": "cleaning.cast", "columns": ["*"]}],
        null_tokens_by_column=[],
    )
    assert codes(evaluate(content, facts([cast]))) == ["IDENTIFIER_CONVERSION"]


def test_barriers_are_exact_at_the_limit() -> None:
    content = policy(
        allowed_operations=["cleaning.filter_rows"],
        column_scopes=[{"operation": "cleaning.filter_rows", "columns": ["importe"]}],
        null_tokens_by_column=[],
        max_excluded_rows_pct=Decimal("5"),
    )
    at_limit = effect(output_rows=95, excluded_rows=5)
    assert evaluate(content, facts([DROP], at_limit)).decision == "approved"
    over = effect(output_rows=94, excluded_rows=6)
    result = evaluate(content, facts([DROP], over))
    assert codes(result) == ["EXCLUDED_ROWS_ABOVE_LIMIT"]
    assert result.reasons[0].measured == "6 filas (6.00 %)" and result.reasons[0].limit == "5 %"
    # Por defecto (0 %): cualquier exclusión exige revisión.
    zero = content.model_copy(update={"max_excluded_rows_pct": Decimal(0)})
    assert codes(evaluate(zero, facts([DROP], effect(output_rows=99, excluded_rows=1)))) == [
        "EXCLUDED_ROWS_ABOVE_LIMIT"
    ]


def test_created_nulls_are_checked_globally_and_per_column() -> None:
    content = policy(max_nulls_created_pct=Decimal("10"))
    # 9 nulos en 300 celdas (3 %) cumplen la barrera global, pero son el 9 % de «importe»
    # con 100 filas: cumple. Con 11 en una columna (11 %) se bloquea aunque el total sea 3,67 %.
    ok = effect(created_nulls=9, columns=[ColumnEffect("c-imp", 9, 9)])
    assert evaluate(content, facts([TRIM], ok)).decision == "approved"
    concentrated = effect(created_nulls=11, columns=[ColumnEffect("c-imp", 11, 11)])
    result = evaluate(content, facts([TRIM], concentrated))
    assert codes(result) == ["NULLS_CREATED_ABOVE_LIMIT"] and result.reasons[0].column == "importe"
    strict = policy()  # 0 %: un solo nulo creado exige revisión
    one = effect(created_nulls=1, columns=[ColumnEffect("c-imp", 1, 1)])
    assert codes(evaluate(strict, facts([TRIM], one))) == [
        "NULLS_CREATED_ABOVE_LIMIT",
        "NULLS_CREATED_ABOVE_LIMIT",
    ]


def test_rounding_output_rows_plan_and_effect_state() -> None:
    assert codes(evaluate(policy(), facts([TRIM], effect(rounded_cells=1)))) == [
        "ROUNDED_CELLS_ABOVE_LIMIT"
    ]
    empty = effect(input_rows=1, output_rows=0, excluded_rows=1)
    assert "OUTPUT_ROWS_BELOW_MINIMUM" in codes(evaluate(policy(), facts([TRIM], empty)))
    assert codes(evaluate(policy(), facts([TRIM], plan_valid=False))) == ["PLAN_INVALID"]
    pending = evaluate(policy(), facts([TRIM], state="running", effect=None, effect_sha256=None))
    assert codes(pending) == ["EFFECT_NOT_READY"]
    legacy = evaluate(policy(), facts([TRIM], effect(columns=None)))
    assert codes(legacy) == ["EFFECT_BREAKDOWN_MISSING"]


@pytest.mark.parametrize(
    "content",
    [
        {"allowed_operations": ["cleaning.trim_whitespace", "cleaning.trim_whitespace"]},
        {"column_scopes": [{"operation": "cleaning.cast", "columns": ["*"]}]},
        {
            "allowed_operations": ["cleaning.trim_whitespace"],
            "column_scopes": [{"operation": "cleaning.trim_whitespace", "columns": ["*", "a"]}],
        },
        {"null_tokens_by_column": [{"column": "a", "tokens": ["x", "x"]}]},
        {"max_excluded_rows_pct": "100.01"},
        {"max_nulls_created_pct": "-1"},
        {"allowed_operations": ["cleaning.unknown"]},
        {"unexpected": True},
    ],
)
def test_invalid_policies_are_rejected(content: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PolicyContent.model_validate(content)
