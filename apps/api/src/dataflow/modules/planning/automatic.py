"""Plan analítico automático (`automatic-plan-v1`, Fase 15).

Convierte la interpretación (`automatic-interpretation-v2`) en un plan acotado: qué análisis
del catálogo automático tienen sentido, con qué medida y dimensión, en qué orden y cuáles se
omiten y por qué. Puro: sin datos, Polars ni otros módulos salvo contratos.
"""

import re
import unicodedata
from collections.abc import Mapping

from dataflow.modules.planning.contracts import AnalysisPlan, PlannedAnalysis
from dataflow.modules.understanding.contracts import AnalyticalColumn, AnalyticalInterpretation

MAX_ANALYSES = 12
MAX_BREAKDOWNS = 4
MIN_GROUPS, MAX_GROUPS = 2, 50
MIN_ANOMALY_MONTHS = 6
SEASONAL_MONTHS = 24
# Dimensiones que un analista suele examinar primero (producto, territorio, canal, categoría).
FIRST = {"product", "producto", "articulo", "item", "sku", "category", "categoria", "familia"}
SECOND = {"region", "zona", "pais", "country", "city", "ciudad", "channel", "canal", "store"}
SECOND |= {"tienda", "segment", "segmento", "customer", "cliente", "vendedor", "seller"}


def tokens(name: str) -> set[str]:
    spaced = re.sub(r"([a-záéíóúñ])([A-Z])", r"\1 \2", name)
    normalized = unicodedata.normalize("NFKD", spaced.casefold())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return set(re.findall(r"[a-z0-9]+", plain))


def add_months(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7]) - 1 + months
    return f"{year + month // 12:04d}-{month % 12 + 1:02d}"


def present_months(analysis: AnalyticalInterpretation) -> list[str] | None:
    """Meses con datos, o None si la lista de faltantes está truncada (no se puede saber)."""
    time = analysis.time
    if time is None or time.first is None or time.last is None:
        return []
    if time.missing_count != len(time.missing):
        return None
    months: list[str] = []
    current = time.first
    while current <= time.last and len(months) < 1200:
        if current not in time.missing:
            months.append(current)
        current = add_months(current, 1)
    return months


def summable(analysis: AnalyticalInterpretation) -> list[AnalyticalColumn]:
    return sorted(
        (
            c
            for c in analysis.columns
            if c.role == "measure" and c.additivity == "additive" and c.currency != "ambiguous"
        ),
        key=lambda c: (not c.monetary, c.ordinal),
    )


def plan_analyses(
    analysis: AnalyticalInterpretation, distinct: Mapping[str, int], row_count: int
) -> AnalysisPlan:
    """`distinct`: valores distintos por columna (del perfil). Decide sin mirar los datos."""
    items: list[PlannedAnalysis] = []
    measures = summable(analysis)
    primary = measures[0] if measures else None
    time = analysis.time
    blocked = {name: item for item in analysis.limited_analyses for name in item.columns}

    def add(
        kind: str,
        title: str,
        priority: int,
        requirements: list[str],
        reason: str,
        accepted: bool,
        measure: str | None = None,
        dimension: str | None = None,
        weight: str | None = None,
        key: str | None = None,
    ) -> None:
        items.append(
            PlannedAnalysis.model_validate(
                {
                    "id": key or kind,
                    "kind": kind,
                    "title": title,
                    "measure": measure,
                    "weight": weight,
                    "dimension": dimension,
                    "priority": priority,
                    "requirements": requirements,
                    "status": "accepted" if accepted else "omitted",
                    "reason": reason,
                }
            )
        )

    name = primary.name if primary else None
    no_measure = (
        "No hay una medida sumable con una sola moneda: sólo se describen conteos."
        if primary is None
        else ""
    )
    # 1. Evolución mensual.
    if time is None:
        add(
            "evolution",
            "Evolución mensual",
            1,
            ["Eje temporal mensual", "Medida sumable"],
            "No hay fecha ni Año + Mes reconocibles: no se analiza la evolución.",
            False,
            name,
        )
    elif primary is None:
        add(
            "evolution",
            "Evolución mensual",
            1,
            ["Eje temporal mensual", "Medida sumable"],
            no_measure,
            False,
        )
    else:
        gaps = f" Meses sin datos: {', '.join(time.missing)}." if time.missing_count else ""
        add(
            "evolution",
            f"Evolución mensual de {primary.name}",
            1,
            ["Eje temporal mensual", f"{primary.name} sumable"],
            f"Hay {time.periods} meses con datos y una medida sumable.{gaps}",
            time.periods >= 2,
            name,
        )
    # 2. Comparación interanual, sólo entre meses presentes en ambos años.
    months = present_months(analysis)
    comparable = (
        [m for m in months if add_months(m, -12) in set(months)] if months is not None else []
    )
    if time is not None and primary is not None:
        has_comparable = bool(comparable)
        add(
            "year_over_year",
            f"Comparación interanual de {primary.name}",
            2,
            ["Al menos un mes presente en dos años consecutivos"],
            f"{len(comparable)} meses comparables con el mismo mes del año anterior."
            if has_comparable
            else (
                "No hay meses presentes en dos años consecutivos: no se compara entre años."
                if months is not None
                else "Faltan demasiados meses para saber cuáles son comparables."
            ),
            has_comparable,
            name,
        )
    # 3. Desgloses por dimensión (participación, concentración y ranking).
    candidates = [c for c in analysis.columns if c.role in {"dimension", "identifier"}]

    def rank(column: AnalyticalColumn) -> tuple[int, int]:
        names = tokens(column.name)
        return (0 if names & FIRST else 1 if names & SECOND else 2, column.ordinal)

    shown = 0
    reported: set[str] = set()
    for column in sorted(candidates, key=rank):
        groups = distinct.get(column.name, 0)
        key = f"breakdown:{column.name}"
        title = f"{name or 'Registros'} por {column.name}"
        requirements = [f"Entre {MIN_GROUPS} y {MAX_GROUPS} grupos", "Identidad única por grupo"]
        if column.name in blocked:
            limited = blocked[column.name]
            if limited.subject not in reported:
                reported.add(limited.subject)
                add(
                    "breakdown",
                    limited.subject,
                    3,
                    requirements,
                    limited.reason,
                    False,
                    name,
                    column.name,
                    key=key,
                )
            continue
        if primary is None:
            add("breakdown", title, 3, requirements, no_measure, False, None, column.name, key=key)
            continue
        if not MIN_GROUPS <= groups <= MAX_GROUPS:
            if column.role == "dimension":
                add(
                    "breakdown",
                    title,
                    3,
                    requirements,
                    f"{groups} grupos: fuera del rango útil para comparar ({MIN_GROUPS}–"
                    f"{MAX_GROUPS}).",
                    False,
                    name,
                    column.name,
                    key=key,
                )
            continue
        if shown >= MAX_BREAKDOWNS:
            add(
                "breakdown",
                title,
                3,
                requirements,
                f"Se priorizaron otras {MAX_BREAKDOWNS} dimensiones.",
                False,
                name,
                column.name,
                key=key,
            )
            continue
        shown += 1
        add(
            "breakdown",
            title,
            3 + shown,
            requirements,
            f"{groups} grupos con identidad única: participación, concentración y ranking.",
            True,
            name,
            column.name,
            key=key,
        )
    # 4. Promedio ponderado: precio = importe ÷ cantidad cuando la relación está comprobada.
    roles = {c.name: c for c in analysis.columns}
    for relationship in analysis.relationships:
        target = roles.get(relationship.target)
        factors = [roles[f] for f in relationship.factors if f in roles]
        rate = next((f for f in factors if f.additivity == "non_additive"), None)
        weight = next((f for f in factors if f.additivity == "additive"), None)
        if target is None or rate is None or weight is None:
            continue
        if target not in measures:
            continue
        add(
            "weighted_average",
            f"{rate.name} medio ponderado por {weight.name}",
            2,
            [f"{relationship.target} = {' × '.join(relationship.factors)} comprobado"],
            f"{rate.name} no se suma: su media ponderada es {target.name} ÷ {weight.name} "
            f"(relación comprobada en {relationship.matching_rows} de "
            f"{relationship.compared_rows} filas).",
            True,
            target.name,
            weight=weight.name,
            key=f"weighted:{rate.name}",
        )
    for column in analysis.columns:
        if column.additivity == "non_additive" and not any(
            item.id == f"weighted:{column.name}" for item in items
        ):
            add(
                "weighted_average",
                f"{column.name} medio ponderado",
                2,
                ["Relación importe = cantidad × precio comprobada"],
                f"No se comprobó qué cantidad pondera {column.name}: sólo su promedio simple.",
                False,
                key=f"weighted:{column.name}",
            )
    # 5. Estacionalidad: al menos 24 meses seguidos.
    if time is not None and primary is not None:
        consecutive = time.periods if time.missing_count == 0 else 0
        add(
            "seasonality",
            f"Estacionalidad de {primary.name}",
            6,
            [f"{SEASONAL_MONTHS} meses seguidos con datos"],
            f"{time.periods} meses seguidos: se compara cada mes del año con su media."
            if consecutive >= SEASONAL_MONTHS
            else f"Hacen falta {SEASONAL_MONTHS} meses seguidos; hay {time.periods} meses"
            + (f" y faltan {time.missing_count}." if time.missing_count else "."),
            consecutive >= SEASONAL_MONTHS,
            name,
        )
    # 6. Anomalías mensuales con método explícito.
    if time is not None and primary is not None:
        enough = time.periods >= MIN_ANOMALY_MONTHS
        add(
            "anomalies",
            f"Meses atípicos de {primary.name}",
            3,
            [f"Al menos {MIN_ANOMALY_MONTHS} meses con datos"],
            "Mediana ± 3 desviaciones absolutas (MAD) de los totales mensuales; los factores "
            "se presentan como asociación, no como causa."
            if enough
            else f"Hay {time.periods} meses: no bastan para distinguir un mes atípico.",
            enough,
            name,
        )
    chosen = sorted(
        (item for item in items if item.status == "accepted"), key=lambda i: (i.priority, i.id)
    )
    omitted = [item for item in items if item.status == "omitted"]
    for item in chosen[MAX_ANALYSES:]:
        omitted.append(
            item.model_copy(
                update={"status": "omitted", "reason": "Límite de análisis por carga alcanzado."}
            )
        )
    chosen = chosen[:MAX_ANALYSES]
    return AnalysisPlan(
        measure=name,
        accepted=chosen,
        omitted=omitted,
        max_analyses=MAX_ANALYSES,
        estimated_cells=row_count * max(1, len(chosen)),
    )
