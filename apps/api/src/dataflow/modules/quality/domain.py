"""Reglas puras de csv-quality-v2: tipos que exige cada regla y validación contra un esquema.

Sin Polars ni SQL. La evaluación sobre datos vive en `rules_engine.py` (subproceso).
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from dataflow.modules.quality.rules_contracts import (
    AllowedValuesRule,
    ConvertibleRule,
    RangeRule,
    RequiredRule,
    Rule,
    RulesetProblem,
    UniqueKeyRule,
)
from dataflow.platform.conversion import Converted, convert
from dataflow.platform.data_types import ALL_TYPES, DataType

DECIMAL = re.compile(r"[+-]?(0|[1-9][0-9]*)(\.[0-9]+)?", re.ASCII)
RANGE_TYPES: frozenset[DataType] = frozenset({"integer", "decimal", "date"})
VALUE_TYPES: frozenset[DataType] = frozenset({"string", "integer", "boolean"})
TEXT_TYPES: frozenset[DataType] = frozenset({"string"})


def rule_columns(rule: Rule) -> list[UUID]:
    return list(rule.column_ids) if isinstance(rule, UniqueKeyRule) else [rule.column_id]


def allowed_types(rule: Rule) -> frozenset[DataType]:
    if isinstance(rule, RangeRule):
        return RANGE_TYPES
    if isinstance(rule, AllowedValuesRule):
        return VALUE_TYPES
    if isinstance(rule, ConvertibleRule):
        return TEXT_TYPES
    return ALL_TYPES  # obligatoriedad y unicidad admiten cualquier tipo


def required_types(rules: list[Rule]) -> dict[UUID, frozenset[DataType]]:
    """Tipos admitidos por columna para todo el conjunto (intersección entre reglas)."""
    result: dict[UUID, frozenset[DataType]] = {}
    for rule in rules:
        for column in rule_columns(rule):
            result[column] = result.get(column, ALL_TYPES) & allowed_types(rule)
    return result


def parse_bound(text: str, data_type: str) -> Decimal | date | None:
    if data_type == "date":
        parsed = convert(text, "date")
        return parsed.value if isinstance(parsed, Converted) else None  # type: ignore[return-value]
    return Decimal(text) if DECIMAL.fullmatch(text) else None


def validate_rules(rules: list[Rule], columns: list[dict[str, Any]]) -> list[RulesetProblem]:
    """Problemas de un conjunto frente al esquema de una tabla (IDs y tipos)."""
    types = {UUID(str(c["id"])): str(c.get("technical_type", "string")) for c in columns}
    names = {UUID(str(c["id"])): str(c["name"]) for c in columns}
    problems: list[RulesetProblem] = []
    for rule in rules:
        for column in rule_columns(rule):
            if column not in types:
                problems.append(
                    RulesetProblem(
                        rule_id=rule.id,
                        code="UNKNOWN_COLUMN",
                        message=f"La regla «{rule.id}» usa una columna que no existe en la tabla.",
                    )
                )
            elif types[column] not in allowed_types(rule):
                problems.append(
                    RulesetProblem(
                        rule_id=rule.id,
                        code="COLUMN_TYPE_MISMATCH",
                        message=f"La regla «{rule.id}» ({rule.kind}) no admite «{names[column]}» "
                        f"de tipo {types[column]}.",
                    )
                )
        if isinstance(rule, RangeRule) and rule.column_id in types:
            bounds = [
                parse_bound(value, types[rule.column_id])
                for value in (rule.minimum, rule.maximum)
                if value is not None
            ]
            if any(bound is None for bound in bounds) or (
                len(bounds) == 2 and bounds[0] > bounds[1]  # type: ignore[operator]
            ):
                problems.append(
                    RulesetProblem(
                        rule_id=rule.id,
                        code="INVALID_BOUND",
                        message=f"Los límites de «{rule.id}» no son válidos para "
                        f"{types[rule.column_id]} (número con punto o fecha AAAA-MM-DD; "
                        "mínimo ≤ máximo).",
                    )
                )
    return problems


def default_description(rule: Rule, names: list[str]) -> str:
    joined = ", ".join(names)
    if isinstance(rule, RequiredRule):
        return f"«{joined}» es obligatoria y está vacía."
    if isinstance(rule, UniqueKeyRule):
        return f"La clave ({joined}) se repite o tiene nulos."
    if isinstance(rule, RangeRule):
        low = rule.minimum if rule.minimum is not None else "−∞"
        high = rule.maximum if rule.maximum is not None else "+∞"
        return f"«{joined}» fuera del rango [{low}, {high}]."
    if isinstance(rule, AllowedValuesRule):
        return f"«{joined}» tiene un valor fuera del catálogo permitido."
    assert isinstance(rule, ConvertibleRule)
    return f"«{joined}» no cumple el formato {rule.format}."
