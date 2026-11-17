"""Calidad analítica automática (`automatic-quality-v1`, Fase 14).

Juzga la evidencia de la interpretación (`automatic-interpretation-v2`) y mide valores
imposibles y atípicos: qué problemas cambian las conclusiones y qué análisis afectan. Pura y
sin efectos: nunca corrige, rellena, deduplica ni excluye registros.
"""

import re
from collections.abc import Sequence
from decimal import Decimal

from dataflow.modules.quality.contracts import AnalyticalFinding, AnalyticalQuality
from dataflow.modules.understanding.contracts import AnalyticalInterpretation

NUMBER = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?\Z")
OUTLIER_FACTOR = Decimal(3)  # vallas de Tukey amplias: Q1 − 3·IQR y Q3 + 3·IQR
MIN_OUTLIER_VALUES = 8


def number(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None and NUMBER.fullmatch(value) else None


def quartiles(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Cuartiles por rango más cercano sobre los valores ordenados (método explícito)."""
    ordered = sorted(values)

    def rank(fraction: Decimal) -> Decimal:
        index = int((fraction * (len(ordered) - 1)).to_integral_value())
        return ordered[index]

    return rank(Decimal("0.25")), rank(Decimal("0.75"))


def assess(
    analysis: AnalyticalInterpretation, cells: Sequence[Sequence[str | None]]
) -> AnalyticalQuality:
    findings: list[AnalyticalFinding] = []

    def add(
        check: str,
        title: str,
        severity: str,
        columns: list[str],
        affected: int,
        samples: list[int],
        evidence: list[str],
        analyses: list[str],
    ) -> None:
        findings.append(
            AnalyticalFinding.model_validate(
                {
                    "id": f"{check}-{len(findings) + 1}",
                    "check": check,
                    "title": title,
                    "severity": severity,
                    "columns": columns,
                    "affected_rows": affected,
                    "sample_row_numbers": samples[:5],
                    "evidence": evidence,
                    "affected_analyses": analyses,
                }
            )
        )

    measures = [c for c in analysis.columns if c.role == "measure"]
    totals = [f"Totales de {c.name}" for c in measures if c.additivity == "additive"]
    time = analysis.time
    evolution = ["Evolución mensual", "Comparación entre periodos"]

    for key in analysis.keys:
        if not key.unique:
            add(
                "AQ-001",
                f"Filas que repiten {', '.join(key.columns)}",
                "warning",
                key.columns,
                key.duplicate_rows,
                key.duplicate_sample_rows,
                [
                    key.evidence,
                    "Pueden ser duplicados o registros legítimos: no se eliminaron.",
                ],
                totals,
            )
    for dependency in analysis.dependencies:
        if dependency.conflicting_values:
            add(
                "AQ-002",
                f"{dependency.determinant} con varios {dependency.dependent}",
                "blocking",
                [dependency.determinant, dependency.dependent],
                dependency.conflicting_rows,
                dependency.sample_row_numbers,
                [
                    f"{dependency.conflicting_values} de {dependency.determinant_values} valores "
                    f"de {dependency.determinant} tienen más de un {dependency.dependent}.",
                    *[f"Ejemplo: {example}." for example in dependency.examples],
                    "No se unificaron nombres: podría ser un cambio legítimo o un error.",
                ],
                [f"Análisis por {dependency.determinant} o {dependency.dependent}"],
            )
    if time is not None and time.missing_count:
        add(
            "AQ-003",
            "Meses sin registros",
            "warning",
            time.columns,
            0,
            [],
            [
                f"Entre {time.first} y {time.last} faltan {time.missing_count} meses: "
                f"{', '.join(time.missing)}.",
                "No se rellenaron con cero: las comparaciones que los incluyan no son válidas.",
            ],
            evolution,
        )
    if time is not None and time.incomplete:
        add(
            "AQ-004",
            "Meses posiblemente incompletos",
            "warning",
            time.columns,
            0,
            [],
            [
                f"{', '.join(time.incomplete)} tiene menos de la mitad de registros que un mes "
                "típico: podría ser un corte parcial.",
            ],
            evolution,
        )
    if time is not None and time.unparsed_rows:
        add(
            "AQ-005",
            "Periodos no reconocidos",
            "warning",
            time.columns,
            time.unparsed_rows,
            time.unparsed_sample_rows,
            [f"{time.unparsed_rows} filas tienen año, mes o fecha que no se pudo interpretar."],
            evolution,
        )
    for column in measures:
        quantity = column.unit_label == "unidades"
        price = column.monetary and column.additivity == "non_additive"
        if not (quantity or price):
            continue
        negatives = [
            row_number
            for row_number, row in enumerate(cells, start=1)
            if (value := number(row[column.ordinal])) is not None and value < 0
        ]
        if negatives:
            add(
                "AQ-006",
                f"Valores negativos en {column.name}",
                "warning",
                [column.name],
                len(negatives),
                negatives,
                [
                    f"{len(negatives)} valores negativos en una "
                    f"{'cantidad' if quantity else 'tarifa o precio'}.",
                    "Podrían ser devoluciones o errores: no se corrigieron.",
                ],
                [f"Totales de {column.name}"],
            )
    for relationship in analysis.relationships:
        exceptions = relationship.compared_rows - relationship.matching_rows
        if exceptions:
            add(
                "AQ-006",
                f"{relationship.target} no coincide con {' × '.join(relationship.factors)}",
                "warning",
                [relationship.target, *relationship.factors],
                exceptions,
                relationship.exception_sample_rows,
                [
                    f"La relación se cumple en {relationship.matching_rows} de "
                    f"{relationship.compared_rows} filas (tolerancia {relationship.tolerance}).",
                    "Las filas que no la cumplen podrían tener descuentos o errores.",
                ],
                [f"Totales de {relationship.target}"],
            )
    for column in measures:
        values = [
            (row_number, value)
            for row_number, row in enumerate(cells, start=1)
            if (value := number(row[column.ordinal])) is not None
        ]
        if len(values) < MIN_OUTLIER_VALUES:
            continue
        q1, q3 = quartiles([value for _, value in values])
        spread = q3 - q1
        if spread <= 0:
            continue
        low, high = q1 - OUTLIER_FACTOR * spread, q3 + OUTLIER_FACTOR * spread
        outliers = [row_number for row_number, value in values if value < low or value > high]
        if outliers:
            add(
                "AQ-007",
                f"Valores atípicos en {column.name}",
                "info",
                [column.name],
                len(outliers),
                outliers,
                [
                    f"{len(outliers)} valores fuera de [{format(low, 'f')}, {format(high, 'f')}] "
                    "(Q1 − 3·IQR, Q3 + 3·IQR).",
                    "Es una observación para investigar, no un error: se conservan.",
                ],
                [f"Promedios y totales de {column.name}"],
            )
    for column in measures:
        if column.currency == "ambiguous":
            add(
                "AQ-008",
                f"Varias monedas en {column.name}",
                "blocking",
                [column.name],
                0,
                [],
                ["La fuente tiene más de una moneda y no se aplican tipos de cambio."],
                [f"Totales de {column.name}"],
            )
    return AnalyticalQuality(
        findings=findings,
        blocking=sum(1 for f in findings if f.severity == "blocking"),
        warnings=sum(1 for f in findings if f.severity == "warning"),
        observations=sum(1 for f in findings if f.severity == "info"),
    )
