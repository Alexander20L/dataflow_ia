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
    DimensionInfo,
    Entity,
    Formula,
    Grain,
    MeasureInfo,
    Period,
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


def classified_roles(
    analysis: Sequence[tuple[str, str]],
    items: Sequence[tuple[str, str, str, bool, bool]],
) -> tuple[list[tuple[str, str]], dict[str, str], list[str], list[str]]:
    """Fase 23: roles de partida con la clasificación del Diccionario.

    `analysis`: (nombre, rol de la interpretación analítica). `items`: (nombre, rol, naturaleza,
    ¿datos personales?, ¿corregida por el usuario?) de la pestaña Dataset. Una columna sin
    corregir conserva su rol analítico (mismas reglas, sin regresiones); una con datos personales
    pasa a texto; una corregida toma el rol que indicó el usuario. Devuelve los roles, la escala
    declarada («ordinal» o «nominal») de las columnas corregidas, las corregidas y las personales.
    """
    by_name = {item[0]: item for item in items}
    roles: list[tuple[str, str]] = []
    declared: dict[str, str] = {}
    corrected: list[str] = []
    personal: list[str] = []
    for name, role in analysis:
        item = by_name.get(name)
        if item is None:
            roles.append((name, role))
            continue
        _, user_role, nature, is_personal, is_corrected = item
        if is_personal:
            personal.append(name)
            roles.append((name, "text"))
            continue
        if not is_corrected:
            roles.append((name, role))
            continue
        corrected.append(name)
        if user_role == "identifier":
            roles.append((name, "identifier"))
        elif user_role == "time" or nature == "temporal":
            roles.append((name, "time"))
        elif nature in {"ordinal", "nominal"} and user_role in {"dimension", "category", "measure"}:
            roles.append((name, "dimension"))
            declared[name] = nature
        elif user_role == "measure":
            roles.append((name, "measure"))
        elif user_role in {"dimension", "category"}:
            roles.append((name, "dimension"))
        elif user_role == "text":
            roles.append((name, "text"))
        else:
            roles.append((name, role))
    return roles, declared, corrected, personal


def numeric_order(values: Sequence[str]) -> list[str] | None:
    try:
        return sorted(values, key=lambda v: Decimal(v.strip()))
    except ArithmeticError:
        return None


def scales(
    columns: Sequence[tuple[str, str]],
    distinct: Mapping[str, list[str]],
    ai_orders: Mapping[str, list[str]] | None = None,
    declared: Mapping[str, str] | None = None,
) -> list[ColumnScale]:
    """`columns`: (nombre, rol de la interpretación analítica). `distinct`: valores distintos de
    las dimensiones (todos, si son pocos). `declared` (Fase 23): escala que el usuario indicó en
    el Diccionario para una dimensión («ordinal» o «nominal»); manda sobre las reglas."""
    result: list[ColumnScale] = []
    for name, role in columns:
        user = (declared or {}).get(name)
        if role == "dimension" and user == "nominal":
            result.append(
                ColumnScale(
                    column=name,
                    scale="nominal",
                    reason="Indicada como cualitativa nominal en el Diccionario: categorías sin "
                    "orden.",
                )
            )
            continue
        if role == "dimension" and user == "ordinal":
            values = distinct.get(name, [])
            found = ordinal_order(values)
            ranked = found[0] if found else numeric_order(values)
            result.append(
                ColumnScale(
                    column=name,
                    scale="ordinal",
                    order=ranked or [],
                    reason="Indicada como cualitativa ordinal en el Diccionario"
                    + (
                        "; sus categorías se ordenan por su valor."
                        if ranked
                        else "; el orden de sus categorías no se conoce, así que se comparan "
                        "sin ordenarlas."
                    ),
                    order_source="user",
                )
            )
            continue
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
        if not meaning.meaning.strip():
            # Fase 24: la IA dice que no lo sabe; se pide confirmación en vez de inventarlo.
            meanings.append(
                ColumnMeaning(
                    column=meaning.column,
                    meaning=UNKNOWN_MEANING,
                    entity=meaning.entity,
                    confidence="low",
                )
            )
            continue
        described = text(meaning.meaning, f"Significado de «{meaning.column}»", 200)
        if described:
            meanings.append(
                confident(
                    ColumnMeaning(
                        column=meaning.column,
                        meaning=described,
                        entity=meaning.entity,
                        confidence=meaning.confidence,
                    )
                )
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
    structural_items: Sequence[Relationship] = (),
    derived_pairs: set[frozenset[str]] | None = None,
) -> list[Relationship]:
    """Relaciones de la IA, de los datos (asociaciones fuertes) y declaradas en la base.

    Orden: las valoradas como relevantes, luego confirmadas, luego el resto; las marcadas como
    «No relevante» se conservan al final (no se ocultan sin dejar rastro). Fase 24: van además
    las estructurales y temporales (`structural_items`), y una asociación entre una columna
    calculada y sus fuentes (`derived_pairs`) no se propone: es una fórmula, no un hallazgo."""
    result: list[Relationship] = list(structural_items)
    seen: set[str] = {r.key for r in structural_items}
    formula_pairs = derived_pairs or set()
    for a, b, kind, hypothesis in ai:
        normalized = (
            "dependency" if kind in {"dependencia", "jerarquia", "dependency"} else ("association")
        )
        key = relationship_key(normalized, a, b)
        if key in seen or (normalized == "association" and frozenset((a, b)) in formula_pairs):
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
    strong = [x for x in strong if frozenset(x.columns) not in formula_pairs]
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
    ordered = sorted(result, key=lambda r: (rank[r.verdict], status_rank[r.status]))
    return [classify(r) for r in ordered]


# --- Fase 24: grano, medidas, dimensiones, periodo y estado de las relaciones ---------------------

ID_WORDS = frozenset(
    {"id", "codigo", "cod", "code", "num", "nro", "numero", "key", "clave", "pk", "uuid"}
)
UNKNOWN_MEANING = "No se puede saber por el nombre ni por el perfil: confírmalo o escríbelo."
FAMILY: dict[str, str] = {
    "association": "statistical",
    "dependency": "structural",
    "declared": "structural",
    "derived": "structural",
    "same_entity": "structural",
    "period": "temporal",
}
AGGREGATION_REASONS: dict[str, tuple[str, str]] = {
    "additive": ("sum", "Sumable: el total tiene sentido."),
    "semi_additive": ("sum", "Sumable dentro de un periodo; entre periodos se compara."),
    "non_additive": ("mean", "No sumable (tasa, precio o promedio): se promedia."),
    "unknown": ("mean", "Sumabilidad no comprobada: sólo el promedio simple."),
}


def words(name: str) -> list[str]:
    """Palabras de un nombre de columna, sin tildes ni mayúsculas (snake, kebab y CamelCase)."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return [w for w in re.split(r"[^a-z0-9]+", plain(spaced)) if w]


def opaque(name: str) -> bool:
    """Un nombre de código («ESTREG», «CDG_20», «X1»): ninguna palabra de 4 o más letras con
    vocal, o todo en mayúsculas y corto. Su significado nunca pasa de confianza baja."""
    letters = re.sub(r"[^A-Za-z]", "", name)
    if letters and letters.isupper() and len(name) <= 10:
        return True
    return not any(len(w) >= 4 and re.search(r"[aeiou]", w) for w in words(name))


def grain(keys: Sequence[tuple[list[str], bool]]) -> Grain:
    """Qué representa una fila: la primera clave única (de la interpretación analítica) y la
    entidad que nombra su identificador («estudiante_id» → estudiante)."""
    unique = next((columns for columns, is_unique in keys if is_unique), None)
    if unique is None:
        return Grain(
            sentence="Ninguna columna identifica cada fila: cada fila es un registro sin clave "
            "propia.",
            key=[],
            entity=None,
            unique=False,
            reason="Ninguna columna ni combinación candidata es única en todas las filas.",
        )
    quoted = " y ".join(f"«{c}»" for c in unique)
    if len(unique) == 1:
        named = [w for w in words(unique[0]) if w not in ID_WORDS]
        entity = " ".join(named) or None
    else:
        entity = None
    sentence = (
        f"Cada fila es un registro de {entity}, único por {quoted}."
        if entity
        else f"Cada fila es una combinación única de {quoted}."
        if len(unique) > 1
        else f"Cada fila es un registro único por {quoted}."
    )
    return Grain(
        sentence=sentence,
        key=list(unique),
        entity=entity,
        unique=True,
        reason=f"{quoted} no se repite en ninguna fila."
        + (" La entidad sale del nombre del identificador." if entity else ""),
    )


def measure_infos(
    columns: Sequence[tuple[str, str, str | None, str | None, bool]], derived: set[str]
) -> list[MeasureInfo]:
    """`columns`: (nombre, rol, sumabilidad, unidad, ¿moneda?) de la interpretación analítica,
    sólo las medidas vigentes. La agregación sale de la sumabilidad; nunca se suma lo que no se
    demostró sumable."""
    result = []
    for name, role, additivity, unit, monetary in columns:
        if role != "measure":
            continue
        kind = additivity if additivity in AGGREGATION_REASONS else "unknown"
        aggregation, reason = AGGREGATION_REASONS[kind]
        if name in derived:
            reason += " Es una columna calculada a partir de otras."
        result.append(
            MeasureInfo(
                column=name,
                additivity=kind,
                aggregation=aggregation,
                unit=unit,
                monetary=monetary,
                derived=name in derived,
                reason=reason,
            )
        )
    return result


def dimension_infos(
    dimensions: Sequence[str], distinct: Mapping[str, int], derived: set[str]
) -> list[DimensionInfo]:
    result = []
    for name in dimensions:
        count = distinct.get(name, 0)
        groupable = 2 <= count <= 50
        reason = (
            f"{count} categorías: sirve para agrupar."
            if groupable
            else "Un solo valor: no separa grupos."
            if count < 2
            else f"{count} categorías: demasiadas para agrupar en un gráfico."
        )
        if name in derived:
            reason += " Se calcula con un umbral de otra columna."
        result.append(
            DimensionInfo(column=name, distinct=count, groupable=groupable, reason=reason)
        )
    return result


def period_of(
    kind: str | None,
    columns: Sequence[str],
    first: str | None,
    last: str | None,
    periods: int,
    missing: int,
) -> Period | None:
    if kind not in {"date", "year_month"}:
        return None
    note = (
        f"{' y '.join(columns)} forman un periodo mensual (no se creó ninguna fecha)."
        if kind == "year_month"
        else f"{columns[0]} es una fecha; se agrupa por mes."
    )
    if missing:
        note += f" Faltan {missing} meses entre el primero y el último."
    return Period(
        kind=kind,
        columns=list(columns),
        first=first,
        last=last,
        periods=periods,
        missing=missing,
        note=note,
    )


def closure(formulas: Sequence[Formula]) -> dict[str, set[str]]:
    """Fuentes de cada columna calculada, también las de sus fuentes calculadas."""
    direct = {f.column: set(f.sources) for f in formulas}
    result: dict[str, set[str]] = {}
    for column in direct:
        seen: set[str] = set()
        pending = list(direct[column])
        while pending:
            source = pending.pop()
            if source in seen or source == column:
                continue
            seen.add(source)
            pending.extend(direct.get(source, set()))
        result[column] = seen
    return result


def structural(
    formulas: Sequence[Formula],
    same_entities: Sequence[tuple[str, str, int]],
    period: Period | None,
    verdicts: Mapping[str, Verdict],
) -> list[Relationship]:
    """Relaciones estructurales y temporales comprobadas fila a fila: cada columna calculada con
    cada una de sus fuentes, las columnas que nombran la misma entidad y el periodo."""
    result = []
    for formula in formulas:
        for source in formula.sources:
            key = relationship_key("derived", formula.column, source)
            result.append(
                Relationship(
                    key=key,
                    columns=(formula.column, source),
                    kind="derived",
                    origin="data",
                    status="confirmed",
                    detail=f"{formula.expression} (se cumple en las {formula.matching_rows} "
                    "filas). Es una fórmula, no un hallazgo.",
                    verdict=verdicts.get(key),
                )
            )
    for a, b, distinct in same_entities:
        key = relationship_key("same_entity", a, b)
        result.append(
            Relationship(
                key=key,
                columns=(a, b),
                kind="same_entity",
                origin="data",
                status="confirmed",
                detail=f"Cada uno de los {distinct} valores de {a} va siempre con el mismo {b} y "
                "al revés: nombran la misma entidad.",
                verdict=verdicts.get(key),
            )
        )
    if period is not None and len(period.columns) == 2:
        a, b = period.columns
        key = relationship_key("period", a, b)
        result.append(
            Relationship(
                key=key,
                columns=(a, b),
                kind="period",
                origin="data",
                status="confirmed",
                detail=period.note,
                verdict=verdicts.get(key),
            )
        )
    return result


def classify(relation: Relationship) -> Relationship:
    """Familia y estado: la valoración del usuario manda; sin ella, «pendiente» si los datos la
    respaldan con fuerza (o es estructural) y «ambigua» si no la respaldan del todo."""
    family = FAMILY[relation.kind]
    if relation.verdict == "relevant":
        state = "validated"
    elif relation.verdict == "not_relevant":
        state = "rejected"
    elif relation.status != "confirmed":
        state = "ambiguous"
    elif family == "statistical" and relation.evidence is not None:
        state = "pending" if relation.evidence.strength == "strong" else "ambiguous"
    else:
        state = "pending"
    return relation.model_copy(update={"family": family, "state": state})


def confident(meaning: ColumnMeaning) -> ColumnMeaning:
    """La confianza de la IA, limitada por las reglas: un nombre de código nunca pasa de baja."""
    if opaque(meaning.column) and meaning.confidence != "low":
        return meaning.model_copy(update={"confidence": "low"})
    return meaning


def with_user_meanings(
    meanings: Sequence[ColumnMeaning], user: Mapping[str, tuple[str | None, bool]]
) -> list[ColumnMeaning]:
    """Significados vigentes: el del usuario (escrito o confirmado) sobre el de la IA."""
    by_column = {m.column: m for m in meanings}
    for column, (text, confirmed) in user.items():
        current = by_column.get(column)
        if text:
            by_column[column] = ColumnMeaning(
                column=column,
                meaning=text,
                entity=current.entity if current else None,
                confidence="high",
                source="user",
                confirmed=True,
            )
        elif confirmed and current is not None:
            by_column[column] = current.model_copy(update={"confirmed": True, "confidence": "high"})
    order = [m.column for m in meanings] + [
        c for c in by_column if c not in {m.column for m in meanings}
    ]
    return [by_column[c] for c in order]
