"""Evaluación de csv-quality-v2 sobre todas las filas (se ejecuta en el subproceso aislado).

Primero las reglas técnicas exactas de csv-quality-v1 (origin: technical); después las reglas
del usuario (origin: user). La completitud técnica no incluye reglas de negocio.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from dataflow.modules.quality.domain import default_description, parse_bound, rule_columns
from dataflow.modules.quality.rules_contracts import (
    AllowedValuesRule,
    ConvertibleRule,
    QualityRulesReport,
    RangeRule,
    RequiredRule,
    Rule,
    RuleIssue,
    RulesetReference,
    TechnicalSummary,
    UniqueKeyRule,
    UserSummary,
)
from dataflow.modules.quality.technical import evaluate_quality
from dataflow.platform.conversion import Failed, convert
from dataflow.platform.tabular import display_cell


def violations(
    rule: Rule,
    rows: Sequence[Sequence[Any]],
    positions: list[int],
    types: list[tuple[str, dict[str, Any]]],
) -> list[int]:
    """Números de registro (1-based) que incumplen la regla."""
    if isinstance(rule, RequiredRule):
        index = positions[0]
        return [n + 1 for n, row in enumerate(rows) if row[index] is None]
    if isinstance(rule, UniqueKeyRule):
        seen: set[tuple[Any, ...]] = set()
        result = []
        for n, row in enumerate(rows):
            key = tuple(row[index] for index in positions)
            if any(value is None for value in key) or key in seen:
                result.append(n + 1)
            seen.add(key)
        return result
    index = positions[0]
    data_type, parameters = types[index]
    if isinstance(rule, RangeRule):
        low = parse_bound(rule.minimum, data_type) if rule.minimum is not None else None
        high = parse_bound(rule.maximum, data_type) if rule.maximum is not None else None
        result = []
        for n, row in enumerate(rows):
            value = row[index]
            if value is None:
                continue
            current: Decimal | date = value if isinstance(value, date) else Decimal(value)
            if (low is not None and current < low) or (  # type: ignore[operator]
                high is not None and current > high  # type: ignore[operator]
            ):
                result.append(n + 1)
        return result
    if isinstance(rule, AllowedValuesRule):
        allowed = set(rule.values)
        return [
            n + 1
            for n, row in enumerate(rows)
            if row[index] is not None
            and display_cell(row[index], data_type, parameters) not in allowed  # type: ignore[arg-type,operator]
        ]
    assert isinstance(rule, ConvertibleRule)
    return [
        n + 1
        for n, row in enumerate(rows)
        if row[index] is not None and isinstance(convert(row[index], rule.type, rule.scale), Failed)
    ]


def evaluate_rules(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    columns: list[dict[str, Any]],
    rules: list[Rule],
    reference: RulesetReference,
) -> QualityRulesReport:
    types = [
        (str(c.get("technical_type", "string")), dict(c.get("type_parameters", {})))
        for c in columns
    ]
    if [str(c["name"]) for c in columns] != headers:
        raise ValueError("El esquema no coincide con la tabla.")
    technical = evaluate_quality(headers, rows, [t for t, _ in types])
    ids = {UUID(str(c["id"])): index for index, c in enumerate(columns)}
    issues = [
        RuleIssue(
            id=issue.id,
            origin="technical",
            rule=issue.rule,
            rule_id=None,
            column_ids=[str(columns[headers.index(issue.column)]["id"])] if issue.column else [],
            columns=[issue.column] if issue.column else [],
            severity=issue.severity,
            affected_rows=issue.affected_rows,
            sample_row_numbers=issue.sample_row_numbers,
            description=issue.description,
        )
        for issue in technical.issues
    ]
    failed = 0
    for rule in rules:
        positions = [ids[column] for column in rule_columns(rule)]
        affected = violations(rule, rows, positions, types)
        if not affected:
            continue
        failed += 1
        names = [headers[index] for index in positions]
        issues.append(
            RuleIssue(
                id=f"U-{rule.id}",
                origin="user",
                rule=rule.kind,
                rule_id=rule.id,
                column_ids=[str(column) for column in rule_columns(rule)],
                columns=names,
                severity=rule.severity,
                affected_rows=len(affected),
                sample_row_numbers=affected[:5],
                description=rule.description or default_description(rule, names),
            )
        )
    return QualityRulesReport(
        ruleset=reference,
        row_count=technical.row_count,
        cell_count=technical.cell_count,
        technical=TechnicalSummary(
            completeness_percent=technical.completeness_percent,
            missing_cells=technical.missing_cells,
            duplicate_rows=technical.duplicate_rows,
            whitespace_cells=technical.whitespace_cells,
        ),
        user=UserSummary(rules_evaluated=len(rules), rules_failed=failed),
        issues=issues,
    )
