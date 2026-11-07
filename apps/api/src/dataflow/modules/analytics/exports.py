"""Resultado de análisis como CSV (Fase 9): cada cifra va acompañada de su `evidence_id`.

Columnas: posición (si hay ranking), dimensiones (valor canónico; vacío en el grupo sin valor)
y periodo (etiqueta), y por métrica su valor, su evidencia y, en @2, base, variación,
variación % y % del total, cada una con su evidencia.
"""

from collections.abc import Callable
from typing import Any, Literal

from dataflow.modules.analytics.contracts import (
    AnalysisResultV2,
    AnalysisResultV3,
    AnyAnalysisResult,
    ComparisonCell,
    ResultRow,
    ResultRowV2,
)
from dataflow.platform.csv_export import CsvProfile, write_csv

COMPARISON_NAMES = {
    "previous_period": "periodo anterior",
    "same_period_last_year": "mismo periodo del año anterior",
}
Getter = Callable[[ResultRow], str | None]
Kind = Literal["text", "decimal", "plain"]


def extended(row: ResultRow) -> ResultRowV2 | None:
    return row if isinstance(row, ResultRowV2) else None


def rank_of(evidence: bool) -> Getter:
    def get(row: ResultRow) -> str | None:
        rank = (extended(row) or ResultRowV2(key={}, labels={}, values={}, evidence={})).rank
        if rank is None:
            return None
        return rank.evidence if evidence else str(rank.position)

    return get


def label_of(key: str) -> Getter:
    return lambda row: row.labels.get(key)


def dimension_of(index: int) -> Getter:
    """Valor canónico de la dimensión; el grupo sin valor ({"missing": true}) queda vacío."""

    def get(row: ResultRow) -> str | None:
        value: Any = row.key["dimensions"][index]["value"]
        return None if isinstance(value, dict) else str(value)

    return get


def value_of(key: str) -> Getter:
    return lambda row: row.values.get(key)


def evidence_of(key: str) -> Getter:
    return lambda row: row.evidence.get(key)


def comparison_cell(row: ResultRow, key: str, kind: str) -> ComparisonCell | None:
    v2 = extended(row)
    if v2 is None:
        return None
    return {str(k): c for k, c in v2.comparisons.get(key, {}).items()}.get(kind)


def comparison_of(key: str, kind: str, field: str) -> Getter:
    def get(row: ResultRow) -> str | None:
        cell = comparison_cell(row, key, kind)
        value = getattr(cell, field) if cell else None
        return None if value is None else str(value)

    return get


def comparison_evidence(key: str, kind: str, cell_name: str) -> Getter:
    def get(row: ResultRow) -> str | None:
        cell = comparison_cell(row, key, kind)
        return cell.evidence[cell_name] if cell else None

    return get


def share_of(key: str, evidence: bool) -> Getter:
    def get(row: ResultRow) -> str | None:
        v2 = extended(row)
        share = v2.share.get(key) if v2 else None
        if share is None:
            return None
        return share.evidence if evidence else share.value

    return get


def analysis_csv(result: AnyAnalysisResult, profile: CsvProfile) -> bytes:
    columns: list[tuple[str, Getter, Kind]] = []
    v2 = result if isinstance(result, AnalysisResultV2 | AnalysisResultV3) else None
    if v2 and v2.ranking:
        columns.append(("Posición", rank_of(False), "plain"))
        columns.append(("Posición · evidence_id", rank_of(True), "plain"))
    for index, dimension in enumerate(result.dimensions):
        if dimension.key == "period":
            name = f"{dimension.name} ({dimension.time_grain})"
            columns.append((name, label_of(dimension.key), "plain"))
            continue
        kind: Kind = (
            "decimal"
            if dimension.technical_type == "decimal"
            else "text"
            if dimension.technical_type == "string"
            else "plain"
        )
        columns.append((dimension.name, dimension_of(index), kind))
    for metric in result.metrics:
        key = metric.key
        unit = metric.currency or metric.unit
        name = f"{metric.label} ({unit})" if unit else metric.label
        numeric: Kind = "decimal" if metric.scale is not None else "plain"
        columns.append((name, value_of(key), numeric))
        columns.append((f"{metric.label} · evidence_id", evidence_of(key), "plain"))
        if v2 is None:
            continue
        for comparison in v2.comparisons:
            label = f"{metric.label} · {COMPARISON_NAMES[comparison]}"
            cells: tuple[tuple[str, str, Kind, str], ...] = (
                ("", "base", numeric, "base"),
                (" · variación", "change", numeric, "change"),
                (" · variación %", "change_pct", "decimal", "change_pct"),
            )
            for suffix, field, cell_kind, evidence in cells:
                columns.append((label + suffix, comparison_of(key, comparison, field), cell_kind))
                columns.append(
                    (
                        f"{label}{suffix} · evidence_id",
                        comparison_evidence(key, comparison, evidence),
                        "plain",
                    )
                )
        if any(t.metric == key for t in v2.shares):
            columns.append((f"{metric.label} · % del total", share_of(key, False), "decimal"))
            columns.append(
                (f"{metric.label} · % del total · evidence_id", share_of(key, True), "plain")
            )
    return write_csv(
        [header for header, _, _ in columns],
        [[getter(row) for _, getter, _ in columns] for row in result.rows],
        profile,
        decimal_columns=frozenset(i for i, (_, _, k) in enumerate(columns) if k == "decimal"),
        text_columns=frozenset(i for i, (_, _, k) in enumerate(columns) if k == "text"),
    )
