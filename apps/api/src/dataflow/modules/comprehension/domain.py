"""Comprensión del negocio (Fase 19, ADR-036): reglas puras, sin Polars, SQL ni IA.

- `measurement-scale-v1`: escala de medida de cada columna a partir de la interpretación
  analítica (roles de `profile@4`) y de los valores distintos. Una escala ordinal necesita un
  orden demostrable: rangos numéricos, un vocabulario ordenado conocido, enteros con pocas
  categorías o un orden propuesto por la IA que contenga exactamente los valores observados.
- Las relaciones de la IA sólo se aceptan sobre columnas que existen y se contrastan con la
  medida calculada; los textos de la IA con cifras que no son nombres de columna se retiran.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from dataflow.modules.comprehension.contracts import (
    AIComprehension,
    Association,
    ColumnMeaning,
    ColumnScale,
    Entity,
    Relationship,
    Strength,
    Verdict,
)

THRESHOLDS: list[tuple[Decimal, Strength]] = [
    (Decimal("0.5"), "strong"),
    (Decimal("0.3"), "moderate"),
    (Decimal("0.1"), "weak"),
]
STRENGTH_LABELS: dict[str, str] = {
    "strong": "fuerte",
    "moderate": "moderada",
    "weak": "débil",
    "negligible": "despreciable",
}
MEASURE_LABELS: dict[str, str] = {
    "pearson": "correlación de Pearson",
    "spearman": "correlación de Spearman",
    "cramers_v": "V de Cramér",
    "eta": "razón de correlación (eta)",
    "dependency": "dependencia funcional",
}
CONFIRMED_FROM = Decimal("0.3")  # moderada o fuerte
DEPENDENCY_SHARE = Decimal("0.98")
DATA_RELATIONSHIPS = 8  # asociaciones fuertes que se proponen sin IA

ORDERED_VOCABULARIES: list[list[str]] = [
    ["muy bajo", "bajo", "medio", "alto", "muy alto"],
    ["muy malo", "malo", "regular", "bueno", "muy bueno", "excelente"],
    ["deficiente", "insuficiente", "suficiente", "notable", "sobresaliente"],
    ["nunca", "casi nunca", "a veces", "casi siempre", "siempre"],
    ["muy en desacuerdo", "en desacuerdo", "neutral", "de acuerdo", "muy de acuerdo"],
    ["very low", "low", "medium", "high", "very high"],
    ["poor", "fair", "good", "very good", "excellent"],
    ["primaria", "secundaria", "tecnica", "universitaria", "posgrado"],
    ["pequeno", "mediano", "grande"],
    ["small", "medium", "large"],
]
RANGE = re.compile(
    r"^\s*(?:de\s+)?(-?\d+(?:[.,]\d+)?)\s*(?:-|–|a|al|hasta|to)\s*(-?\d+(?:[.,]\d+)?)\s*\S*\s*$",
    re.IGNORECASE,
)
OPEN_RANGE = re.compile(
    r"^\s*(?:<|>|<=|>=|menos de|mas de|más de|hasta|desde|under|over)"
    r"\s*(-?\d+(?:[.,]\d+)?)\s*\S*\s*$",
    re.IGNORECASE,
)
INTEGER = re.compile(r"^-?\d+$")
DIGIT = re.compile(r"\d")


def plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.strip().casefold())
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def strength(value: Decimal) -> Strength:
    magnitude = abs(value)
    return next((label for bound, label in THRESHOLDS if magnitude >= bound), "negligible")


def relationship_key(kind: str, a: str, b: str) -> str:
    first, second = sorted([a, b])
    return f"{kind}:{first}|{second}"


# --- Escalas de medida ------------------------------------------------------------------------


def range_bound(value: str) -> Decimal | None:
    for pattern in (RANGE, OPEN_RANGE):
        match = pattern.match(value)
        if match:
            bound = Decimal(match.group(1).replace(",", "."))
            lowered = plain(value)
            # «menos de 10» va antes de «10 a 20»; «más de 50» después.
            if lowered.startswith(("<", "menos de", "hasta", "under")):
                return bound - Decimal("0.0001")
            return bound
    return None


def ordinal_order(values: Sequence[str]) -> tuple[list[str], str] | None:
    """Orden demostrable de las categorías o None."""
    if len(values) < 2:
        return None
    bounds = [range_bound(v) for v in values]
    known = [b for b in bounds if b is not None]
    if len(known) == len(values):
        ordered = [v for _, v in sorted(zip(known, values, strict=True), key=lambda p: p[0])]
        return ordered, "Rangos numéricos: se ordenan por su límite inferior."
    normalized = {plain(v): v for v in values}
    for vocabulary in ORDERED_VOCABULARIES:
        if set(normalized) <= set(vocabulary):
            return (
                [normalized[word] for word in vocabulary if word in normalized],
                "Categorías de un vocabulario ordenado conocido.",
            )
    if all(INTEGER.match(v) for v in values) and len(values) <= 10:
        return (
            sorted(values, key=int),
            "Pocos enteros distintos: escala ordenada (por ejemplo, una valoración).",
        )
    return None


def scales(
    columns: Sequence[tuple[str, str]],
    distinct: Mapping[str, list[str]],
    ai_orders: Mapping[str, list[str]] | None = None,
) -> list[ColumnScale]:
    """`columns`: (nombre, rol de la interpretación analítica). `distinct`: valores distintos de
    las dimensiones (todos, si son pocos)."""
    result: list[ColumnScale] = []
    for name, role in columns:
        if role == "measure":
            result.append(
                ColumnScale(
                    column=name,
                    scale="ratio",
                    reason="Medida numérica con cero significativo: admite sumas y cocientes.",
                )
            )
        elif role == "time":
            result.append(
                ColumnScale(
                    column=name,
                    scale="interval",
                    reason="Tiempo: se ordena y se restan intervalos, pero no se suma.",
                )
            )
        elif role in {"identifier", "text", "empty"}:
            reasons = {
                "identifier": "Identifica registros: no se agrega ni se ordena.",
                "text": "Texto libre: no se agrupa ni se ordena.",
                "empty": "Sin valores.",
            }
            result.append(ColumnScale(column=name, scale=role, reason=reasons[role]))
        else:
            values = distinct.get(name, [])
            order = ordinal_order(values)
            suggested = (ai_orders or {}).get(name)
            if order is not None:
                result.append(
                    ColumnScale(
                        column=name,
                        scale="ordinal",
                        order=order[0],
                        reason=order[1],
                        order_source="rules",
                    )
                )
            elif suggested and values and sorted(suggested) == sorted(values):
                result.append(
                    ColumnScale(
                        column=name,
                        scale="ordinal",
                        order=list(suggested),
                        reason="La IA propuso un orden que contiene exactamente los valores "
                        "observados.",
                        order_source="ai",
                    )
                )
            else:
                result.append(
                    ColumnScale(
                        column=name,
                        scale="nominal",
                        reason="Categorías sin orden demostrable: se cuentan y comparan.",
                    )
                )
    return result


# --- Textos de la IA ----------------------------------------------------------------------------


def clean_text(text: str, columns: Iterable[str], limit: int = 300) -> str | None:
    """El texto sin cifras propias: las únicas cifras admitidas son las de nombres de columna."""
    stripped = text.strip()[:limit]
    if not stripped:
        return None
    remainder = stripped
    for name in sorted(columns, key=len, reverse=True):
        if name:
            remainder = remainder.replace(name, " ")
    return None if DIGIT.search(remainder) else stripped


def accept_ai(reply: AIComprehension, columns: Sequence[str]) -> tuple[AIComprehension, list[str]]:
    """Filtra la respuesta: columnas inexistentes y textos con cifras se retiran (con motivo)."""
    known = set(columns)
    discarded: list[str] = []

    def text(value: str, what: str, limit: int = 300) -> str | None:
        cleaned = clean_text(value, columns, limit)
        if cleaned is None and value.strip():
            discarded.append(f"{what}: contenía cifras que no salen de los datos.")
        return cleaned

    domain = text(reply.domain, "Descripción del dataset", 400) or ""
    entities = []
    for entity in reply.entities[:10]:
        members = [c for c in entity.columns if c in known]
        name = text(entity.name, "Entidad", 80)
        if name and members:
            entities.append(Entity(name=name, columns=members))
    meanings = []
    for meaning in reply.meanings:
        if meaning.column not in known:
            discarded.append(f"Significado de «{meaning.column[:60]}»: la columna no existe.")
            continue
        described = text(meaning.meaning, f"Significado de «{meaning.column}»", 200)
        if described:
            meanings.append(
                ColumnMeaning(column=meaning.column, meaning=described, entity=meaning.entity)
            )
    relationships = []
    for a, b, kind, hypothesis in reply.relationships[:15]:
        if a not in known or b not in known or a == b:
            discarded.append(f"Relación {a[:40]} – {b[:40]}: columnas inexistentes o repetidas.")
            continue
        relationships.append((a, b, kind, text(hypothesis, f"Relación {a} – {b}") or ""))
    questions = [q for q in (text(q, "Pregunta", 200) for q in reply.questions[:8]) if q]
    orders = {k: v for k, v in reply.orders.items() if k in known}
    return (
        AIComprehension(
            domain=domain,
            entities=entities,
            meanings=meanings,
            orders=orders,
            relationships=relationships,
            questions=questions,
        ),
        discarded,
    )


# --- Relaciones ---------------------------------------------------------------------------------


def find(associations: Sequence[Association], a: str, b: str) -> Association | None:
    pair = {a, b}
    candidates = [x for x in associations if set(x.columns) == pair]
    # Entre números se prefiere Spearman (robusta); si no, la que haya.
    return next((x for x in candidates if x.measure == "spearman"), None) or next(
        iter(candidates), None
    )


def describe(item: Association) -> str:
    label = MEASURE_LABELS[item.measure]
    return (
        f"{label[:1].upper()}{label[1:]} {item.value.replace('.', ',')} "
        f"({STRENGTH_LABELS[item.strength]}) sobre {item.rows} filas."
    )


def judged(
    key: str,
    a: str,
    b: str,
    kind: str,
    origin: str,
    hypothesis: str | None,
    associations: Sequence[Association],
    dependencies: Mapping[tuple[str, str], Association],
    verdicts: Mapping[str, Verdict],
) -> Relationship:
    if kind == "dependency":
        evidence = dependencies.get((a, b)) or dependencies.get((b, a))
        if evidence is None:
            status, detail = "not_testable", "No se pudo comprobar la dependencia."
        else:
            holds = Decimal(evidence.value) >= DEPENDENCY_SHARE
            status = "confirmed" if holds else "not_supported"
            detail = (
                f"Cada valor de {evidence.columns[0]} tiene un único {evidence.columns[1]} en "
                f"el {format(Decimal(evidence.value) * 100, '.2f').replace('.', ',')} % de los "
                f"casos ({evidence.rows} valores)."
            )
    else:
        evidence = find(associations, a, b)
        if evidence is None:
            status = "not_testable"
            detail = (
                "No hay una medida de asociación para este par (identificadores, texto libre o "
                "pocas filas con ambos valores)."
            )
        else:
            supported = abs(Decimal(evidence.value)) >= CONFIRMED_FROM
            status = "confirmed" if supported else "not_supported"
            detail = describe(evidence)
    return Relationship(
        key=key,
        columns=(a, b),
        kind="dependency" if kind == "dependency" else "association",
        origin=origin,
        hypothesis=hypothesis,
        status=status,
        evidence=evidence,
        detail=detail,
        verdict=verdicts.get(key),
    )


def relationships(
    ai: Sequence[tuple[str, str, str, str]],
    associations: Sequence[Association],
    dependencies: Mapping[tuple[str, str], Association],
    declared: Sequence[tuple[str, str]],
    verdicts: Mapping[str, Verdict],
    data_dependencies: Sequence[tuple[str, str]] = (),
) -> list[Relationship]:
    """Relaciones de la IA, de los datos (asociaciones fuertes) y declaradas en la base.

    Orden: las valoradas como relevantes, luego confirmadas, luego el resto; las marcadas como
    «No relevante» se conservan al final (no se ocultan sin dejar rastro)."""
    result: list[Relationship] = []
    seen: set[str] = set()
    for a, b, kind, hypothesis in ai:
        normalized = (
            "dependency" if kind in {"dependencia", "jerarquia", "dependency"} else ("association")
        )
        key = relationship_key(normalized, a, b)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            judged(
                key,
                a,
                b,
                normalized,
                "ai",
                hypothesis or None,
                associations,
                dependencies,
                verdicts,
            )
        )
    for a, b in data_dependencies:
        key = relationship_key("dependency", a, b)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            judged(key, a, b, "dependency", "data", None, associations, dependencies, verdicts)
        )
    strong = sorted(
        (x for x in associations if x.strength == "strong" and x.measure != "pearson"),
        key=lambda x: (-abs(Decimal(x.value)), x.columns),
    )
    for item in strong[:DATA_RELATIONSHIPS]:
        a, b = item.columns
        key = relationship_key("association", a, b)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            judged(key, a, b, "association", "data", None, associations, dependencies, verdicts)
        )
    for column, reference in declared:
        key = relationship_key("declared", column, reference)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            Relationship(
                key=key,
                columns=(column, reference),
                kind="declared",
                origin="declared",
                status="confirmed",
                detail=f"Clave foránea declarada en la base: {column} → {reference}.",
                verdict=verdicts.get(key),
            )
        )
    rank = {"relevant": 0, None: 1, "not_relevant": 2}
    status_rank = {"confirmed": 0, "not_testable": 1, "not_supported": 2}
    return sorted(result, key=lambda r: (rank[r.verdict], status_rank[r.status]))
