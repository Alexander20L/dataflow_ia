"""Reglas puras de `dataset-inspection-v1` (sin Polars ni base de datos): naturaleza
estadística, rol, grupos, lectura de fechas, frecuencia temporal y diccionario vigente."""

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from dataflow.modules.inspection.contracts import (
    AnnotationRequest,
    ColumnAnnotation,
    ColumnInspection,
    DictionaryEntry,
    Group,
    Inspection,
    Nature,
    Role,
    TechnicalType,
)
from dataflow.platform.errors import ApplicationError

# Textos que suelen significar «sin dato». Se cuentan aparte: nunca se convierten en nulos.
MISSING_TOKENS = frozenset(
    {
        "null",
        "nulo",
        "none",
        "nan",
        "n/a",
        "na",
        "n.a.",
        "n/d",
        "nd",
        "s/d",
        "sin dato",
        "sin datos",
        "no disponible",
        "#n/a",
        "#n/d",
        "-",
        "--",
        "?",
    }
)
NUMBER = re.compile(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d{1,2})?\Z")
INTEGER = re.compile(r"[-+]?(?:0|[1-9]\d*)\Z")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
ISO_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?\Z")
DATE_LIKE = re.compile(r"(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})\Z")
# Patrones para Polars (motor de expresiones regulares de Rust: sin \Z).
LEADING_ZERO = r"^0\d+$"
NUMBER_PATTERN = r"^[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d{1,2})?$"

ROLE_FROM_ANALYSIS: dict[str, Role] = {
    "identifier": "identifier",
    "dimension": "dimension",
    "measure": "measure",
    "time": "time",
    "text": "text",
    "empty": "unknown",
}
ROLE_LABELS: dict[Role, str] = {
    "identifier": "identificador",
    "dimension": "dimensión",
    "measure": "medida",
    "time": "fecha o periodo",
    "category": "categoría",
    "text": "texto descriptivo",
    "unknown": "desconocido",
}
NATURE_LABELS: dict[Nature, str] = {
    "nominal": "cualitativa nominal",
    "ordinal": "cualitativa ordinal",
    "discrete": "cuantitativa discreta",
    "continuous": "cuantitativa continua",
    "temporal": "temporal",
    "unknown": "desconocida",
}
TYPE_LABELS: dict[TechnicalType, str] = {
    "string": "texto",
    "integer": "entero",
    "decimal": "decimal",
    "boolean": "booleano",
    "date": "fecha",
    "datetime": "fecha y hora",
    "empty": "vacía",
}
QUANTITATIVE: frozenset[Nature] = frozenset({"discrete", "continuous"})


def percent(part: int, total: int) -> str:
    """Porcentaje con dos decimales y redondeo half-up (29 de 30 → «96.67»)."""
    if total <= 0:
        return "0.00"
    value = Decimal(part) * 100 / Decimal(total)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def is_missing_token(value: str) -> bool:
    return value.strip().casefold() in MISSING_TOKENS


def technical_type(values: list[str]) -> TechnicalType:
    """Tipo técnico de una columna de texto sobre todos sus valores no nulos (mismas reglas que
    el perfil `profile@4`, más fecha y hora ISO). Basta un valor que no encaje para que la
    columna quede como texto: nunca se fuerza una conversión con pérdida."""
    if not values:
        return "empty"
    if all(len(v) <= 38 and NUMBER.fullmatch(v) for v in values):
        if all(abs(Decimal(v).adjusted()) <= 12 for v in values):
            return "integer" if all(INTEGER.fullmatch(v) for v in values) else "decimal"
        return "string"
    if all(ISO_DATE.fullmatch(v) for v in values):
        try:
            for value in values:
                date.fromisoformat(value)
            return "date"
        except ValueError:
            return "string"
    if all(ISO_DATETIME.fullmatch(v) for v in values):
        return "datetime"
    if all(v.lower() in {"true", "false"} for v in values):
        return "boolean"
    return "string"


def date_readings(value: str) -> set[str]:
    """Formatos válidos para un valor con aspecto de fecha (día/mes/año, mes/día/año,
    año/mes/día). Vacío si no tiene aspecto de fecha o no es válido en ningún formato."""
    match = DATE_LIKE.fullmatch(value.strip())
    if not match:
        return set()
    a, b, c = (int(part) for part in match.groups())
    first, last = match.group(1), match.group(3)
    candidates: dict[str, tuple[int, int, int]] = {}
    if len(first) == 4:
        candidates["year_month_day"] = (a, b, c)
    elif len(last) in {2, 4}:
        year = c if len(last) == 4 else 2000 + c
        candidates["day_month_year"] = (year, b, a)
        candidates["month_day_year"] = (year, a, b)
    valid = set()
    for name, (year, month, day) in candidates.items():
        try:
            date(year, month, day)
            valid.add(name)
        except ValueError:
            continue
    return valid


def is_ambiguous_date(value: str) -> bool:
    """Válida como día/mes y como mes/día con fechas distintas (03/04/2026, no 05/05/2026)."""
    readings = date_readings(value)
    if not {"day_month_year", "month_day_year"} <= readings:
        return False
    match = DATE_LIKE.fullmatch(value.strip())
    assert match
    return int(match.group(1)) != int(match.group(2))


def looks_like_date(value: str) -> bool:
    return DATE_LIKE.fullmatch(value.strip()) is not None


def nature_of(
    technical: TechnicalType, role: Role, time_part: str | None, distinct: int
) -> tuple[Nature, str]:
    """Naturaleza estadística a partir del tipo, el rol y la parte temporal detectada. El
    orden (ordinal) nunca se supone: sólo el usuario puede indicarlo."""
    if technical == "empty":
        return "unknown", "La columna no tiene valores."
    if technical in {"date", "datetime"}:
        return "temporal", "Todos los valores son fechas válidas."
    if role == "time" or time_part in {"year", "month", "date"}:
        return "temporal", "La interpretación automática la reconoce como parte del tiempo."
    if role == "identifier":
        return "nominal", "Identifica registros: sus valores son etiquetas, no cantidades."
    if technical == "boolean":
        return "nominal", "Dos valores posibles (verdadero/falso)."
    if role == "measure" and technical == "integer":
        return "discrete", "Medida con valores enteros: se cuenta, no se mide."
    if role == "measure" and technical == "decimal":
        return "continuous", "Medida con decimales: puede tomar cualquier valor de un rango."
    if technical in {"integer", "decimal"}:
        return (
            "nominal",
            "Números usados como códigos o grupos (la interpretación no la trata como medida).",
        )
    if role == "text":
        return "unknown", "Texto libre: no se trata como variable estadística."
    if distinct <= 1:
        return "nominal", "Un solo valor distinto."
    return "nominal", "Texto con categorías sin orden conocido."


def group_of(nature: Nature, role: Role) -> Group:
    if role == "identifier":
        return "identifier"
    if nature == "temporal" or role == "time":
        return "temporal"
    if nature in QUANTITATIVE:
        return "numeric"
    if nature in {"nominal", "ordinal"}:
        return "categorical"
    return "other"


def month_end(day: date) -> bool:
    return (day + timedelta(days=1)).month != day.month


def frequency_of(days: list[date]) -> str | None:
    """Frecuencia observada (con al menos tres fechas distintas): la unidad más pequeña entre
    fechas consecutivas, si todas las distancias son múltiplos de ella (los saltos mayores son
    periodos que faltan). Diaria, semanal, mensual, trimestral o anual; si no, «irregular»."""
    ordered = sorted(set(days))
    if len(ordered) < 3:
        return None
    pairs = list(zip(ordered, ordered[1:], strict=False))
    gaps = [(b - a).days for a, b in pairs]
    if min(gaps) == 1:
        return "daily"
    if min(gaps) == 7 and all(gap % 7 == 0 for gap in gaps):
        return "weekly"
    same_day = all(a.day == b.day or (month_end(a) and month_end(b)) for a, b in pairs)
    months = [(b.year - a.year) * 12 + b.month - a.month for a, b in pairs]
    if same_day and min(months) >= 1:
        unit = min(months)
        for size, name in ((1, "monthly"), (3, "quarterly"), (12, "yearly")):
            if unit == size and all(m % size == 0 for m in months):
                return name
    return "irregular"


def period_key(day: date, frequency: str) -> str:
    if frequency == "monthly":
        return f"{day.year:04d}-{day.month:02d}"
    if frequency == "quarterly":
        return f"{day.year:04d}-T{(day.month - 1) // 3 + 1}"
    if frequency == "yearly":
        return f"{day.year:04d}"
    return day.isoformat()


def describe(column: ColumnInspection, role: Role, nature: Nature) -> str:
    """Descripción básica y mecánica: tipo, naturaleza, rol y cobertura (sin interpretar el
    negocio, que es de la pestaña Comprensión)."""
    parts = [
        f"{TYPE_LABELS[column.technical_type].capitalize()}, {NATURE_LABELS[nature]}",
        f"rol {ROLE_LABELS[role]}",
        f"{column.distinct} valores distintos",
    ]
    if column.nulls:
        parts.append(f"{column.null_percent} % nulos")
    return "; ".join(parts) + "."


def dictionary(
    inspection: Inspection, annotations: dict[str, ColumnAnnotation], version: UUID
) -> list[DictionaryEntry]:
    """Diccionario vigente: la clasificación automática y, encima, la última corrección del
    usuario para la misma columna de la misma fuente (también de versiones anteriores)."""
    entries = []
    for column in inspection.columns:
        note = annotations.get(column.name)
        role = (note.role if note and note.role else None) or column.role
        nature = (note.nature if note and note.nature else None) or column.nature
        changed = note is not None and (
            (note.role is not None and note.role != column.role)
            or (note.nature is not None and note.nature != column.nature)
            or note.time_format is not None
            or bool(note.notes)
        )
        status = "corrected" if changed else "confirmed" if note and note.confirmed else "automatic"
        if note is None or status == "automatic":
            origin = f"Clasificación automática ({inspection.scope.rules}): {column.nature_reason}"
        else:
            where = (
                "en esta versión"
                if note.version_id == version
                else "en una versión anterior del mismo archivo"
            )
            origin = (
                f"Corrección manual {where}."
                if status == "corrected"
                else f"Clasificación automática confirmada por ti {where}."
            )
        entries.append(
            DictionaryEntry(
                column_id=column.id,
                name=column.name,
                technical_type=column.technical_type,
                nature=nature,
                role=role,
                group=group_of(nature, role),
                description=describe(column, role, nature),
                distinct=column.distinct,
                nulls=column.nulls,
                status=status,
                origin=origin,
                automatic_nature=column.nature,
                automatic_role=column.role,
                time_format=note.time_format if note else None,
                notes=note.notes if note else None,
                inherited=note is not None and note.version_id != version,
                updated_at=note.created_at if note else None,
            )
        )
    return entries


def groups(entries: list[DictionaryEntry]) -> dict[Group, int]:
    counts: dict[Group, int] = {
        "numeric": 0,
        "categorical": 0,
        "temporal": 0,
        "identifier": 0,
        "other": 0,
    }
    for entry in entries:
        counts[entry.group] += 1
    return counts


def validate_annotation(request: AnnotationRequest, column: ColumnInspection) -> None:
    """Combinaciones que no tienen sentido; el resto se acepta tal cual (es metadato)."""
    role = request.role or column.role
    nature = request.nature or column.nature
    if role == "measure" and nature not in QUANTITATIVE:
        raise ApplicationError(
            "ANNOTATION_INVALID",
            "Una medida tiene que ser cuantitativa (discreta o continua).",
            422,
        )
    if nature in QUANTITATIVE and column.technical_type not in {"integer", "decimal"}:
        raise ApplicationError(
            "ANNOTATION_INVALID",
            "Sólo una columna con valores numéricos puede ser cuantitativa.",
            422,
        )
    if request.time_format is not None and nature != "temporal" and role != "time":
        raise ApplicationError(
            "ANNOTATION_INVALID",
            "La interpretación temporal sólo se indica en columnas temporales o de fecha.",
            422,
        )
    if request.notes is not None and len(request.notes.strip()) == 0:
        raise ApplicationError("ANNOTATION_INVALID", "La observación está vacía.", 422)
