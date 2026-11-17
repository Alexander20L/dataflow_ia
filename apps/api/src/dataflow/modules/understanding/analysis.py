"""Interpretación analítica por reglas (`automatic-interpretation-v2`, Fase 14).

Pura: recibe el perfil y las celdas como texto canónico; sin BD, Polars, IA ni otros módulos.
Produce hipótesis con evidencia (papeles de columna, eje temporal, claves, relaciones y
dependencias), nunca confirmaciones. Ante la duda limita el análisis en vez de suponer.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from itertools import combinations

from dataflow.modules.understanding.contracts import (
    AnalyticalColumn,
    AnalyticalInterpretation,
    ColumnDependency,
    ColumnRole,
    DatasetProfile,
    KeyCandidate,
    LimitedAnalysis,
    MeasureRelationship,
    TimeAxis,
)

RULES_VERSION = "automatic-interpretation-v2"
NUMBER = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?\Z")
INTEGER = re.compile(r"[-+]?(?:0|[1-9]\d*)\Z")
# Código: letras y dígitos juntos (C001, SKU-12). Un texto con dígitos y espacios no lo es.
CODE = re.compile(r"(?=[^ ]*\d)(?=[^ ]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_\-./]{1,29}\Z")

IDENTIFIERS = {"id", "codigo", "code", "sku", "postal", "telefono", "phone", "dni", "ruc"}
YEARS = {"year", "ano", "anio", "ejercicio"}
MONTHS_NAMES = {"month", "mes"}
MONEY = {
    "importe",
    "monto",
    "amount",
    "price",
    "precio",
    "cost",
    "costo",
    "coste",
    "revenue",
    "ingreso",
    "ingresos",
    "sales",
    "venta",
    "ventas",
    "facturacion",
    "subtotal",
    "total",
}
SALES = {"revenue", "ventas", "venta", "sales", "ingreso", "ingresos", "facturacion", "importe"}
QUANTITY = {"units", "unidades", "quantity", "qty", "cantidad", "piezas", "items"}
NON_ADDITIVE = {
    "price",
    "precio",
    "rate",
    "tasa",
    "percent",
    "porcentaje",
    "pct",
    "ratio",
    "avg",
    "average",
    "promedio",
    "media",
    "per",
    "margin",
    "margen",
    "tarifa",
    "unitario",
}
SEMI_ADDITIVE = {"stock", "inventario", "inventory", "existencias", "saldo", "balance"}
ADDITIVE = MONEY | QUANTITY | {"count", "conteo"}
CURRENCY_COLUMNS = {"moneda", "currency", "divisa"}
CURRENCY_CODES = {"usd", "eur", "pen", "mxn", "cop", "clp", "ars", "gbp", "brl"}
PRODUCTS = {"product", "producto", "articulo", "item", "sku"}
MONTH_NUMBERS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan", "enero", "ene"),
            ("february", "feb", "febrero"),
            ("march", "mar", "marzo"),
            ("april", "apr", "abril", "abr"),
            ("may", "mayo"),
            ("june", "jun", "junio"),
            ("july", "jul", "julio"),
            ("august", "aug", "agosto", "ago"),
            ("september", "sep", "sept", "septiembre", "setiembre", "set"),
            ("october", "oct", "octubre"),
            ("november", "nov", "noviembre"),
            ("december", "dec", "diciembre", "dic"),
        ],
        start=1,
    )
    for name in names
}
MAX_KEY_COLUMNS = 8
MAX_MEASURES = 8
TOLERANCE = Decimal("0.005")  # relativa; mínimo absoluto 0,01 (redondeo de céntimos)
LABELS = {
    "generic": "Perfil general de datos",
    "sales": "Posible contexto comercial (ventas)",
    "inventory": "Posible contexto de inventario",
    "ambiguous": "Contexto de negocio no concluyente",
}


def plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def tokens(name: str) -> set[str]:
    spaced = re.sub(r"([a-záéíóúñ])([A-Z])", r"\1 \2", name)
    return set(re.findall(r"[a-z0-9]+", plain(spaced)))


def decimal(value: str | None) -> Decimal | None:
    if value is None or not NUMBER.fullmatch(value):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:  # pragma: no cover - la expresión regular ya lo impide
        return None


def month_number(value: str) -> int | None:
    if INTEGER.fullmatch(value):
        number = int(value)
        return number if 1 <= number <= 12 else None
    return MONTH_NUMBERS.get(plain(value.strip()).rstrip("."))


def is_year(values: list[str]) -> bool:
    return bool(values) and all(
        INTEGER.fullmatch(value) and 1900 <= int(value) <= 2100 for value in values
    )


def add_months(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7]) - 1 + months
    return f"{year + month // 12:04d}-{month % 12 + 1:02d}"


def months_between(first: str, last: str) -> list[str]:
    result: list[str] = []
    current = first
    while current <= last and len(result) < 1200:
        result.append(current)
        current = add_months(current, 1)
    return result


def row_periods(
    columns: list[AnalyticalColumn], cells: Sequence[Sequence[str | None]]
) -> tuple[TimeAxis | None, list[str | None]]:
    """Periodo mensual de cada fila (o None) y el eje temporal que forman."""
    by_part = {column.time_part: column for column in columns if column.role == "time"}
    year, month, day = by_part.get("year"), by_part.get("month"), by_part.get("date")
    periods: list[str | None] = []
    if year is not None and month is not None:
        kind, names = "year_month", [year.name, month.name]
        for row in cells:
            y, m = row[year.ordinal], row[month.ordinal]
            number = month_number(m) if m is not None else None
            periods.append(f"{int(y):04d}-{number:02d}" if y is not None and number else None)
    elif day is not None:
        kind, names = "date", [day.name]
        periods = [
            value[:7] if value is not None else None
            for value in (row[day.ordinal] for row in cells)
        ]
    else:
        return None, [None] * len(cells)
    counts = Counter(period for period in periods if period is not None)
    observed = sorted(counts)
    expected = months_between(observed[0], observed[-1]) if observed else []
    missing = [period for period in expected if period not in counts]
    incomplete: list[str] = []
    if len(observed) >= 3:
        ordered = sorted(counts.values())
        median = ordered[len(ordered) // 2]
        # Sólo los extremos: un primer o último mes con menos de la mitad de registros que la
        # mediana suele ser un corte parcial. Es una advertencia, no una corrección.
        incomplete = [p for p in (observed[0], observed[-1]) if counts[p] * 2 < median]
    unparsed_rows = [
        number
        for number, (row, period) in enumerate(zip(cells, periods, strict=True), start=1)
        if period is None and any(row[c.ordinal] is not None for c in (year, month, day) if c)
    ]
    unparsed = len(unparsed_rows)
    axis = TimeAxis(
        kind=kind,
        columns=names,
        first=observed[0] if observed else None,
        last=observed[-1] if observed else None,
        periods=len(observed),
        years=sorted({period[:4] for period in observed}),
        missing=missing[:24],
        missing_count=len(missing),
        incomplete=incomplete,
        unparsed_rows=unparsed,
        unparsed_sample_rows=unparsed_rows[:5],
    )
    return axis, periods


def classify(
    profile: DatasetProfile, cells: Sequence[Sequence[str | None]]
) -> list[AnalyticalColumn]:
    rows = profile.row_count
    currency_values: set[str] = set()
    for index, column in enumerate(profile.columns):
        if tokens(column.name) & CURRENCY_COLUMNS:
            currency_values |= {v for v in (row[index] for row in cells) if v is not None}
    result: list[AnalyticalColumn] = []
    for index, column in enumerate(profile.columns):
        names = tokens(column.name)
        values = [v for v in (row[index] for row in cells) if v is not None]
        valid = len(values)
        evidence = [f"{valid} valores no nulos de {rows}."]
        role: ColumnRole = "text"
        time_part = None
        if not values:
            role = "empty"
            evidence.append("No hay valores para interpretar.")
        elif names & YEARS and is_year(values):
            role, time_part = "time", "year"
            evidence.append("Nombre de año y enteros entre 1900 y 2100: es tiempo, no medida.")
        elif names & MONTHS_NAMES and all(month_number(value) for value in values):
            role, time_part = "time", "month"
            evidence.append("Nombre de mes y valores de mes reconocibles: es tiempo, no medida.")
        elif column.suggested_type == "date":
            role, time_part = "time", "date"
            evidence.append("Fechas ISO reconocibles en todos los valores.")
        elif names & IDENTIFIERS:
            role = "identifier"
            evidence.append("El nombre indica un identificador: no se agrega como medida.")
        elif column.numeric is not None:
            role = "measure"
            evidence.append("Todos los valores son números: medida candidata.")
        elif column.unique_count > 1 and all(CODE.fullmatch(value) for value in values):
            role = "identifier"
            evidence.append("Todos los valores son códigos (letras y dígitos): identificador.")
        elif column.unique_count <= 50 and column.unique_count <= max(1, valid // 2):
            role = "dimension"
            evidence.append(
                f"{column.unique_count} valores distintos que se repiten: dimensión para agrupar."
            )
        else:
            evidence.append("Texto sin repeticiones suficientes para agrupar.")
        additivity = None
        monetary = False
        currency = currency_code = unit = unit_label = None
        if role == "measure":
            monetary = bool(names & MONEY) and not names & QUANTITY
            if names & NON_ADDITIVE:
                additivity = "non_additive"
                evidence.append("Precio, tasa o promedio: no se suma entre registros.")
            elif names & SEMI_ADDITIVE:
                additivity = "semi_additive"
                evidence.append("Saldo o existencias: no se suma entre fechas.")
            elif names & ADDITIVE:
                additivity = "additive"
                evidence.append("Importe o cantidad: se puede sumar entre registros.")
            else:
                additivity = "unknown"
                evidence.append("Sin evidencia de aditividad: no se suma.")
            if monetary:
                codes = names & CURRENCY_CODES
                if len(currency_values) > 1:
                    currency = "ambiguous"
                    evidence.append("Hay varias monedas en la fuente: no se agregan juntas.")
                elif len(currency_values) == 1:
                    currency, currency_code = "known", next(iter(currency_values)).upper()
                elif len(codes) == 1:
                    currency, currency_code = "known", next(iter(codes)).upper()
                else:
                    currency = "unknown"
                    evidence.append("Moneda no identificada: no se inventa.")
                unit, unit_label = currency, currency_code
            elif names & QUANTITY:
                unit, unit_label = "known", "unidades"
            else:
                unit = "unknown"
        result.append(
            AnalyticalColumn(
                ordinal=index,
                name=column.name,
                role=role,
                time_part=time_part,
                additivity=additivity,
                monetary=monetary,
                currency=currency,
                currency_code=currency_code,
                unit=unit,
                unit_label=unit_label,
                evidence=evidence,
            )
        )
    return result


def key_candidates(
    columns: list[AnalyticalColumn], cells: Sequence[Sequence[str | None]]
) -> list[KeyCandidate]:
    rows = len(cells)
    if rows < 2:
        return []
    order = {"time": 0, "identifier": 1, "dimension": 2, "text": 3}
    pool = sorted(
        (c for c in columns if c.role in order),
        key=lambda c: (order[c.role], c.ordinal),
    )[:MAX_KEY_COLUMNS]
    largest = 4 if rows <= 20000 else 3
    found: list[KeyCandidate] = []
    best: tuple[int, tuple[AnalyticalColumn, ...]] | None = None
    for size in range(1, largest + 1):
        for group in combinations(pool, size):
            if any(set(k.columns) <= {c.name for c in group} for k in found):
                continue
            seen = {tuple(row[c.ordinal] for c in group) for row in cells}
            if any(None in key for key in seen):
                continue
            if len(seen) == rows:
                names = [c.name for c in group]
                found.append(
                    KeyCandidate(
                        columns=names,
                        unique=True,
                        duplicate_rows=0,
                        evidence=f"Cada combinación de {', '.join(names)} aparece una sola vez.",
                    )
                )
            elif best is None or len(seen) > best[0]:
                best = (len(seen), group)
        if found:
            return found[:3]
    if best is not None and best[0] * 100 >= rows * 95:
        names = [c.name for c in best[1]]
        first: set[tuple[str | None, ...]] = set()
        repeated: list[int] = []
        for number, row in enumerate(cells, start=1):
            key = tuple(row[c.ordinal] for c in best[1])
            if key in first:
                repeated.append(number)
            first.add(key)
        return [
            KeyCandidate(
                columns=names,
                unique=False,
                duplicate_rows=rows - best[0],
                duplicate_sample_rows=repeated[:5],
                evidence=(
                    f"{', '.join(names)} identifica casi todas las filas; "
                    f"{rows - best[0]} filas repiten una combinación."
                ),
            )
        ]
    return []


def relationships(
    columns: list[AnalyticalColumn], cells: Sequence[Sequence[str | None]]
) -> list[MeasureRelationship]:
    measures = [c for c in columns if c.role == "measure"][:MAX_MEASURES]
    numbers = {c.ordinal: [decimal(row[c.ordinal]) for row in cells] for c in measures}
    found: list[MeasureRelationship] = []

    def matches(target: int, a: int, b: int, limit: int | None) -> tuple[int, int, list[int]]:
        compared = matching = 0
        exceptions: list[int] = []
        rows = zip(numbers[target], numbers[a], numbers[b], strict=True)
        for number, (x, y, z) in enumerate(rows, start=1):
            if x is None or y is None or z is None:
                continue
            compared += 1
            product = y * z
            if abs(x - product) <= max(Decimal("0.01"), abs(product) * TOLERANCE):
                matching += 1
            elif len(exceptions) < 5:
                exceptions.append(number)
            if limit is not None and compared >= limit:
                break
        return compared, matching, exceptions

    for target in measures:
        for a, b in combinations([m for m in measures if m is not target], 2):
            compared, matching, _ = matches(target.ordinal, a.ordinal, b.ordinal, 50)
            if compared < 3 or matching * 10 < compared * 9:
                continue
            compared, matching, exceptions = matches(target.ordinal, a.ordinal, b.ordinal, None)
            if matching * 100 >= compared * 95:
                found.append(
                    MeasureRelationship(
                        target=target.name,
                        factors=[a.name, b.name],
                        compared_rows=compared,
                        matching_rows=matching,
                        tolerance="0,5 % (mínimo 0,01)",
                        exception_sample_rows=exceptions,
                    )
                )
    return found


def minority_rows(
    cells: Sequence[Sequence[str | None]],
    determinant: int,
    dependent: int,
    conflicts: list[str],
    pairs: Counter[tuple[str, str]],
) -> list[int]:
    """Primeras filas cuyo atributo difiere del más frecuente para su código."""
    majority: dict[str, tuple[int, str]] = {}
    for (x, y), count in pairs.items():
        if x in conflicts and (x not in majority or (count, y) > majority[x]):
            majority[x] = (count, y)
    rows: list[int] = []
    for number, row in enumerate(cells, start=1):
        key, value = row[determinant], row[dependent]
        if key in majority and value is not None and value != majority[key][1]:
            rows.append(number)
            if len(rows) == 5:
                break
    return rows


def dependencies(
    columns: list[AnalyticalColumn], cells: Sequence[Sequence[str | None]]
) -> list[ColumnDependency]:
    found: list[ColumnDependency] = []
    for determinant in columns:
        if determinant.role not in {"identifier", "dimension"}:
            continue
        for dependent in columns:
            if dependent is determinant or dependent.role not in {
                "identifier",
                "dimension",
                "text",
            }:
                continue
            related = bool(tokens(determinant.name) & tokens(dependent.name))
            # Sin nombre compartido sólo se relacionan un código y su atributo (código → x).
            if not related and determinant.role != "identifier":
                continue
            mapping: dict[str, set[str]] = defaultdict(set)
            rows_by_value: Counter[str] = Counter()
            pairs: Counter[tuple[str, str]] = Counter()
            for row in cells:
                x, y = row[determinant.ordinal], row[dependent.ordinal]
                if x is not None and y is not None:
                    mapping[x].add(y)
                    rows_by_value[x] += 1
                    pairs[(x, y)] += 1
            repeated = [x for x in mapping if rows_by_value[x] > 1]
            if len(mapping) < 2 or not repeated:
                continue
            if len({y for ys in mapping.values() for y in ys}) < 2:
                continue
            conflicts = sorted(x for x, ys in mapping.items() if len(ys) > 1)
            holds = len(mapping) - len(conflicts)
            if not (related and holds * 2 >= len(mapping)) and holds * 10 < len(mapping) * 9:
                continue
            # Una dependencia que se cumple sólo se informa desde un código (código → nombre);
            # la inversa (nombre → código) no añade información si no hay conflictos.
            if not conflicts and determinant.role != "identifier":
                continue
            found.append(
                ColumnDependency(
                    determinant=determinant.name,
                    dependent=dependent.name,
                    determinant_values=len(mapping),
                    conflicting_values=len(conflicts),
                    conflicting_rows=sum(rows_by_value[x] for x in conflicts),
                    sample_row_numbers=minority_rows(
                        cells, determinant.ordinal, dependent.ordinal, conflicts, pairs
                    ),
                    examples=[f"{x}: {' / '.join(sorted(mapping[x])[:3])}" for x in conflicts[:5]],
                )
            )
    return found[:10]


def summable_measures(columns: list[AnalyticalColumn]) -> list[AnalyticalColumn]:
    """Medidas que se pueden sumar: importes primero, después cantidades (orden de la fuente)."""
    return sorted(
        (
            c
            for c in columns
            if c.role == "measure" and c.additivity == "additive" and c.currency != "ambiguous"
        ),
        key=lambda c: (not c.monetary, c.ordinal),
    )


def context_of(columns: list[AnalyticalColumn], time: TimeAxis | None) -> str:
    measures = [c for c in columns if c.role == "measure"]
    names = [tokens(c.name) for c in measures]
    sales = time is not None and (
        any(n & SALES and c.additivity == "additive" for n, c in zip(names, measures, strict=True))
        or (any(n & QUANTITY for n in names) and any(n & {"price", "precio"} for n in names))
    )
    products = any(tokens(c.name) & PRODUCTS for c in columns if c.role != "measure")
    inventory = products and any(n & SEMI_ADDITIVE for n in names)
    if sales and inventory:
        return "ambiguous"
    return "sales" if sales else ("inventory" if inventory else "generic")


def analyze(
    profile: DatasetProfile, cells: Sequence[Sequence[str | None]]
) -> AnalyticalInterpretation:
    columns = classify(profile, cells)
    time, _ = row_periods(columns, cells)
    keys = key_candidates(columns, cells)
    found_relationships = relationships(columns, cells)
    found_dependencies = dependencies(columns, cells)
    context = context_of(columns, time)
    measures = [c for c in columns if c.role == "measure"]
    summable = summable_measures(columns)
    limited: list[LimitedAnalysis] = []
    for dependency in found_dependencies:
        if dependency.conflicting_values:
            limited.append(
                LimitedAnalysis(
                    subject=f"Análisis por {dependency.determinant} o {dependency.dependent}",
                    columns=[dependency.determinant, dependency.dependent],
                    reason=(
                        f"{dependency.conflicting_values} valores de {dependency.determinant} "
                        f"aparecen con más de un {dependency.dependent}: no se sabe qué "
                        "entidad representa cada grupo."
                    ),
                )
            )
    for column in measures:
        if column.currency == "ambiguous":
            limited.append(
                LimitedAnalysis(
                    subject=f"Totales de {column.name}",
                    columns=[column.name],
                    reason="Hay varias monedas: no se suman importes sin tipo de cambio.",
                )
            )
    blocked = {name for item in limited for name in item.columns}
    available = ["Conteos, completitud y detalle del archivo."]
    if time is not None and summable:
        available.append(f"Evolución mensual de {summable[0].name}.")
        if len(time.years) > 1:
            available.append(f"Comparación de {summable[0].name} entre años.")
    elif time is not None:
        available.append("Registros por mes (no hay medida sumable).")
    for column in columns:
        if column.role == "dimension" and column.name not in blocked and summable:
            available.append(f"{summable[0].name} por {column.name}.")
    for column in measures:
        if column.additivity in {"non_additive", "unknown"}:
            available.append(f"Promedio simple de {column.name}, sin sumar ni ponderar.")
    limitations = [
        "Las interpretaciones son hipótesis por reglas con su evidencia, no confirmaciones.",
        "No se rellenan vacíos, no se eliminan duplicados ni atípicos y no se convierten "
        "valores ambiguos.",
    ]
    if any(c.monetary and c.currency == "unknown" for c in measures):
        limitations.append("La moneda no figura en los datos: los importes se muestran sin moneda.")
    if any(c.additivity == "semi_additive" for c in measures):
        limitations.append("Saldos y existencias no se suman entre fechas.")
    if time is None:
        limitations.append("No hay eje temporal reconocible: no se analiza evolución.")
    key = keys[0] if keys else None
    row_meaning = {
        "sales": "Cada fila parece una línea de venta",
        "inventory": "Cada fila parece un corte de inventario",
    }.get(context, "Cada fila es un registro")
    if key is not None and key.unique:
        row_meaning += f", única por {', '.join(key.columns)}."
    elif key is not None:
        row_meaning += (
            f"; {', '.join(key.columns)} casi la identifica ({key.duplicate_rows} repeticiones)."
        )
    else:
        row_meaning += "; no se encontró una combinación de columnas que la identifique."
    return AnalyticalInterpretation(
        context=context,
        label=LABELS[context],
        summary=(
            "Se interpretó el papel de cada columna, el periodo y las relaciones con evidencia "
            "calculada sobre todas las filas. Lo que no puede justificarse se limita y se "
            "explica; no hace falta responder nada."
        ),
        row_meaning=row_meaning,
        columns=columns,
        time=time,
        keys=keys,
        relationships=found_relationships,
        dependencies=found_dependencies,
        available_analyses=available,
        limited_analyses=limited,
        limitations=limitations,
    )
