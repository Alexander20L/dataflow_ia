"""Consultas de seguimiento de la investigación (`analytics.followup@1`, Fase 16).

Catálogo cerrado `investigation-followup-v1`, calculado con el mismo motor y las mismas métricas
virtuales que `analytics.automatic@1`:

- `month_by_group`: en un mes, qué grupos de una dimensión se apartan de su mediana mensual.
- `change_by_group`: reparto de la variación interanual entre los grupos (meses comparables).
- `group_evolution`: evolución mensual de un grupo y su peso en el total.

Las consultas ya llegan validadas; si no hay datos que las sustenten el resultado es `empty`
con su motivo. Nada se rellena y una asociación no es una causa.
"""

from collections.abc import Sequence
from decimal import Decimal

from dataflow.modules.analytics.automatic import (
    Builder,
    Runner,
    Table,
    es,
    median,
    monthly_series,
    number,
    pct,
    rounded,
    signed,
)
from dataflow.modules.analytics.contracts import (
    AnalysisResultV2,
    AutomaticInsight,
    AutomaticScope,
    FollowUpBatch,
    FollowUpQuery,
    FollowUpResult,
    InsightChart,
    InsightPoint,
)
from dataflow.modules.understanding.contracts import AnalyticalInterpretation
from dataflow.platform.decimal_context import exact_context

ASSOCIATION = "Es una asociación para investigar, no una causa demostrada."


def by_group(result: AnalysisResultV2) -> dict[str, dict[str, tuple[Decimal, str]]]:
    """grupo → mes → (valor, evidencia del motor)."""
    groups: dict[str, dict[str, tuple[Decimal, str]]] = {}
    for row in result.rows:
        group, month = row.labels.get("d0"), row.labels.get("period")
        value = number(row.values.get("m0"))
        if group is None or month is None or value is None or not str(month)[:4].isdigit():
            continue
        groups.setdefault(str(group), {})[str(month)] = (value, row.evidence["m0"])
    return groups


def empty(query: FollowUpQuery, reason: str) -> FollowUpResult:
    return FollowUpResult(key=query.key, query=query, status="empty", reason=reason)


def month_by_group(
    builder: Builder, query: FollowUpQuery, result: AnalysisResultV2
) -> FollowUpResult:
    month, measure, dimension = query.month or "", query.measure, query.dimension
    rows = []
    for group, months in by_group(result).items():
        if month not in months:
            continue
        value, evidence = months[month]
        center = median([item[0] for item in months.values()])
        with exact_context():
            rows.append((group, value, center, value - center, evidence, len(months)))
    if not rows:
        return empty(query, f"Ningún grupo de {dimension} tiene datos en {month}.")
    rows.sort(key=lambda row: (-abs(row[3]), row[0]))
    figures = []
    for group, value, center, shift, evidence, count in rows[:3]:
        figures.append(
            builder.figure(
                query.key,
                f"{group}:value",
                f"{measure} de {dimension} = {group} en {month}",
                str(value),
                "number",
                "analytics.query@2: suma del grupo en el mes",
                {"query": query.key, "engine_evidence_id": evidence},
            )
        )
        figures.append(
            builder.figure(
                query.key,
                f"{group}:shift",
                f"Desvío de {dimension} = {group} frente a su mediana mensual",
                rounded(shift),
                "number",
                "valor del grupo en el mes − mediana de sus meses con dato",
                {"query": query.key, "group": group, "median": rounded(center), "months": count},
            )
        )
    first = rows[0]
    statement = (
        f"En {month}, el mayor desvío de {measure} por {dimension} es {first[0]}: "
        f"{es(first[1])} frente a su mediana mensual de {es(rounded(first[2]))} "
        f"({signed(rounded(first[3]))})."
    )
    if len(rows) > 1:
        second = rows[1]
        statement += f" Le sigue {second[0]} ({signed(rounded(second[3]))})."
    insight = AutomaticInsight(
        id=f"{query.key}:summary",
        analysis_id=query.key,
        kind=query.kind,
        title=f"{month}: {measure} por {dimension} frente a su nivel habitual",
        statement=statement,
        importance=60,
        figures=figures,
        chart=InsightChart(
            type="bar",
            title=f"Desvío de {measure} en {month} por {dimension}",
            unit="number",
            points=[
                InsightPoint(label=row[0], value=rounded(row[3]), evidence_id=None)
                for row in rows[:12]
            ],
        ),
        coverage=f"{len(rows)} grupos con datos en {month}",
        notes=["La mediana se calcula con los meses en que el grupo tiene datos.", ASSOCIATION],
    )
    return FollowUpResult(
        key=query.key,
        query=query,
        status="computed",
        insight=insight,
        evidence=builder.evidence,
    )


def change_by_group(
    builder: Builder,
    query: FollowUpQuery,
    totals: AnalysisResultV2,
    result: AnalysisResultV2,
) -> FollowUpResult:
    year, measure, dimension = query.year or 0, query.measure, query.dimension
    previous = year - 1
    present = {label for label, *_ in monthly_series(totals)}
    months = sorted(
        label
        for label in present
        if label.startswith(f"{year}-") and f"{previous}{label[4:]}" in present
    )
    if not months:
        return empty(query, f"No hay meses de {year} con dato también en {previous}.")
    rows = []
    for group, values in by_group(result).items():
        with exact_context():
            current = sum((values[m][0] for m in months if m in values), Decimal(0))
            base = sum(
                (values[f"{previous}{m[4:]}"][0] for m in months if f"{previous}{m[4:]}" in values),
                Decimal(0),
            )
            rows.append((group, current, base, current - base))
    if not rows:
        return empty(query, f"Ningún grupo de {dimension} tiene datos en esos meses.")
    with exact_context():
        total = sum((row[3] for row in rows), Decimal(0))
    rows.sort(key=lambda row: (-abs(row[3]), row[0]))
    inputs = {"query": query.key, "months": months, "groups": [row[0] for row in rows]}
    figures = [
        builder.figure(
            query.key,
            "total",
            f"Variación de {measure} {year} frente a {previous} (meses comparables)",
            str(total),
            "number",
            "Σ (actual − base) de los grupos en los meses comparables",
            inputs,
        )
    ]
    parts = []
    for group, current, base, diff in rows[:3]:
        share = pct(diff, total) if total else None
        figures.append(
            builder.figure(
                query.key,
                f"{group}:diff",
                f"Variación de {dimension} = {group}",
                str(diff),
                "number",
                f"Σ {year} − Σ {previous} del grupo en los meses comparables",
                {**inputs, "group": group, "current": str(current), "base": str(base)},
            )
        )
        if share is not None:
            figures.append(
                builder.figure(
                    query.key,
                    f"{group}:contribution",
                    f"Aporte de {group} a la variación",
                    share,
                    "percent",
                    "variación del grupo ÷ variación total × 100, HALF_EVEN a 1 decimal",
                    {**inputs, "group": group},
                )
            )
        parts.append(
            f"{group} {signed(str(diff))}"
            + (f" ({es(share)} % del cambio)" if share is not None else "")
        )
    statement = (
        f"De la variación de {measure} entre {previous} y {year} ({signed(str(total))}, "
        f"{len(months)} meses comparables), el mayor aporte por {dimension} es de "
        f"{'; '.join(parts)}."
    )
    notes = ["Sólo se comparan meses con datos en ambos años.", ASSOCIATION]
    if any(row[3] * total < 0 for row in rows) and total:
        notes.insert(0, "Hay grupos que se movieron en sentido contrario al total.")
    insight = AutomaticInsight(
        id=f"{query.key}:summary",
        analysis_id=query.key,
        kind=query.kind,
        title=f"Variación {year} frente a {previous} por {dimension}",
        statement=statement,
        importance=65,
        figures=figures,
        chart=InsightChart(
            type="bar",
            title=f"Variación de {measure} por {dimension}",
            unit="number",
            points=[
                InsightPoint(label=row[0], value=str(row[3]), evidence_id=None) for row in rows[:12]
            ],
        ),
        coverage=f"Meses comparables: {', '.join(months)} · {len(rows)} grupos",
        notes=notes,
    )
    return FollowUpResult(
        key=query.key, query=query, status="computed", insight=insight, evidence=builder.evidence
    )


def group_evolution(
    builder: Builder,
    query: FollowUpQuery,
    totals: AnalysisResultV2,
    result: AnalysisResultV2,
) -> FollowUpResult:
    group, measure, dimension = query.group or "", query.measure, query.dimension
    months = by_group(result).get(group)
    if not months:
        return empty(query, f"{dimension} = {group} no tiene datos mensuales.")
    series = sorted(months.items())
    last_label, (last_value, last_evidence) = series[-1]
    peak_label, (peak_value, peak_evidence) = max(series, key=lambda item: (item[1][0], item[0]))
    with exact_context():
        own = sum((value for value, _ in months.values()), Decimal(0))
        total = sum((value for _, value, _, _ in monthly_series(totals)), Decimal(0))
    share = pct(own, total) if total > 0 and own >= 0 else None
    figures = [
        builder.figure(
            query.key,
            "last",
            f"{measure} de {group} en {last_label}",
            str(last_value),
            "number",
            "analytics.query@2: suma del grupo en el mes",
            {"query": query.key, "engine_evidence_id": last_evidence},
        ),
        builder.figure(
            query.key,
            "peak",
            f"Mes con mayor {measure} de {group}",
            str(peak_value),
            "number",
            "máximo de las sumas mensuales del grupo",
            {"query": query.key, "month": peak_label, "engine_evidence_id": peak_evidence},
        ),
    ]
    statement = (
        f"{dimension} = {group}: en {last_label}, {measure} fue {es(last_value)}; su mes "
        f"máximo fue {peak_label} ({es(peak_value)})."
    )
    if share is not None:
        figures.append(
            builder.figure(
                query.key,
                "share",
                f"Participación de {group} en {measure} del periodo",
                share,
                "percent",
                "Σ del grupo ÷ Σ total de los meses con dato × 100",
                {"query": query.key, "group_total": str(own), "total": str(total)},
            )
        )
        statement += f" Reúne el {es(share)} % de {measure} del periodo."
    insight = AutomaticInsight(
        id=f"{query.key}:summary",
        analysis_id=query.key,
        kind=query.kind,
        title=f"Evolución de {dimension} = {group}",
        statement=statement,
        importance=55,
        figures=figures,
        chart=InsightChart(
            type="line",
            title=f"{measure} de {group} por mes",
            unit="number",
            points=[
                InsightPoint(label=label, value=str(value), evidence_id=evidence)
                for label, (value, evidence) in series
            ],
        ),
        coverage=f"{len(series)} meses con datos del grupo",
        notes=["Los meses sin datos del grupo no se cuentan como cero."],
    )
    return FollowUpResult(
        key=query.key, query=query, status="computed", insight=insight, evidence=builder.evidence
    )


def run_followups(
    cells: Sequence[Sequence[str | None]],
    periods: Sequence[str | None],
    analysis: AnalyticalInterpretation,
    queries: Sequence[FollowUpQuery],
    scope: AutomaticScope,
) -> FollowUpBatch:
    known = {column.name for column in analysis.columns}
    measures = sorted({q.measure for q in queries if q.measure in known})
    dimensions = sorted({q.dimension for q in queries if q.dimension in known})
    runner = Runner(Table(analysis, cells, periods, measures, dimensions), scope)
    results = []
    for query in queries:
        if query.measure not in known or query.dimension not in known:
            results.append(empty(query, "La columna no existe en la tabla."))
            continue
        monthly = runner.queries.get(f"monthly:{query.dimension}:{query.measure}")
        if monthly is None:
            monthly = runner.query(
                f"monthly:{query.dimension}:{query.measure}",
                [query.measure],
                [query.dimension],
                True,
            )
        builder = Builder(scope)
        if query.kind == "month_by_group":
            results.append(month_by_group(builder, query, monthly))
            continue
        totals = runner.queries.get(f"totals:{query.measure}")
        if totals is None:
            totals = runner.query(f"totals:{query.measure}", [query.measure], [], True)
        if query.kind == "change_by_group":
            results.append(change_by_group(builder, query, totals, monthly))
        else:
            results.append(group_evolution(builder, query, totals, monthly))
    return FollowUpBatch(scope=scope, results=results)
