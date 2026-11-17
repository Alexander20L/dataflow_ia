"""Reglas puras de `dataset-inspection-v2` (sin Polars ni base de datos): naturaleza
estadística, rol, grupos, lectura de fechas, frecuencia temporal, diccionario vigente y, desde la
Fase 23, dominio evidente de los valores, columnas dicotómicas, escalas ordinales candidatas y
datos personales."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from dataflow.modules.inspection.contracts import (
    AnnotationRequest,
    ColumnAnnotation,
    ColumnInspection,
    DictionaryEntry,
    Group,
    Nature,
    OrdinalHint,
    PersonalHint,
    PersonalKind,
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

# --- Fase 23: pistas por el nombre de la columna -------------------------------------------------
# Se comparan palabras del nombre sin tildes ni mayúsculas («Asistencia_Pct» → asistencia, pct).
PERCENT_WORDS = frozenset({"pct", "porc", "porcentaje", "percent", "percentage", "pcnt"})
NON_NEGATIVE_WORDS = frozenset(
    {
        "edad",
        "age",
        "cantidad",
        "quantity",
        "qty",
        "unidades",
        "units",
        "precio",
        "price",
        "horas",
        "hours",
        "stock",
        "peso",
        "weight",
        "altura",
        "height",
        "duracion",
        "duration",
        "asistencia",
        "attendance",
        # Fase 28
        "dias",
        "ausencia",
        "ausencias",
        "faltas",
        "tardanzas",
        "antiguedad",
    }
)
# Fase 28: escalas de valoración (se reconocen por el nombre y se acotan por los valores).
RATING_WORDS = frozenset(
    {
        "evaluacion",
        "puntuacion",
        "puntaje",
        "calificacion",
        "valoracion",
        "satisfaccion",
        "rating",
        "score",
    }
)
RATING_SCALES = [(1, 5), (0, 5), (1, 10), (0, 10)]
ORDINAL_WORDS = frozenset(
    {
        "ciclo",
        "nivel",
        "grado",
        "semestre",
        "curso",
        "escala",
        "rating",
        "valoracion",
        "estrellas",
        "stars",
        "prioridad",
        "priority",
        "level",
        "grade",
        "tier",
        "etapa",
        "fase",
        "satisfaccion",
        "satisfaction",
    }
)
MAX_ORDINAL_VALUES = 12
PersonalStatus = Literal["automatic", "confirmed", "rejected", "marked"]
NAME_WORDS = frozenset(
    {"nombre", "nombres", "apellido", "apellidos", "name", "names", "surname", "fullname"}
)
# Si el nombre habla de un objeto y no de una persona («nombre_producto»), no es dato personal.
NOT_A_PERSON = frozenset(
    {
        "producto",
        "product",
        "empresa",
        "company",
        "categoria",
        "category",
        "curso",
        "course",
        "carrera",
        "archivo",
        "file",
        "tienda",
        "store",
        "item",
        "articulo",
        "region",
        "ciudad",
        "city",
        "pais",
        "country",
        "marca",
        "brand",
        "proyecto",
        "project",
        "campana",
        "campaign",
        "departamento",
        "department",
        "area",
        "sede",
        "sucursal",
        "branch",
        "plan",
        "servicio",
        "service",
    }
)
DOCUMENT_WORDS = frozenset(
    {"dni", "documento", "pasaporte", "passport", "ssn", "cedula", "nif", "nie", "curp"}
)
EMAIL_WORDS = frozenset({"email", "correo", "mail"})
PHONE_WORDS = frozenset({"telefono", "celular", "movil", "phone", "mobile", "tel", "whatsapp"})
ADDRESS_WORDS = frozenset({"direccion", "address", "domicilio", "calle"})
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}\Z")
PHONE = re.compile(r"\+?\d[\d\s().-]{5,18}\d\Z")
DOCUMENT = re.compile(r"[A-Za-z]?\d{6,12}[A-Za-z]?\Z")
PERSONAL_SHARE = Decimal("0.8")  # parte de los valores que debe tener el formato esperado


def words(name: str) -> list[str]:
    """Palabras de un nombre de columna, sin tildes ni mayúsculas (snake, kebab y CamelCase)."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    folded = unicodedata.normalize("NFKD", spaced.casefold())
    plain = "".join(c for c in folded if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z0-9]+", plain) if w]


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


def domain_kind(name: str) -> tuple[str, str] | None:
    """Dominio evidente por el nombre: («percent» | «non_negative», motivo). Sólo se comprueba en
    columnas cuantitativas; un valor fuera del dominio es un aviso, nunca se corrige."""
    found = set(words(name))
    if found & PERCENT_WORDS or "%" in name:
        return "percent", "El nombre indica un porcentaje: se espera un valor entre 0 y 100."
    if found & RATING_WORDS:
        word = sorted(found & RATING_WORDS)[0]
        return "rating", f"El nombre indica una escala de valoración («{word}»)"
    if found & NON_NEGATIVE_WORDS:
        word = sorted(found & NON_NEGATIVE_WORDS)[0]
        return "non_negative", f"El nombre indica una cantidad («{word}»): no se espera negativa."
    return None


def rating_scale(minimum: float, maximum: float) -> tuple[int, int] | None:
    """La escala de valoración más estrecha que contiene todos los valores (1–5, 0–5, 1–10 u
    0–10); None si los valores no caben en ninguna."""
    return next(
        ((low, high) for low, high in RATING_SCALES if low <= minimum and maximum <= high), None
    )


def ordinal_hint(
    name: str, technical: TechnicalType, role: Role, values: Sequence[str]
) -> OrdinalHint | None:
    """Enteros con pocos valores distintos que parecen una escala ordenada (un ciclo, un nivel,
    una valoración 1–5). `values`: los valores distintos no nulos. Nunca se aplica sola."""
    if technical != "integer" or role not in {"measure", "dimension"}:
        return None
    if not 3 <= len(values) <= MAX_ORDINAL_VALUES:
        return None
    numbers = sorted({int(v) for v in values})
    order = [str(n) for n in numbers]
    named = sorted(set(words(name)) & ORDINAL_WORDS)
    if named:
        return OrdinalHint(
            order=order,
            reason=f"Enteros con {len(numbers)} valores y nombre de escala («{named[0]}»): "
            "parece un orden (por ejemplo, un ciclo o un nivel), no una cantidad.",
        )
    contiguous = numbers == list(range(numbers[0], numbers[-1] + 1))
    if contiguous and numbers[0] in {0, 1} and numbers[-1] in {3, 4, 5, 7, 10}:
        return OrdinalHint(
            order=order,
            reason=f"Enteros consecutivos de {numbers[0]} a {numbers[-1]}: parece una escala "
            "de valoración, no una cantidad.",
        )
    return None


def share(values: Sequence[str], pattern: re.Pattern[str]) -> bool:
    if not values:
        return False
    matched = sum(1 for v in values if pattern.fullmatch(v.strip()))
    return Decimal(matched) >= PERSONAL_SHARE * len(values)


def personal_hint(
    name: str, technical: TechnicalType, values: Sequence[str], role: Role = "text"
) -> PersonalHint | None:
    """Columna que parece contener datos de personas: por el nombre y, salvo nombres propios y
    direcciones, también por el formato de los valores. `values`: valores distintos no nulos.
    Un nombre o una dirección sólo se marcan si la columna es texto libre: un nombre que se
    repite y agrupa registros («Customer_Name» en ventas) es una dimensión del negocio; el
    usuario puede marcarla a mano."""
    found = set(words(name))
    if found & NOT_A_PERSON:
        return None

    def hint(kind: PersonalKind, reason: str) -> PersonalHint:
        return PersonalHint(kind=kind, reason=reason)

    if technical == "string" and share(values, EMAIL):
        return hint("email", "Al menos el 80 % de los valores tiene forma de correo electrónico.")
    if found & EMAIL_WORDS and technical == "string":
        return hint("email", "El nombre indica un correo electrónico.")
    if found & DOCUMENT_WORDS and share(values, DOCUMENT):
        return hint(
            "document",
            "El nombre indica un documento de identidad y los valores son "
            "códigos de 6 a 12 dígitos.",
        )
    if found & PHONE_WORDS and share(values, PHONE):
        return hint(
            "phone",
            "El nombre indica un teléfono y los valores tienen forma de número de teléfono.",
        )
    free_text = role in {"text", "unknown"}
    if found & ADDRESS_WORDS and technical == "string" and free_text:
        return hint("address", "El nombre indica una dirección postal.")
    if found & NAME_WORDS and technical == "string" and free_text:
        return hint("name", "El nombre indica el nombre o apellido de una persona.")
    return None


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


def personal_state(
    column: ColumnInspection, note: ColumnAnnotation | None
) -> tuple[bool, PersonalStatus | None]:
    """(¿datos personales?, estado): la detección automática vale salvo que el usuario la
    confirme, la descarte o marque una columna que no se detectó."""
    detected = column.personal is not None
    decided = note.personal if note else None
    if decided is None:
        return detected, "automatic" if detected else None
    if decided:
        return True, "confirmed" if detected else "marked"
    return False, "rejected" if detected else None


def dictionary(
    columns: list[ColumnInspection],
    rules: str,
    annotations: dict[str, ColumnAnnotation],
    version: UUID,
) -> list[DictionaryEntry]:
    """Diccionario vigente: la clasificación automática y, encima, la última corrección del
    usuario para la misma columna de la misma fuente (también de versiones anteriores). Desde la
    Fase 23 es también la clasificación de partida de la comprensión."""
    entries = []
    for column in columns:
        note = annotations.get(column.name)
        role = (note.role if note and note.role else None) or column.role
        nature = (note.nature if note and note.nature else None) or column.nature
        personal, personal_status = personal_state(column, note)
        changed = note is not None and (
            (note.role is not None and note.role != column.role)
            or (note.nature is not None and note.nature != column.nature)
            or note.time_format is not None
            or bool(note.notes)
            or bool(note.null_tokens)
            or personal_status in {"rejected", "marked"}
        )
        status = "corrected" if changed else "confirmed" if note and note.confirmed else "automatic"
        if note is None or status == "automatic":
            origin = f"Clasificación automática ({rules}): {column.nature_reason}"
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
                dichotomous=column.dichotomous,
                ordinal_candidate=column.ordinal_candidate if nature != "ordinal" else None,
                personal=personal,
                personal_kind=column.personal.kind if column.personal else None,
                personal_status=personal_status,
                null_tokens=list(note.null_tokens) if note else [],
            )
        )
    return entries


@dataclass(frozen=True)
class Classified:
    """Clasificación vigente de una columna para las etapas siguientes (Fase 23)."""

    name: str
    role: Role
    nature: Nature
    personal: bool
    corrected: bool


def classification(entries: list[DictionaryEntry]) -> list[Classified]:
    """Lo que la comprensión toma del Diccionario: rol, naturaleza y datos personales."""
    return [
        Classified(
            name=entry.name,
            role=entry.role,
            nature=entry.nature,
            personal=entry.personal,
            corrected=entry.status == "corrected",
        )
        for entry in entries
    ]


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


def validate_annotation(
    request: AnnotationRequest, column: ColumnInspection, declared: Sequence[str] = ()
) -> None:
    """Combinaciones que no tienen sentido; el resto se acepta tal cual (es metadato).
    `declared`: textos ya declarados como nulos en la columna (en una versión derivada ya no
    aparecen en los datos, pero se pueden volver a enviar)."""
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
    if request.null_tokens:
        found = {variant for token in column.missing.tokens for variant in token.variants}
        found |= set(declared)
        unknown = [token for token in request.null_tokens if token not in found]
        if unknown:
            raise ApplicationError(
                "ANNOTATION_INVALID",
                "Sólo se pueden declarar como nulos los textos de «sin dato» que la inspección "
                f"encontró en la columna (no está: «{unknown[0][:50]}»).",
                422,
            )
