"""Cálculo de `dataset-inspection-v2` con Polars sobre la tabla leída completa.

La tabla leída conserva los valores como texto (y las columnas regionales en su celda
canónica): aquí sólo se cuentan, se clasifican y se resumen. Nada se convierte ni se corrige.
Fase 23: dominio evidente de los valores, atípicos (vallas de Tukey), filas repetidas sin los
identificadores, columnas dicotómicas, escalas ordinales candidatas y datos personales.
"""

import io
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import polars as pl

from dataflow.modules.ingestion.contracts import (
    ConvertedColumn,
    KeptColumn,
    SourceFacts,
    SourceReading,
)
from dataflow.modules.inspection.contracts import (
    INSPECTION_RULES,
    Bin,
    CategoricalStats,
    ColumnInspection,
    FileInspection,
    Finding,
    Frequency,
    Group,
    Inspection,
    InspectionScope,
    Missing,
    MixedTypes,
    NumericStats,
    Outliers,
    PeriodCandidate,
    QualityDimension,
    Severity,
    Summary,
    TemporalStats,
    TokenCount,
    ValueDomain,
)
from dataflow.modules.inspection.domain import (
    LEADING_ZERO,
    MISSING_TOKENS,
    NUMBER_PATTERN,
    ROLE_FROM_ANALYSIS,
    date_readings,
    domain_kind,
    frequency_of,
    group_of,
    is_ambiguous_date,
    looks_like_date,
    nature_of,
    ordinal_hint,
    percent,
    period_key,
    personal_hint,
    technical_type,
)
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import AnalyticalColumn, DatasetProfile

TOP = 10
EXAMPLES = 5
SAMPLE_ROWS = 10
MAX_BINS = 20
MAX_PERIODS = 20000
MIN_OUTLIER_VALUES = 8
MILD, EXTREME = 1.5, 3.0  # vallas de Tukey
PERSONAL_SAMPLE = 5000  # valores distintos que se miran para reconocer datos personales

FORMAT_LABELS = {
    "decimal_comma": "coma decimal (1.234,5)",
    "decimal_point_grouped": "punto decimal con miles (1,234.5)",
    "day_month_year": "día/mes/año",
    "month_day_year": "mes/día/año",
    "year_month_day": "año-mes-día",
}
AQ_DIMENSIONS: dict[str, QualityDimension] = {
    "AQ-001": "uniqueness",
    "AQ-002": "consistency",
    "AQ-003": "integrity",
    "AQ-004": "integrity",
    "AQ-005": "validity",
    "AQ-006": "validity",
    "AQ-007": "validity",
    "AQ-008": "consistency",
}
AQ_SEVERITY: dict[str, Severity] = {"blocking": "high", "warning": "medium", "info": "info"}


@dataclass(frozen=True)
class FileMeta:
    file_name: str
    uploaded_at: datetime
    sha256: str
    format: Literal["csv", "xlsx", "pdf", "sqlserver", "other"]
    selection_rule: str | None
    origin: str | None


def number_text(value: float) -> str:
    """Número para mostrar: entero si lo es; si no, hasta seis decimales sin ceros de más."""
    if math.isfinite(value) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def severity_by_share(part: int, total: int) -> Severity:
    share = part / total if total else 0
    return "high" if share >= 0.5 else "medium" if share >= 0.1 else "low"


def rows_where(mask: pl.Series) -> list[int]:
    """Números de fila (desde 1) donde la máscara es verdadera, los primeros SAMPLE_ROWS."""
    return [int(i) + 1 for i in mask.arg_true().head(SAMPLE_ROWS).to_list()]


def histogram(numbers: pl.Series, technical: str) -> tuple[list[Bin], str]:
    distinct = numbers.n_unique()
    if technical == "integer" and distinct <= MAX_BINS:
        counts = numbers.value_counts(sort=False).sort(numbers.name)
        return (
            [
                Bin(label=number_text(float(v)), lower=None, upper=None, count=int(c))
                for v, c in counts.iter_rows()
            ],
            "Frecuencia de cada valor (enteros con pocos valores distintos).",
        )
    low, high = float(cast(float, numbers.min())), float(cast(float, numbers.max()))
    if low == high:
        return (
            [
                Bin(
                    label=number_text(low),
                    lower=number_text(low),
                    upper=number_text(high),
                    count=numbers.len(),
                )
            ],
            "Un único valor.",
        )
    bins = min(MAX_BINS, math.ceil(math.log2(numbers.len())) + 1)
    width = (high - low) / bins
    index = ((numbers - low) / width).floor().cast(pl.Int64).clip(0, bins - 1)
    positions = Counter(index.to_list())
    result = []
    for position in range(bins):
        lower, upper = low + position * width, low + (position + 1) * width
        closing = "]" if position == bins - 1 else ")"
        result.append(
            Bin(
                label=f"[{number_text(lower)}, {number_text(upper)}{closing}",
                lower=number_text(lower),
                upper=number_text(upper),
                count=positions.get(position, 0),
            )
        )
    return result, f"{bins} intervalos de igual ancho (regla de Sturges, máximo {MAX_BINS})."


def fences(q1: float, q3: float, factor: float) -> tuple[float, float]:
    spread = q3 - q1
    return q1 - factor * spread, q3 + factor * spread


def outlier_stats(numbers: pl.Series, q1: float, q3: float) -> Outliers | None:
    """Vallas de Tukey con los mismos cuartiles que se muestran (interpolación lineal). Sin
    dispersión (IQR = 0) o con menos de MIN_OUTLIER_VALUES valores no se calcula."""
    if numbers.len() < MIN_OUTLIER_VALUES or q3 - q1 <= 0:
        return None
    low, high = fences(q1, q3, MILD)
    far_low, far_high = fences(q1, q3, EXTREME)
    return Outliers(
        mild_lower=number_text(low),
        mild_upper=number_text(high),
        extreme_lower=number_text(far_low),
        extreme_upper=number_text(far_high),
        count=int(((numbers < low) | (numbers > high)).sum()),
        extreme=int(((numbers < far_low) | (numbers > far_high)).sum()),
        method="Vallas de Tukey: atípico fuera de [Q1 − 1,5·IQR, Q3 + 1,5·IQR] y extremo fuera de "
        "[Q1 − 3·IQR, Q3 + 3·IQR], con los cuartiles de esta columna. Es un aviso: no se elimina "
        "ni se corrige ningún valor.",
    )


def numeric_stats(values: pl.Series, technical: str) -> NumericStats:
    numbers = values.cast(pl.Float64).alias("value")
    bins, method = histogram(numbers, technical)
    std = numbers.std(ddof=1) if numbers.len() >= 2 else None
    q1 = float(cast(float, numbers.quantile(0.25, "linear")))
    q3 = float(cast(float, numbers.quantile(0.75, "linear")))
    return NumericStats(
        count=numbers.len(),
        minimum=number_text(float(cast(float, numbers.min()))),
        maximum=number_text(float(cast(float, numbers.max()))),
        mean=number_text(float(cast(float, numbers.mean()))),
        median=number_text(float(cast(float, numbers.median()))),
        std=number_text(float(cast(float, std))) if std is not None else None,
        q1=number_text(q1),
        q3=number_text(q3),
        histogram=bins,
        method="Sobre todos los valores no nulos; cuartiles por interpolación lineal; "
        "desviación estándar muestral (n − 1). " + method,
        outliers=outlier_stats(numbers, q1, q3),
    )


def expected_periods(first: date, last: date, frequency: str) -> list[str] | None:
    keys: list[str] = []
    if frequency == "daily":
        if (last - first).days > MAX_PERIODS:
            return None
        return [(first + timedelta(days=d)).isoformat() for d in range((last - first).days + 1)]
    step = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(frequency)
    if step is None:
        return None
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month) and len(keys) <= MAX_PERIODS:
        keys.append(period_key(date(year, month, 1), frequency))
        month += step
        while month > 12:
            year, month = year + 1, month - 12
    return keys


def temporal_from_dates(days: list[date], minimum: str, maximum: str) -> TemporalStats:
    frequency = frequency_of(days)
    distinct = sorted(set(days))
    missing: list[str] = []
    missing_count: int | None = None
    if frequency in {"daily", "monthly", "quarterly", "yearly"}:
        assert frequency is not None
        seen = {period_key(d, frequency) for d in distinct}
        expected = expected_periods(distinct[0], distinct[-1], frequency)
        if expected is not None:
            gaps = [key for key in dict.fromkeys(expected) if key not in seen]
            missing_count, missing = len(gaps), gaps[:SAMPLE_ROWS]
    return TemporalStats(
        minimum=minimum,
        maximum=maximum,
        span_days=(distinct[-1] - distinct[0]).days if distinct else None,
        frequency=cast(
            Literal["daily", "weekly", "monthly", "quarterly", "yearly", "irregular"] | None,
            frequency,
        ),
        distinct_periods=len(distinct),
        missing_periods=missing_count,
        missing_sample=missing,
        method="Frecuencia: la diferencia más común entre fechas distintas consecutivas. "
        "Periodos faltantes: los del calendario entre la primera y la última fecha que no "
        "aparecen (sólo con frecuencia diaria, mensual, trimestral o anual).",
    )


def year_stats(values: pl.Series) -> TemporalStats:
    years = sorted({int(v) for v in values.to_list()})
    seen = set(years)
    gaps = [str(y) for y in range(years[0], years[-1] + 1) if y not in seen]
    return TemporalStats(
        minimum=str(years[0]),
        maximum=str(years[-1]),
        span_days=None,
        frequency="yearly" if len(years) >= 2 else None,
        distinct_periods=len(years),
        missing_periods=len(gaps),
        missing_sample=gaps[:SAMPLE_ROWS],
        method="Años enteros: faltan los años entre el primero y el último que no aparecen.",
    )


def categorical(values: pl.Series, rows: int) -> CategoricalStats:
    counts = (
        values.alias("value")
        .value_counts(sort=False, name="count")
        .sort(["count", "value"], descending=[True, False])
    )
    top = counts.head(TOP)
    shown = int(top.get_column("count").sum()) if top.height else 0
    return CategoricalStats(
        distinct=counts.height,
        top=[
            Frequency(value=str(v)[:200], count=int(c), percent=percent(int(c), rows))
            for v, c in top.iter_rows()
        ],
        others=values.len() - shown,
    )


def finding(
    kind: str,
    dimension: QualityDimension,
    title: str,
    columns: list[str],
    affected: int,
    rows: int,
    description: str,
    severity: Severity,
    examples: list[str] | None = None,
    sample: list[int] | None = None,
    source: Literal["dataset-inspection-v2", "automatic-quality-v1"] = "dataset-inspection-v2",
) -> Finding:
    return Finding(
        id=f"{kind}:{'|'.join(columns)}"[:300],
        dimension=dimension,
        kind=kind,
        title=title,
        columns=columns,
        affected_rows=affected,
        percent=percent(affected, rows),
        examples=[e[:120] for e in (examples or [])][:EXAMPLES],
        sample_rows=(sample or [])[:SAMPLE_ROWS],
        description=description,
        severity=severity,
        source=source,
    )


@dataclass(frozen=True)
class ColumnResult:
    column: ColumnInspection
    findings: list[Finding]
    nulls: int


def token_counts(present: pl.Series, lowered: pl.Series, is_token: pl.Series) -> list[TokenCount]:
    """Textos de «sin dato» agrupados sin mayúsculas ni espacios, con sus escrituras exactas."""
    raw = present.filter(is_token).to_list()
    keys = lowered.filter(is_token).to_list()
    counts: Counter[str] = Counter(keys)
    variants: dict[str, list[str]] = {}
    for key, value in zip(keys, raw, strict=True):
        spellings = variants.setdefault(key, [])
        if value not in spellings and len(spellings) < 10:
            spellings.append(value[:50])
    return [
        TokenCount(token=token, count=count, variants=sorted(variants[token]))
        for token, count in sorted(counts.items())
    ]


def inspect_column(
    index: int,
    name: str,
    series: pl.Series,
    column_id: UUID,
    rows: int,
    info: AnalyticalColumn | None,
    converted: dict[str, ConvertedColumn],
    kept: dict[str, KeptColumn],
) -> ColumnResult:
    """Perfil y diagnóstico de una columna sobre todos sus valores (sin corregir nada)."""
    text = (series if series.dtype == pl.String else series.cast(pl.String)).alias("value")
    nulls = text.null_count()
    present = text.drop_nulls()
    stripped = present.str.strip_chars()
    empty = int((present == "").sum())
    whitespace = int(((stripped == "") & (present != "")).sum())
    lowered = stripped.str.to_lowercase()
    is_token = lowered.is_in(list(MISSING_TOKENS))
    tokens = token_counts(present, lowered, is_token)
    meaningful = present.filter((stripped != "") & ~is_token)
    technical = technical_type(present.to_list())
    role = ROLE_FROM_ANALYSIS.get(info.role, "unknown") if info else "unknown"
    if technical == "empty":
        role = "unknown"
    distinct = present.n_unique()
    nature, reason = nature_of(technical, role, info.time_part if info else None, distinct)
    stats_numeric = stats_temporal = stats_categorical = None
    if nature in {"discrete", "continuous"} and present.len():
        stats_numeric = numeric_stats(present, technical)
    elif nature == "temporal" and technical in {"date", "datetime"} and present.len():
        days = present.str.slice(0, 10).str.to_date("%Y-%m-%d").to_list()
        stats_temporal = temporal_from_dates(
            cast(list[date], days), str(present.min()), str(present.max())
        )
    elif nature == "temporal" and info and info.time_part == "year" and technical == "integer":
        stats_temporal = year_stats(present)
    if nature in {"nominal", "ordinal"} and role != "identifier" and present.len():
        stats_categorical = categorical(present, rows)
    elif nature == "temporal" and stats_temporal is None and present.len():
        stats_categorical = categorical(present, rows)

    zeros = int(present.str.contains(LEADING_ZERO).sum()) if technical == "string" else 0
    mixed = None
    if technical == "string" and meaningful.len():
        numeric_mask = meaningful.str.contains(NUMBER_PATTERN)
        numeric_count = int(numeric_mask.sum())
        text_count = meaningful.len() - numeric_count
        if numeric_count and text_count:
            minority = ~numeric_mask if numeric_count >= text_count else numeric_mask
            mixed = MixedTypes(
                numeric=numeric_count,
                text=text_count,
                examples=[v[:120] for v in dict.fromkeys(meaningful.filter(minority).to_list())][
                    :EXAMPLES
                ],
            )
    note = None
    if name in converted:
        note = converted[name].explanation
    elif name in kept:
        note = f"Se dejó como texto: {kept[name].reason}"

    # --- Fase 23: dominio, dicotomía, escala ordinal candidata y datos personales ---
    distinct_values = meaningful.unique()
    numbers = text.cast(pl.Float64, strict=False) if nature in {"discrete", "continuous"} else None
    value_domain = None
    outside = None
    rule = domain_kind(name) if numbers is not None else None
    if rule is not None and numbers is not None:
        kind, why = rule
        outside = (numbers < 0) | (numbers > 100) if kind == "percent" else numbers < 0
        outside = outside.fill_null(False)
        value_domain = ValueDomain(
            kind=cast(Literal["percent", "non_negative"], kind),
            lower="0",
            upper="100" if kind == "percent" else None,
            outside=int(outside.sum()),
            reason=why,
        )
    dichotomous = role != "identifier" and technical != "empty" and distinct_values.len() == 2
    ordinal = (
        ordinal_hint(name, technical, role, distinct_values.to_list())
        if nature in {"discrete", "nominal"}
        else None
    )
    personal = (
        personal_hint(name, technical, distinct_values.head(PERSONAL_SAMPLE).to_list(), role)
        if role != "time"
        else None
    )

    column = ColumnInspection(
        id=column_id,
        ordinal=index,
        name=name,
        technical_type=technical,
        nature=nature,
        nature_reason=reason,
        role=role,
        role_evidence=list(info.evidence) if info else [],
        group=group_of(nature, role),
        count=present.len(),
        nulls=nulls,
        null_percent=percent(nulls, rows),
        distinct=distinct,
        distinct_percent=percent(distinct, rows),
        examples=[v[:120] for v in dict.fromkeys(present.head(1000).to_list())][:3],
        missing=Missing(
            nulls=nulls,
            empty_strings=empty,
            whitespace=whitespace,
            tokens=tokens,
        ),
        leading_zeros=zeros,
        mixed=mixed,
        numeric=stats_numeric,
        temporal=stats_temporal,
        categorical=stats_categorical,
        reading=note,
        dichotomous=dichotomous,
        domain=value_domain,
        ordinal_candidate=ordinal,
        personal=personal,
    )

    # --- Diagnóstico de la columna (sin corregir nada) ---
    findings: list[Finding] = []
    if nulls:
        findings.append(
            finding(
                "missing_values",
                "completeness",
                f"Valores nulos en «{name}»",
                [name],
                nulls,
                rows,
                "Celdas sin valor en el original (una celda vacía se lee como nula).",
                severity_by_share(nulls, rows),
                sample=rows_where(text.is_null()),
            )
        )
    if tokens:
        count = sum(t.count for t in tokens)
        findings.append(
            finding(
                "missing_tokens",
                "completeness",
                f"Posibles faltantes escritos como texto en «{name}»",
                [name],
                count,
                rows,
                "Valores como «N/A» o «-» suelen significar «sin dato», pero no se cuentan "
                "como nulos ni se convierten: se conservan tal cual. Puedes declararlos como "
                "nulos en el Diccionario (se crea una versión derivada; el original no cambia).",
                "low",
                examples=[t.token for t in tokens],
                sample=rows_where(
                    text.str.strip_chars().str.to_lowercase().is_in(list(MISSING_TOKENS))
                ),
            )
        )
    if empty or whitespace:
        findings.append(
            finding(
                "blank_text",
                "completeness",
                f"Celdas en blanco en «{name}»",
                [name],
                empty + whitespace,
                rows,
                "Celdas con texto vacío o sólo espacios: no son nulas y se conservan.",
                "low",
                sample=rows_where(text.str.strip_chars() == ""),
            )
        )
    if mixed is not None:
        findings.append(
            finding(
                "mixed_types",
                "format",
                f"Tipos mixtos en «{name}»",
                [name],
                min(mixed.numeric, mixed.text),
                rows,
                f"{mixed.numeric} valores numéricos y {mixed.text} de texto: la columna se "
                "conserva como texto para no perder información. Los ejemplos son del grupo "
                "minoritario.",
                "medium",
                examples=mixed.examples,
            )
        )
    if zeros and technical == "string":
        findings.append(
            finding(
                "leading_zeros",
                "format",
                f"Códigos con ceros iniciales en «{name}»",
                [name],
                zeros,
                rows,
                "Valores como «00125» se conservan como texto con sus ceros: no se tratan "
                "como números.",
                "info",
                examples=present.filter(present.str.contains(LEADING_ZERO))
                .head(EXAMPLES)
                .to_list(),
            )
        )
    if technical == "string" and meaningful.len():
        dated = [v for v in meaningful.unique().to_list() if looks_like_date(v)]
        if dated and len(dated) * 2 >= meaningful.n_unique():
            invalid = sorted(v for v in dated if not date_readings(v))
            ambiguous = sorted(v for v in dated if is_ambiguous_date(v))
            if invalid:
                mask = text.is_in(invalid)
                findings.append(
                    finding(
                        "invalid_dates",
                        "validity",
                        f"Fechas inválidas en «{name}»",
                        [name],
                        int(mask.sum()),
                        rows,
                        "Valores con forma de fecha que no existen en ningún formato "
                        "(día/mes/año, mes/día/año ni año-mes-día).",
                        "medium",
                        examples=invalid,
                        sample=rows_where(mask.fill_null(False)),
                    )
                )
            if ambiguous:
                mask = text.is_in(ambiguous)
                findings.append(
                    finding(
                        "ambiguous_dates",
                        "format",
                        f"Fechas ambiguas en «{name}»",
                        [name],
                        int(mask.sum()),
                        rows,
                        "Pueden leerse como día/mes o como mes/día y ningún valor del archivo "
                        "lo decide: no se eligió ninguna interpretación y la columna sigue "
                        "como texto. Puedes anotar la correcta en el Diccionario.",
                        "medium",
                        examples=ambiguous,
                        sample=rows_where(mask.fill_null(False)),
                    )
                )
    if name in kept and kept[name].kind == "number":
        findings.append(
            finding(
                "conversion_not_applied",
                "validity",
                f"Conversión no aplicada en «{name}»",
                [name],
                present.len(),
                rows,
                f"La lectura no convirtió la columna: {kept[name].reason}",
                "low",
            )
        )
    if role == "identifier" and present.len():
        repeated = text.is_duplicated() & text.is_not_null()
        count = int(repeated.sum())
        if count:
            findings.append(
                finding(
                    "duplicate_identifier",
                    "uniqueness",
                    f"Identificadores repetidos en «{name}»",
                    [name],
                    count,
                    rows,
                    "Registros que comparten el mismo valor de una columna que parece "
                    "identificador. No se elimina ninguno.",
                    "medium",
                    examples=[str(v) for v in text.filter(repeated).unique().head(EXAMPLES)],
                    sample=rows_where(repeated),
                )
            )
    if value_domain is not None and outside is not None and value_domain.outside:
        assert numbers is not None
        bad = numbers.filter(outside)
        findings.append(
            finding(
                "out_of_range",
                "validity",
                f"Valores fuera de rango en «{name}»",
                [name],
                value_domain.outside,
                rows,
                (
                    "Valores fuera de 0–100 en una columna que, por su nombre, es un porcentaje."
                    if value_domain.kind == "percent"
                    else "Valores negativos en una columna que, por su nombre, no debería tenerlos."
                )
                + " No se corrigen: revisa si son errores de captura.",
                "medium",
                examples=[number_text(float(v)) for v in bad.unique().sort().head(EXAMPLES)],
                sample=rows_where(outside),
            )
        )
    outliers = stats_numeric.outliers if stats_numeric else None
    if outliers is not None and outliers.count and numbers is not None:
        low, high = float(outliers.mild_lower), float(outliers.mild_upper)
        mask = ((numbers < low) | (numbers > high)).fill_null(False)
        values = numbers.filter(mask)
        far = sorted({float(v) for v in values.to_list()}, key=lambda v: -abs(v - (low + high) / 2))
        findings.append(
            finding(
                "outliers",
                "validity",
                f"Valores atípicos en «{name}»",
                [name],
                outliers.count,
                rows,
                f"{outliers.count} valores fuera de [{outliers.mild_lower}, "
                f"{outliers.mild_upper}] (Q1 − 1,5·IQR, Q3 + 1,5·IQR); {outliers.extreme} de ellos "
                f"extremos (fuera de [{outliers.extreme_lower}, {outliers.extreme_upper}]). Un "
                "valor atípico no es un error: se conserva para que lo revises.",
                "info",
                examples=[number_text(v) for v in far[:EXAMPLES]],
                sample=rows_where(mask),
            )
        )
    return ColumnResult(column, findings, nulls)


def inspect_columns(
    frame: pl.DataFrame,
    ids: list[UUID],
    profile: DatasetProfile,
    reading: SourceReading | None,
) -> list[ColumnResult]:
    """Perfil y diagnóstico de todas las columnas. Es también la clasificación de partida de la
    comprensión (Fase 23): mismas reglas sobre la misma tabla, mismo resultado."""
    analysis = profile.overview.analysis if profile.overview else None
    analytical: dict[str, AnalyticalColumn] = (
        {c.name: c for c in analysis.columns} if analysis else {}
    )
    converted = {c.column: c for c in (reading.converted if reading else [])}
    kept = {c.column: c for c in (reading.kept_as_text if reading else [])}
    return [
        inspect_column(
            index,
            name,
            frame.get_column(name),
            ids[index] if index < len(ids) else UUID(int=index),
            frame.height,
            analytical.get(name),
            converted,
            kept,
        )
        for index, name in enumerate(frame.columns)
    ]


def classify_table(
    content: bytes, ids: list[UUID], profile: DatasetProfile
) -> list[ColumnInspection]:
    """Clasificación automática de las columnas de una tabla leída (para la comprensión)."""
    frame = pl.read_parquet(io.BytesIO(content))
    return [result.column for result in inspect_columns(frame, ids, profile, None)]


def inspect(
    content: bytes,
    ids: list[UUID],
    profile: DatasetProfile,
    quality: QualityReport | None,
    reading: SourceReading | None,
    facts: SourceFacts | None,
    meta: FileMeta,
    scope: InspectionScope,
) -> Inspection:
    frame = pl.read_parquet(io.BytesIO(content))
    rows = frame.height
    analysis = profile.overview.analysis if profile.overview else None
    results = inspect_columns(frame, ids, profile, reading)
    columns = [r.column for r in results]
    findings = [f for r in results for f in r.findings]
    missing_cells = sum(r.nulls for r in results)

    neutral = pl.DataFrame(
        [frame.get_column(n).alias(f"c{i}") for i, n in enumerate(frame.columns)]
    )
    repeats = ~neutral.select(pl.struct(pl.all()).is_first_distinct()).to_series()
    duplicates = int(repeats.sum())
    if duplicates:
        findings.append(
            finding(
                "duplicate_rows",
                "uniqueness",
                "Filas duplicadas",
                [],
                duplicates,
                rows,
                "Copias exactas de una fila anterior (todas las columnas iguales). No se elimina "
                "ninguna: el recuento es de las copias, sin la primera aparición.",
                "medium",
                sample=rows_where(repeats),
            )
        )
    # Fase 23: con identificadores, dos filas iguales en todo lo demás también son repetidas
    # (el identificador distinto puede ocultar un registro cargado dos veces).
    identifiers = [c.name for c in columns if c.role == "identifier"]
    rest = [i for i, c in enumerate(columns) if c.role != "identifier"]
    without_ids: int | None = None
    if identifiers and rest:
        others = neutral.select([f"c{i}" for i in rest])
        repeated = ~others.select(pl.struct(pl.all()).is_first_distinct()).to_series()
        without_ids = int(repeated.sum())
        if without_ids > duplicates:
            findings.append(
                finding(
                    "duplicate_rows_without_ids",
                    "uniqueness",
                    "Filas repetidas sin contar los identificadores",
                    identifiers,
                    without_ids,
                    rows,
                    "Filas iguales a una anterior en todas las columnas salvo "
                    f"{', '.join(f'«{n}»' for n in identifiers)}: pueden ser el mismo registro "
                    "cargado dos veces con otro identificador, o registros legítimos. No se "
                    "elimina ninguna.",
                    "medium",
                    sample=rows_where(repeated),
                )
            )
    # El atípico extremo de la calidad automática (AQ-007, 3·IQR) ya está en el aviso de
    # atípicos de la inspección de esa columna (1,5·IQR y 3·IQR): no se repite.
    covered = {c.name for c in columns if c.numeric is not None and c.numeric.outliers is not None}
    for item in quality.analytical.findings if quality and quality.analytical else []:
        if item.check == "AQ-007" and set(item.columns) <= covered:
            continue
        findings.append(
            finding(
                f"automatic:{item.check}",
                AQ_DIMENSIONS[item.check],
                item.title,
                item.columns,
                item.affected_rows,
                rows,
                " ".join(item.evidence[:3])
                + (
                    " Un valor extremo no se considera un error ni se elimina."
                    if item.check == "AQ-007"
                    else ""
                ),
                AQ_SEVERITY[item.severity],
                sample=[n for n in item.sample_row_numbers][:SAMPLE_ROWS],
                source="automatic-quality-v1",
            ).model_copy(update={"id": item.id})
        )
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order[f.severity], f.dimension, f.id))

    periods = []
    if analysis and analysis.time and analysis.time.kind == "year_month":
        axis = analysis.time
        periods.append(
            PeriodCandidate(
                columns=axis.columns,
                periods=axis.periods,
                first=axis.first,
                last=axis.last,
                unparsed_rows=axis.unparsed_rows,
                note="Año y Mes podrían formar un periodo mensual. No se creó ninguna fecha "
                "ni columna nueva: es una lectura posible que puedes confirmar en el Diccionario.",
            )
        )

    cells = rows * frame.width
    automatic_groups: dict[Group, int] = {
        "numeric": 0,
        "categorical": 0,
        "temporal": 0,
        "identifier": 0,
        "other": 0,
    }
    for column in columns:
        automatic_groups[column.group] += 1
    dates = sorted(
        {
            FORMAT_LABELS[c.format]
            for c in (reading.converted if reading else [])
            if c.kind == "date"
        }
    )
    header = (
        f"Fila {facts.header_row} de «{facts.sheet}»"
        if facts and facts.format == "xlsx" and facts.header_row
        else f"Primera fila del archivo ({frame.width} columnas)"
    )
    rules = ["Celda vacía = nulo (no se inventan valores)", INSPECTION_RULES]
    if reading:
        rules.insert(0, reading.rule)
    if meta.selection_rule:
        rules.insert(0, meta.selection_rule)
    if facts:
        rules.append(facts.rule)
    file = FileInspection(
        file_name=meta.file_name,
        format=meta.format,
        uploaded_at=meta.uploaded_at,
        size_bytes=facts.size_bytes if facts else None,
        sha256=meta.sha256,
        encoding=(reading.encoding if reading else None) or (facts.encoding if facts else None),
        separator=(reading.separator if reading else None) or (facts.separator if facts else None),
        decimal_convention=FORMAT_LABELS.get(reading.convention or "") if reading else None,
        date_convention=", ".join(dates) or None,
        header=header,
        blank_lines=facts.blank_lines if facts else None,
        sheets=facts.sheets if facts else [],
        sheet=facts.sheet if facts else None,
        table=facts.table if facts else None,
        used_range=facts.used_range if facts else None,
        empty_rows=facts.empty_rows if facts else None,
        empty_columns=facts.empty_columns if facts else [],
        formula_cells=facts.formula_cells if facts else None,
        date_cells=facts.date_cells if facts else None,
        inexact_numbers=facts.inexact_numbers if facts else None,
        selection_rule=meta.selection_rule,
        converted=reading.converted if reading else [],
        kept_as_text=reading.kept_as_text if reading else [],
        rules=rules,
        problems=(facts.problems if facts else []) + ([meta.origin] if meta.origin else []),
    )
    limitations = [
        f"Todas las cifras se calculan sobre los {rows} registros leídos, sin muestras.",
        "Las columnas que la lectura regional convirtió se muestran en su formato canónico "
        "(por ejemplo, 1234.5); el original se puede descargar sin cambios.",
        "El orden de una variable (cualitativa ordinal) nunca se supone: las escalas candidatas "
        "se señalan y sólo cuentan si las confirmas en el Diccionario.",
        "Los rangos esperados (porcentajes, cantidades no negativas) se deducen del nombre de la "
        "columna; los atípicos y los valores fuera de rango son avisos y no se corrigen.",
        "Los datos personales se reconocen por el nombre de la columna y el formato de los "
        "valores; esas columnas nunca se envían a la IA.",
        "La memoria es la estimación de Polars para la tabla leída.",
    ]
    if analysis is None:
        limitations.append(
            "Esta carga no tiene interpretación analítica: los roles quedan como desconocidos."
        )
    return Inspection(
        scope=scope,
        summary=Summary(
            rows=rows,
            columns=frame.width,
            cells=cells,
            missing_cells=missing_cells,
            completeness_percent=percent(cells - missing_cells, cells),
            duplicate_rows=duplicates,
            memory_bytes=int(frame.estimated_size()),
            groups=automatic_groups,
            duplicate_rows_without_ids=without_ids,
            identifier_columns=identifiers,
            personal_columns=[c.name for c in columns if c.personal is not None],
        ),
        columns=columns,
        findings=findings,
        periods=periods,
        file=file,
        limitations=limitations,
    )
