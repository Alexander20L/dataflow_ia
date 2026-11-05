from collections.abc import Sequence
from typing import Any

from dataflow.modules.quality.contracts import WHITESPACE_CHARS, QualityIssue, QualityReport


def evaluate_quality(
    headers: list[str], rows: Sequence[Sequence[Any]], types: Sequence[str] | None = None
) -> QualityReport:
    """csv-quality-v1. Q-003 (sólo espacios) se evalúa únicamente en columnas de texto: una
    columna tipada no puede contener espacios. Sin tipos, todas las columnas son texto."""
    issues: list[QualityIssue] = []
    missing = whitespace = 0
    for index, name in enumerate(headers):
        text = types is None or types[index] == "string"
        null_rows = [i + 1 for i, row in enumerate(rows) if row[index] is None]
        space_rows = (
            [
                i + 1
                for i, row in enumerate(rows)
                if (value := row[index]) is not None and not value.strip(WHITESPACE_CHARS)
            ]
            if text
            else []
        )
        missing += len(null_rows)
        whitespace += len(space_rows)
        for rule, affected, description, action in [
            (
                "Q-001",
                null_rows,
                "Campo vacío (nulo).",
                "Revisar la fuente antes de imputar o excluir.",
            ),
            (
                "Q-003",
                space_rows,
                "Valor compuesto sólo de espacios.",
                "Revisar si el espacio es significativo antes de normalizar.",
            ),
        ]:
            if affected:
                issues.append(
                    QualityIssue(
                        id=f"{rule}-{index}",
                        rule=rule,
                        column=name,
                        severity="medium" if rule == "Q-001" else "low",
                        affected_rows=len(affected),
                        sample_row_numbers=affected[:5],
                        description=description,
                        proposed_action=action,
                    )
                )
    seen: set[tuple[str | None, ...]] = set()
    duplicates: list[int] = []
    for i, row in enumerate(rows):
        key = tuple(row)
        if key in seen:
            duplicates.append(i + 1)
        seen.add(key)
    if duplicates:
        issues.append(
            QualityIssue(
                id="Q-002",
                rule="Q-002",
                column=None,
                severity="medium",
                affected_rows=len(duplicates),
                sample_row_numbers=duplicates[:5],
                description="Fila idéntica a una anterior, considerando todas las columnas.",
                proposed_action="Confirmar si es una repetición válida antes de eliminarla.",
            )
        )
    cells = len(headers) * len(rows)
    return QualityReport(
        row_count=len(rows),
        cell_count=cells,
        missing_cells=missing,
        duplicate_rows=len(duplicates),
        whitespace_cells=whitespace,
        completeness_percent=round(100 * (cells - missing) / cells, 2) if cells else 0,
        issues=issues,
    )
