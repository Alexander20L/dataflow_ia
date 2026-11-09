"""Análisis automático (`analytics.automatic@1`, regla `automatic-analysis-v1`, Fase 15).

Ejecuta el plan `automatic-plan-v1` sobre la tabla importada. Prepara en memoria una
representación tipada (medidas decimales y el periodo mensual como fecha) y reutiliza el motor
de `analytics.query@2` con métricas virtuales (sin revisiones guardadas) para evolución,
comparaciones, participación y ranking. Concentración, promedio ponderado, estacionalidad y
anomalías se calculan aquí con aritmética decimal exacta. Cada cifra tiene evidencia.

Nada se modifica ni se rellena: un mes sin datos no es cero y una asociación no es una causa.
"""

import re
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from dataflow.modules.analytics.contracts import (
    AnalysisResultV2,
    AutomaticAnalysis,
    AutomaticEvidence,
    AutomaticInsight,
    AutomaticScope,
    AutomaticUnit,
    EvidenceScope,
    InsightChart,
    InsightFigure,
    InsightPoint,
    MetricContent,
    MetricReference,
    QueryParametersV2,
    Ranking,
)
from dataflow.modules.analytics.engine import Metric, run_query_v2
from dataflow.modules.planning.public import AnalysisPlan, PlannedAnalysis
from dataflow.modules.understanding.contracts import AnalyticalInterpretation
from dataflow.platform.canonical import digest
from dataflow.platform.decimal_context import exact_context

RULES = "automatic-analysis-v1"
PERIOD = "__periodo_mensual__"
MAX_GROUPS = 50
MAD_FACTOR = Decimal("1.4826")  # MAD → desviación típica en una distribución normal
MAD_LIMIT = Decimal(3)
HUNDRED = Decimal(100)


def number(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(text)
    except ArithmeticError:
        return None
    return value if value.is_finite() else None


def pct(part: Decimal, whole: Decimal, scale: int = 1) -> str | None:
    if whole == 0:
        return None
    with exact_context():
        return str((part * HUNDRED / whole).quantize(Decimal(1).scaleb(-scale), ROUND_HALF_EVEN))


def rounded(value: Decimal, scale: int = 2) -> str:
    with exact_context():
        return str(value.quantize(Decimal(1).scaleb(-scale), ROUND_HALF_EVEN))


def es(value: object) -> str:
    """Cifra canónica con formato español para los textos (las cifras guardan el canónico)."""
    text = str(value)
    if not re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
        return text
    sign = text[0] if text[0] in "+-" else ""
    integer, _, fraction = text.lstrip("+-").partition(".")
    grouped = re.sub(r"\B(?=(\d{3})+(?!\d))", ".", integer)
    return f"{sign}{grouped},{fraction}" if fraction else f"{sign}{grouped}"


def signed(text: str | None) -> str:
    if text is None:
        return "sin base comparable"
    return es(text) if text.startswith("-") else f"+{es(text)}"


def median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with exact_context():
        return (ordered[middle - 1] + ordered[middle]) / 2


class Builder:
    """Reúne hallazgos y evidencias con identificadores deterministas."""

    def __init__(self, scope: AutomaticScope) -> None:
        self.scope = scope
        self.insights: list[AutomaticInsight] = []
        self.evidence: list[AutomaticEvidence] = []

    def figure(
        self,
        analysis: str,
        name: str,
        label: str,
        value: str | None,
        unit: AutomaticUnit,
        method: str,
        inputs: dict[str, Any],
    ) -> InsightFigure:
        identifier = digest(
            "automatic_evidence",
            {
                "scope": self.scope.model_dump(mode="json"),
                "analysis": analysis,
                "name": name,
                "value": value,
                "method": method,
            },
        )
        self.evidence.append(
            AutomaticEvidence(
                evidence_id=identifier,
                analysis_id=analysis,
                label=label,
                value=value,
                unit=unit,
                method=method,
                inputs=inputs,
            )
        )
        return InsightFigure(label=label, value=value, unit=unit, evidence_id=identifier)


class Table:
    """Representación tipada en memoria: medidas decimales, dimensiones y periodo."""

    def __init__(
        self,
        analysis: AnalyticalInterpretation,
        cells: Sequence[Sequence[str | None]],
        periods: Sequence[str | None],
        measures: list[str],
        dimensions: list[str],
    ) -> None:
        by_name = {column.name: column for column in analysis.columns}
        self.columns: list[dict[str, Any]] = []
        self.ids: dict[str, UUID] = {}
        typed: list[list[Any]] = [[] for _ in cells]
        for name in measures:
            ordinal = by_name[name].ordinal
            values = [number(row[ordinal]) for row in cells]
            scale = max((max(0, -int(v.as_tuple().exponent)) for v in values if v), default=0)
            integer = all(v is None or v == v.to_integral_value() for v in values) and scale == 0
            self.add(name, "integer" if integer else "decimal", {} if integer else {"scale": scale})
            for row, value in zip(typed, values, strict=True):
                row.append(
                    None
                    if value is None
                    else int(value)
                    if integer
                    else value.quantize(Decimal(1).scaleb(-scale))
                )
        for name in dimensions:
            ordinal = by_name[name].ordinal
            self.add(name, "string", {})
            for row, source in zip(typed, cells, strict=True):
                row.append(source[ordinal])
        self.add(PERIOD, "date", {})
        for row, period in zip(typed, periods, strict=True):
            row.append(date(int(period[:4]), int(period[5:7]), 1) if period else None)
        self.rows = typed
        self.headers = [str(column["name"]) for column in self.columns]

    def add(self, name: str, kind: str, parameters: dict[str, Any]) -> None:
        identifier = uuid5(NAMESPACE_URL, f"automatic-column:{name}")
        self.ids[name] = identifier
        self.columns.append(
            {
                "id": str(identifier),
                "name": name,
                "technical_type": kind,
                "type_parameters": parameters,
            }
        )


class Runner:
    def __init__(self, table: Table, scope: AutomaticScope) -> None:
        self.table, self.scope = table, scope
        self.queries: dict[str, AnalysisResultV2] = {}

    def metric(self, measure: str) -> Metric:
        content = MetricContent(
            label=measure,
            measure_column_id=self.table.ids[measure],
            aggregation="sum",
            time_column_id=self.table.ids[PERIOD],
            base_table=self.scope.input,
        )
        reference = MetricReference(
            revision_id=uuid5(NAMESPACE_URL, f"automatic-metric:{measure}"),
            content_sha256=digest("analytics_metric", content.hashed()),
        )
        return Metric(reference, 1, content)

    def query(
        self,
        key: str,
        measures: list[str],
        dimensions: list[str],
        monthly: bool,
        comparisons: list[str] | None = None,
        shares: bool = False,
    ) -> AnalysisResultV2:
        metrics = [self.metric(measure) for measure in measures]
        references = [metric.reference for metric in metrics]
        parameters = QueryParametersV2.model_validate(
            {
                "metrics": [r.model_dump(mode="json") for r in references],
                "dimensions": [str(self.table.ids[d]) for d in dimensions],
                "time_grain": "month" if monthly else None,
                "comparisons": comparisons or [],
                "share_of_total": [str(references[0].revision_id)] if shares else [],
                "ranking": Ranking(metric_revision_id=references[0].revision_id, top_n=MAX_GROUPS)
                if shares and dimensions
                else None,
                "max_result_rows": 10000,
            }
        )
        scope = EvidenceScope(
            execution_id=self.scope.execution_id,
            step_id=f"{self.scope.step_id}:{key}",
            input=self.scope.input,
            semantic_ref=None,
            query_filters=[],
            time_grain="month" if monthly else None,
            time_range=None,
        )
        result = run_query_v2(
            self.table.headers, self.table.rows, self.table.columns, metrics, parameters, scope
        )
        self.queries[key] = result
        return result


def monthly_series(result: AnalysisResultV2) -> list[tuple[str, Decimal, str, Any]]:
    """(mes, valor, evidencia, fila) de los meses con valor, en orden cronológico."""
    series = []
    for row in result.rows:
        label = row.labels.get("period")
        value = number(row.values.get("m0"))
        if label is None or not label[:4].isdigit() or value is None:
            continue
        series.append((label, value, row.evidence["m0"], row))
    return sorted(series, key=lambda item: item[0])


def evolution(
    builder: Builder, item: PlannedAnalysis, result: AnalysisResultV2, incomplete: list[str]
) -> None:
    measure = item.measure or ""
    series = monthly_series(result)
    if not series:
        return
    last_label, last_value, last_evidence, last_row = series[-1]
    peak = max(series, key=lambda point: (point[1], point[0]))
    figures = [
        builder.figure(
            item.id,
            "last",
            f"{measure} en {last_label}",
            str(last_value),
            "number",
            "analytics.query@2: suma del mes",
            {"query": item.id, "engine_evidence_id": last_evidence},
        ),
    ]
    statement = f"En {last_label}, {measure} fue {es(last_value)}"
    comparison = last_row.comparisons.get("m0", {}).get("previous_period")
    if comparison is not None and comparison.change_pct is not None:
        figures.append(
            builder.figure(
                item.id,
                "last_change_pct",
                f"Variación de {last_label} frente a {comparison.base_label}",
                comparison.change_pct,
                "percent",
                "analytics.query@2: variación sobre el periodo anterior",
                {"query": item.id, "engine_evidence_id": comparison.evidence["change_pct"]},
            )
        )
        statement += f", {signed(comparison.change_pct)} % frente a {comparison.base_label}"
    elif comparison is not None:
        statement += f" ({comparison.base_label or 'el mes anterior'} no tiene datos comparables)"
    figures.append(
        builder.figure(
            item.id,
            "peak",
            f"Mes con mayor {measure}",
            str(peak[1]),
            "number",
            "máximo de las sumas mensuales",
            {"query": item.id, "month": peak[0], "engine_evidence_id": peak[2]},
        )
    )
    statement += f". El mes con mayor {measure} fue {peak[0]} ({es(peak[1])})."
    notes = ["Los meses sin datos no se cuentan como cero: la serie los omite."]
    if incomplete:
        notes.append(f"Posiblemente incompletos: {', '.join(incomplete)}.")
    builder.insights.append(
        AutomaticInsight(
            id=f"{item.id}:summary",
            analysis_id=item.id,
            kind=item.kind,
            title=item.title,
            statement=statement,
            importance=90,
            figures=figures,
            chart=InsightChart(
                type="line",
                title=f"{measure} por mes",
                unit="number",
                points=[
                    InsightPoint(label=label, value=str(value), evidence_id=evidence)
                    for label, value, evidence, _ in series
                ],
            ),
            coverage=f"{len(series)} meses con datos · {result.metrics[0].counts.included_rows} "
            f"filas incluidas · {result.metrics[0].counts.excluded_by_nulls} sin valor",
            notes=notes,
        )
    )


def year_over_year(builder: Builder, item: PlannedAnalysis, result: AnalysisResultV2) -> None:
    measure = item.measure or ""
    rows = []
    for label, value, evidence, row in monthly_series(result):
        cell = row.comparisons.get("m0", {}).get("same_period_last_year")
        base = number(cell.base) if cell is not None else None
        if cell is not None and cell.base_status == "available" and base is not None:
            rows.append((label, value, base, evidence, cell.evidence.get("base")))
    if not rows:
        return
    year = max(label[:4] for label, *_ in rows)
    current = [row for row in rows if row[0][:4] == year]
    with exact_context():
        total = sum((row[1] for row in current), Decimal(0))
        base = sum((row[2] for row in current), Decimal(0))
    change = pct(total - base, base)
    months = [row[0] for row in current]
    inputs = {
        "query": item.id,
        "months": months,
        "engine_evidence_ids": [row[3] for row in current],
        "base_evidence_ids": [row[4] for row in current],
    }
    previous = str(int(year) - 1)
    figures = [
        builder.figure(
            item.id,
            "current",
            f"{measure} {year} (meses comparables)",
            str(total),
            "number",
            "suma de los meses con base el año anterior",
            inputs,
        ),
        builder.figure(
            item.id,
            "base",
            f"{measure} {previous} (mismos meses)",
            str(base),
            "number",
            "suma de las bases del mismo mes del año anterior",
            inputs,
        ),
        builder.figure(
            item.id,
            "change_pct",
            f"Variación {year} frente a {previous}",
            change,
            "percent",
            "(actual − base) ÷ base × 100, HALF_EVEN a 1 decimal",
            inputs,
        ),
    ]
    builder.insights.append(
        AutomaticInsight(
            id=f"{item.id}:{year}",
            analysis_id=item.id,
            kind=item.kind,
            title=item.title,
            statement=(
                f"En los {len(current)} meses de {year} con dato también en {previous}, "
                f"{measure} sumó {es(total)} frente a {es(base)}: {signed(change)} %."
            ),
            importance=85,
            figures=figures,
            chart=InsightChart(
                type="bar",
                title=f"{measure}: {previous} frente a {year} (meses comparables)",
                unit="number",
                points=[
                    InsightPoint(
                        label=previous, value=str(base), evidence_id=figures[1].evidence_id
                    ),
                    InsightPoint(label=year, value=str(total), evidence_id=figures[0].evidence_id),
                ],
            ),
            coverage=f"Meses comparables: {', '.join(months)}",
            notes=["Sólo se comparan meses con datos en ambos años; el resto no se compara."],
        )
    )


def breakdown(
    builder: Builder, item: PlannedAnalysis, result: AnalysisResultV2, order: int
) -> None:
    measure, dimension = item.measure or "", item.dimension or ""
    rows = []
    for row in result.rows:
        value = number(row.values.get("m0"))
        if value is None or row.labels.get("d0") is None:
            continue
        rows.append((str(row.labels["d0"]), value, row))
    if not rows:
        return
    rows.sort(key=lambda entry: (-entry[1], entry[0]))
    with exact_context():
        total = sum((entry[1] for entry in rows), Decimal(0))
    negative = any(entry[1] < 0 for entry in rows)
    top_label, top_value, top_row = rows[0]
    share_cell = top_row.share.get("m0")
    figures = [
        builder.figure(
            item.id,
            "top_share",
            f"Participación de {top_label} en {measure}",
            share_cell.value if share_cell else pct(top_value, total),
            "percent",
            "analytics.query@2: participación sobre el total",
            {"query": item.id, "engine_evidence_id": share_cell.evidence if share_cell else None},
        )
    ]
    notes: list[str] = []
    statement = f"{top_label} concentra el {es(figures[0].value)} % de {measure}"
    if negative or total <= 0:
        notes.append("Hay valores negativos: no se calcula la concentración.")
    else:
        with exact_context():
            top3 = sum((entry[1] for entry in rows[:3]), Decimal(0))
            hhi = sum(((entry[1] * HUNDRED / total) ** 2 for entry in rows), Decimal(0))
        hhi_text = rounded(hhi, 0)
        level = "alta" if hhi >= 2500 else "moderada" if hhi >= 1500 else "baja"
        inputs = {"query": item.id, "groups": [entry[0] for entry in rows], "total": str(total)}
        figures.append(
            builder.figure(
                item.id,
                "top3_share",
                f"Participación de los 3 primeros {dimension}",
                pct(top3, total),
                "percent",
                "Σ 3 mayores ÷ total × 100",
                inputs,
            )
        )
        figures.append(
            builder.figure(
                item.id,
                "hhi",
                f"Índice de concentración (HHI) por {dimension}",
                hhi_text,
                "index",
                "Σ (participación en %)², de 0 a 10.000",
                inputs,
            )
        )
        statement += (
            f"; los 3 primeros, el {es(figures[1].value)} %. Concentración {level} "
            f"(HHI {es(hhi_text)})."
            if len(rows) > 3
            else f". Concentración {level} (HHI {es(hhi_text)})."
        )
    builder.insights.append(
        AutomaticInsight(
            id=f"{item.id}:summary",
            analysis_id=item.id,
            kind=item.kind,
            title=item.title,
            statement=statement,
            importance=max(30, 70 - 5 * order),
            figures=figures,
            chart=InsightChart(
                type="bar",
                title=f"{measure} por {dimension}",
                unit="number",
                points=[
                    InsightPoint(label=label, value=str(value), evidence_id=row.evidence["m0"])
                    for label, value, row in rows[:12]
                ],
            ),
            coverage=f"{len(rows)} grupos · {result.metrics[0].counts.included_rows} filas "
            "incluidas",
            notes=notes + ([f"{len(rows) - 12} grupos no se muestran."] if len(rows) > 12 else []),
        )
    )


def weighted(
    builder: Builder,
    item: PlannedAnalysis,
    analysis: AnalyticalInterpretation,
    cells: Sequence[Sequence[str | None]],
    dimension: str | None,
) -> None:
    by_name = {column.name: column for column in analysis.columns}
    target, weight = by_name[item.measure or ""], by_name[item.weight or ""]
    rate_name = item.id.split(":", 1)[1]
    rate = by_name[rate_name]
    groups: dict[str, list[Decimal]] = {}
    rates: list[Decimal] = []
    used = 0
    for row in cells:
        amount, quantity = number(row[target.ordinal]), number(row[weight.ordinal])
        simple = number(row[rate.ordinal])
        if simple is not None:
            rates.append(simple)
        if amount is None or quantity is None:
            continue
        used += 1
        keys = ["__total__"]
        if dimension is not None and row[by_name[dimension].ordinal] is not None:
            keys.append(str(row[by_name[dimension].ordinal]))
        for key in keys:
            totals = groups.setdefault(key, [Decimal(0), Decimal(0)])
            with exact_context():
                totals[0] += amount
                totals[1] += quantity
    if "__total__" not in groups or groups["__total__"][1] == 0:
        return

    def ratio(key: str) -> str | None:
        amount, quantity = groups[key]
        if quantity == 0:
            return None
        with exact_context():
            return rounded(amount / quantity, 2)

    total_amount, total_quantity = groups["__total__"]
    with exact_context():
        simple_mean = rounded(sum(rates, Decimal(0)) / len(rates), 2) if rates else None
    inputs = {
        "amount": target.name,
        "weight": weight.name,
        "rows": used,
        "sum_amount": str(total_amount),
        "sum_weight": str(total_quantity),
    }
    figures = [
        builder.figure(
            item.id,
            "weighted",
            f"{rate.name} medio ponderado",
            ratio("__total__"),
            "number",
            f"Σ {target.name} ÷ Σ {weight.name}, HALF_EVEN a 2 decimales",
            inputs,
        ),
    ]
    statement = (
        f"{rate.name} medio ponderado por {weight.name}: {es(figures[0].value)} "
        f"(Σ {target.name} ÷ Σ {weight.name})"
    )
    if simple_mean is not None:
        figures.append(
            builder.figure(
                item.id,
                "simple",
                f"Promedio simple de {rate.name}",
                simple_mean,
                "number",
                "media aritmética de las filas, HALF_EVEN a 2 decimales",
                {"column": rate.name, "rows": len(rates)},
            )
        )
        statement += f"; el promedio simple por fila sería {es(simple_mean)}"
    statement += "."
    points = []
    if dimension is not None:
        for key in sorted(k for k in groups if k != "__total__"):
            value = ratio(key)
            figure = builder.figure(
                item.id,
                f"group:{key}",
                f"{rate.name} ponderado · {dimension} = {key}",
                value,
                "number",
                f"Σ {target.name} ÷ Σ {weight.name} del grupo",
                {
                    "group": key,
                    "dimension": dimension,
                    "sum_amount": str(groups[key][0]),
                    "sum_weight": str(groups[key][1]),
                },
            )
            points.append(InsightPoint(label=key, value=value, evidence_id=figure.evidence_id))
    builder.insights.append(
        AutomaticInsight(
            id=f"{item.id}:summary",
            analysis_id=item.id,
            kind=item.kind,
            title=item.title,
            statement=statement,
            importance=60,
            figures=figures,
            chart=InsightChart(
                type="bar",
                title=f"{rate.name} ponderado por {dimension}",
                unit="number",
                points=points,
            )
            if points
            else None,
            coverage=f"{used} filas con {target.name} y {weight.name}",
            notes=[f"{rate.name} no se suma: un promedio simple sobrerrepresenta filas pequeñas."],
        )
    )


def anomalies(
    builder: Builder,
    item: PlannedAnalysis,
    evolution_result: AnalysisResultV2,
    factors: dict[str, AnalysisResultV2],
) -> None:
    measure = item.measure or ""
    series = monthly_series(evolution_result)
    values = [value for _, value, _, _ in series]
    if len(values) < 2:
        return
    center = median(values)
    with exact_context():
        mad = median([abs(value - center) for value in values])
        limit = MAD_LIMIT * MAD_FACTOR * mad
    method = "|valor − mediana| > 3 × 1,4826 × MAD de los totales mensuales"
    if mad == 0:
        return
    found = [
        (label, value, evidence)
        for label, value, evidence, _ in series
        if abs(value - center) > limit
    ]
    if not found:
        builder.insights.append(
            AutomaticInsight(
                id=f"{item.id}:none",
                analysis_id=item.id,
                kind=item.kind,
                title=item.title,
                statement=f"Ningún mes de {measure} se aparta del nivel habitual "
                f"(mediana {es(rounded(center))}).",
                importance=20,
                figures=[
                    builder.figure(
                        item.id,
                        "median",
                        f"Mediana mensual de {measure}",
                        rounded(center),
                        "number",
                        "mediana de totales mensuales",
                        {"query": "evolution", "months": len(series)},
                    )
                ],
                coverage=f"{len(series)} meses",
                notes=[method],
            )
        )
        return
    for label, value, evidence in found:
        deviation = value - center
        figures = [
            builder.figure(
                item.id,
                f"{label}:value",
                f"{measure} en {label}",
                str(value),
                "number",
                "analytics.query@2: suma del mes",
                {"query": "evolution", "engine_evidence_id": evidence},
            ),
            builder.figure(
                item.id,
                f"{label}:median",
                f"Mediana mensual de {measure}",
                rounded(center),
                "number",
                "mediana de los totales mensuales",
                {"query": "evolution", "months": len(series)},
            ),
        ]
        associated = []
        for dimension, result in factors.items():
            by_group: dict[str, dict[str, Decimal]] = {}
            for row in result.rows:
                group, month = row.labels.get("d0"), row.labels.get("period")
                amount = number(row.values.get("m0"))
                if group is None or month is None or amount is None:
                    continue
                by_group.setdefault(str(group), {})[str(month)] = amount
            best: tuple[Decimal, str] | None = None
            for group, months in by_group.items():
                if label not in months:
                    continue
                shift = months[label] - median(list(months.values()))
                if (shift > 0) == (deviation > 0) and (best is None or abs(shift) > abs(best[0])):
                    best = (shift, group)
            if best is not None:
                associated.append(f"{dimension} = {best[1]} ({signed(rounded(best[0]))})")
                figures.append(
                    builder.figure(
                        item.id,
                        f"{label}:{dimension}",
                        f"Desvío de {dimension} = {best[1]} en {label}",
                        rounded(best[0]),
                        "number",
                        "valor del grupo en el mes − su mediana mensual",
                        {"query": f"factors:{dimension}", "group": best[1]},
                    )
                )
        direction = "por encima" if deviation > 0 else "por debajo"
        statement = (
            f"{label}: {measure} = {es(value)}, {signed(rounded(deviation))} {direction} de la "
            f"mediana mensual ({es(rounded(center))})."
        )
        if associated:
            statement += f" Se asocia sobre todo a {' y '.join(associated)}."
        builder.insights.append(
            AutomaticInsight(
                id=f"{item.id}:{label}",
                analysis_id=item.id,
                kind=item.kind,
                title=f"Mes atípico de {measure}: {label}",
                statement=statement,
                importance=80,
                figures=figures,
                coverage=f"{len(series)} meses evaluados",
                notes=[method, "Es una asociación para investigar, no una causa demostrada."],
            )
        )


def seasonality(builder: Builder, item: PlannedAnalysis, result: AnalysisResultV2) -> None:
    measure = item.measure or ""
    series = monthly_series(result)
    if len(series) < 24:
        return
    by_month: dict[str, list[Decimal]] = {}
    for label, value, _, _ in series:
        by_month.setdefault(label[5:7], []).append(value)
    with exact_context():
        overall = sum((value for _, value, _, _ in series), Decimal(0)) / len(series)
        index = (
            {
                month: sum(values, Decimal(0)) / len(values) * HUNDRED / overall
                for month, values in by_month.items()
            }
            if overall
            else {}
        )
    if not index:
        return
    high = max(index, key=lambda m: (index[m], m))
    low = min(index, key=lambda m: (index[m], m))
    points = []
    for month in sorted(index):
        figure = builder.figure(
            item.id,
            f"index:{month}",
            f"Índice estacional del mes {month}",
            rounded(index[month], 1),
            "index",
            "media del mes ÷ media mensual × 100",
            {"month": month},
        )
        points.append(InsightPoint(label=month, value=figure.value, evidence_id=figure.evidence_id))
    builder.insights.append(
        AutomaticInsight(
            id=f"{item.id}:summary",
            analysis_id=item.id,
            kind=item.kind,
            title=item.title,
            statement=(
                f"El mes {high} suele estar en {es(rounded(index[high], 1))} y el mes {low} en "
                f"{es(rounded(index[low], 1))} (100 = mes medio)."
            ),
            importance=50,
            figures=[],
            chart=InsightChart(
                type="bar", title=f"Índice estacional de {measure}", unit="index", points=points
            ),
            coverage=f"{len(series)} meses seguidos",
            notes=["Con pocos años, el patrón puede deberse a hechos puntuales."],
        )
    )


def run_automatic(
    cells: Sequence[Sequence[str | None]],
    periods: Sequence[str | None],
    analysis: AnalyticalInterpretation,
    plan: AnalysisPlan,
    scope: AutomaticScope,
) -> AutomaticAnalysis:
    builder = Builder(scope)
    accepted = {item.id: item for item in plan.accepted}
    breakdowns = [item for item in plan.accepted if item.kind == "breakdown"]
    measures: list[str] = []
    for item in plan.accepted:
        for name in (item.measure, item.weight):
            if name and name not in measures and item.kind != "weighted_average":
                measures.append(name)
    dimensions = [item.dimension for item in breakdowns if item.dimension]
    runner: Runner | None = None
    if measures:
        runner = Runner(Table(analysis, cells, periods, measures, dimensions), scope)
    evolution_result = None
    if runner is not None and plan.measure and ("evolution" in accepted or "anomalies" in accepted):
        comparisons = ["previous_period"]
        if "year_over_year" in accepted:
            comparisons.append("same_period_last_year")
        evolution_result = runner.query("evolution", [plan.measure], [], True, comparisons)
    incomplete = analysis.time.incomplete if analysis.time else []
    if evolution_result is not None and "evolution" in accepted:
        evolution(builder, accepted["evolution"], evolution_result, incomplete)
    if evolution_result is not None and "year_over_year" in accepted:
        year_over_year(builder, accepted["year_over_year"], evolution_result)
    for order, item in enumerate(breakdowns):
        if runner is not None and item.measure and item.dimension:
            result = runner.query(item.id, [item.measure], [item.dimension], False, shares=True)
            breakdown(builder, item, result, order)
    for item in plan.accepted:
        if item.kind == "weighted_average":
            weighted(builder, item, analysis, cells, dimensions[0] if dimensions else None)
    if evolution_result is not None and "anomalies" in accepted and runner is not None:
        factors = {
            dimension: runner.query(f"factors:{dimension}", [plan.measure or ""], [dimension], True)
            for dimension in dimensions
        }
        anomalies(builder, accepted["anomalies"], evolution_result, factors)
    if evolution_result is not None and "seasonality" in accepted:
        seasonality(builder, accepted["seasonality"], evolution_result)
    limitations = [
        "Cifras calculadas por reglas sobre todas las filas; ninguna sale de un modelo de IA.",
        "Los meses sin datos no se cuentan como cero y no se rellenan valores.",
        "Las asociaciones con productos, regiones u otros grupos no demuestran causas.",
    ]
    limitations.extend(f"{item.title}: {item.reason}" for item in plan.omitted)
    builder.insights.sort(key=lambda insight: (-insight.importance, insight.id))
    return AutomaticAnalysis(
        scope=scope,
        plan=plan,
        insights=builder.insights,
        evidence=builder.evidence,
        queries=runner.queries if runner is not None else {},
        limitations=limitations,
    )
