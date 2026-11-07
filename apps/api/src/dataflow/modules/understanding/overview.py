"""Dashboard inicial determinista. No limpia ni confirma significados de negocio."""

import re
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal

from dataflow.modules.understanding.contracts import (
    AutomaticInterpretation,
    AutomaticOverview,
    DatasetProfile,
    OverviewChart,
    OverviewDetail,
    OverviewKpi,
    OverviewPoint,
)
from dataflow.platform.data_types import DataType
from dataflow.platform.decimal_context import exact_context
from dataflow.platform.tabular import Cell, display_cell

MAX_CATEGORIES = 12
MAX_CHARTS = 4
DETAIL_ROWS = 20
DETAIL_CELL_CHARS = 300
IDENTIFIER = re.compile(
    r"(^|[\W_])(id|codigo|código|code|sku|postal|telefono|teléfono)([\W_]|$)", re.I
)


def identifier(name: str) -> bool:
    return bool(IDENTIFIER.search(name)) or name.lower().endswith("_id")


def automatic_overview(
    profile: DatasetProfile,
    rows: Sequence[Sequence[Cell]],
    types: Sequence[tuple[DataType, dict[str, object]]],
    interpretation: AutomaticInterpretation | None = None,
) -> AutomaticOverview:
    headers = [column.name for column in profile.columns]
    count = len(rows)
    cells = count * len(headers)
    nulls = sum(column.null_count for column in profile.columns)
    duplicates = count - len(set(tuple(row) for row in rows))
    with exact_context():
        completeness = (
            str((Decimal(cells - nulls) * 100 / cells).quantize(Decimal("0.01")))
            if cells
            else "0.00"
        )
    kpis = [
        OverviewKpi(id="rows", label="Registros", value=str(count), unit="count"),
        OverviewKpi(id="columns", label="Columnas", value=str(len(headers)), unit="count"),
        OverviewKpi(
            id="completeness", label="Completitud de celdas", value=completeness, unit="percent"
        ),
        OverviewKpi(
            id="duplicates",
            label="Filas idénticas adicionales",
            value=str(duplicates),
            unit="count",
        ),
    ]
    limitations = [
        "Análisis descriptivo automático: no confirma ventas, ingresos, moneda ni otras "
        "definiciones de negocio. No se modificaron ni eliminaron registros.",
        "Los vacíos no se rellenan con cero. Las estadísticas numéricas no incluyen nulos; "
        "los textos ambiguos se conservan sin convertir.",
    ]
    charts: list[OverviewChart] = []
    numeric_columns = 0
    indices = list(range(len(profile.columns)))
    if interpretation is not None:
        # Fechas y categorías primero para que las primeras columnas no oculten la serie
        # temporal. El detalle y los ordinales conservan el orden original de la fuente.
        priority = {"date": 0, "category": 1}
        indices.sort(key=lambda index: (priority.get(interpretation.columns[index].role, 2), index))
    for index in indices:
        column = profile.columns[index]
        is_identifier = (
            interpretation.columns[index].role == "identifier"
            if interpretation is not None
            else identifier(column.name)
        )
        if is_identifier:
            continue
        valid = count - column.null_count
        statistics_allowed = (
            interpretation is None or interpretation.columns[index].statistics_allowed
        )
        if column.numeric and numeric_columns < 3 and statistics_allowed:
            numeric_columns += 1
            summary = column.numeric
            with exact_context():
                mean = format(Decimal(summary.mean).quantize(Decimal("0.000001")), "f")
            for stat, label, stat_value in (
                ("mean", "Promedio", mean),
                ("minimum", "Mínimo", format(Decimal(summary.minimum), "f")),
                ("maximum", "Máximo", format(Decimal(summary.maximum), "f")),
            ):
                kpis.append(
                    OverviewKpi(
                        id=f"c{index}_{stat}",
                        label=f"{label} de {column.name}",
                        value=stat_value,
                        unit="number",
                        column=column.name,
                        valid_rows=summary.count,
                        excluded_rows=count - summary.count,
                    )
                )
        if len(charts) >= MAX_CHARTS - 1:
            continue
        if column.suggested_type == "date":
            counts = Counter(str(row[index])[:7] for row in rows if row[index] is not None)
            # Una serie acotada: últimos meses disponibles, sin rellenar ausencias como cero.
            periods = sorted(counts)
            selected = periods[-120:]
            charts.append(
                OverviewChart(
                    id=f"c{index}_months",
                    title=f"Registros por mes de {column.name}",
                    type="line",
                    column=column.name,
                    points=[OverviewPoint(label=key, value=counts[key]) for key in selected],
                    valid_rows=sum(counts[key] for key in selected),
                    excluded_rows=column.null_count + sum(counts[key] for key in periods[:-120]),
                    omitted_groups=max(0, len(periods) - 120),
                )
            )
        elif column.suggested_type in {"string", "boolean"} and (
            1 <= column.unique_count <= 50 and column.unique_count <= max(1, valid // 2)
        ):
            counts = Counter(
                display_cell(row[index], *types[index]) or ""
                for row in rows
                if row[index] is not None
            )
            groups = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
            selected_groups = groups[:MAX_CATEGORIES]
            represented = sum(value for _, value in selected_groups)
            charts.append(
                OverviewChart(
                    id=f"c{index}_counts",
                    title=f"Registros por {column.name}",
                    type="bar",
                    column=column.name,
                    points=[
                        OverviewPoint(label=str(key), value=value) for key, value in selected_groups
                    ],
                    valid_rows=represented,
                    excluded_rows=count - represented,
                    omitted_groups=max(0, len(groups) - MAX_CATEGORIES),
                )
            )
    # Siempre útil incluso si no hay categorías o fechas interpretables.
    charts.append(
        OverviewChart(
            id="missing",
            title="Celdas vacías por columna",
            type="bar",
            points=[
                OverviewPoint(label=column.name, value=column.null_count)
                for column in sorted(profile.columns, key=lambda c: (-c.null_count, c.name))[:12]
            ],
            valid_rows=count,
            excluded_rows=0,
            omitted_groups=max(0, len(headers) - 12),
        )
    )
    shown: list[list[str | None]] = []
    truncated_cells = False
    for row in rows[:DETAIL_ROWS]:
        values = []
        for value, (kind, parameters) in zip(row, types, strict=True):
            text = display_cell(value, kind, parameters)
            if text is not None and len(text) > DETAIL_CELL_CHARS:
                truncated_cells = True
                text = text[:DETAIL_CELL_CHARS] + "…"
            values.append(text)
        shown.append(values)
    if duplicates:
        limitations.append("Las filas idénticas se conservaron: podrían ser registros legítimos.")
    return AutomaticOverview(
        algorithm="automatic-overview-v2"
        if interpretation is not None
        else "automatic-overview-v1",
        source_sha256=profile.source_sha256,
        kpis=kpis,
        charts=charts,
        table_detail=OverviewDetail(
            columns=headers,
            rows=shown,
            total_rows=count,
            truncated=count > DETAIL_ROWS,
            cells_truncated=truncated_cells,
        ),
        limitations=limitations,
        interpretation=interpretation,
    )
