"""Modelo de datos de tablas relacionadas (Fase 31, ADR-049, regla `relations-v1`).

Puro: sin Polars, sin base de datos y sin red. Recibe las tablas ya leídas (celdas canónicas de
texto) y construye, con reglas fijas, el modelo de datos del conjunto:

1. **Claves**: una columna sin vacíos y sin valores repetidos (al menos dos registros).
2. **Relaciones** (columna de la tabla A → clave de la tabla B), entre todas las tablas:
   - declaradas por la base de datos (clave foránea), o
   - detectadas por el nombre: la misma columna en las dos tablas (p. ej. `codigo_alumno`) o una
     clave genérica de B (`id`, `codigo`…) combinada con el nombre de B (`id_estudiante` →
     `estudiantes.id`). Dos columnas `id` sin más no se relacionan.
   Sólo cuentan si **todos** los valores de la columna de A están en la clave de B (al menos dos
   distintos). Cardinalidad: muchos a uno (N:1) o uno a uno (1:1) si la columna de A tampoco se
   repite. Ante la duda (una columna que coincide con varias tablas) no se usa y se explica.
3. **Tablas de hechos**: las que apuntan a otras y a las que nadie apunta (asistencia, notas).
4. **Vista de cada tabla de hechos**: la tabla de hechos con lo que apunta (muchos a uno, a dos
   pasos como mucho): sus registros no cambian (asistencia + estudiante + carrera).
5. **Vista general** (por entidad): la tabla a la que apuntan más tablas de hechos (estudiantes),
   con lo que ella apunta (su carrera) y, de cada tabla de hechos, métricas por registro de la
   entidad: registros, promedio de cada columna numérica y % de la categoría menos frecuente de
   cada columna de dos valores. Así se analizan juntas todas las tablas (asistencia **y** notas
   por carrera). Las métricas se calculan con decimales exactos y no se redondean.
6. **Versión principal**: la vista general si hay dos tablas de hechos o más; si no, la vista de
   la única tabla de hechos. Cada tabla y cada vista se analiza además como versión propia.
"""

import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

RULE = "relations-v1"
MAX_DEPTH = 2
KEY_NAMES = ("id", "codigo", "cod", "code", "clave", "key", "nro", "numero", "num")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
TOKEN = re.compile(r"[A-Za-z]+|\d+")
HUNDRED = Decimal(100)

Cells = list[list[str | None]]


@dataclass(frozen=True)
class Table:
    label: str
    headers: list[str]
    rows: Cells


@dataclass(frozen=True)
class Declared:
    """Clave foránea declarada: `table.column` → `references_table.references_column`."""

    table: str
    column: str
    references_table: str
    references_column: str


@dataclass
class Relation:
    table: str
    column: str
    references_table: str
    references_column: str
    origin: Literal["declared", "detected"]
    cardinality: Literal["N:1", "1:1"] = "N:1"
    status: Literal["joined", "not_joined"] = "not_joined"
    reason: str = ""
    added_columns: list[str] = field(default_factory=list)
    valid: bool = False


@dataclass
class TableRole:
    label: str
    rows: int
    headers: list[str]
    keys: list[str]
    role: Literal["fact", "entity", "dimension", "separate"]
    reason: str


@dataclass
class View:
    name: str
    kind: Literal["fact", "entity"]
    base: str
    tables: list[str]
    headers: list[str]
    rows: Cells
    description: str


@dataclass
class Result:
    tables: list[TableRole]
    relations: list[Relation]
    views: list[View]
    main: str | None  # nombre de la vista principal

    @property
    def joined(self) -> bool:
        return bool(self.views)


def normalize(name: str) -> str:
    """Nombre comparable: minúsculas, sin tildes y sólo letras y dígitos."""
    plain = unicodedata.normalize("NFKD", name.lower())
    return "".join(c for c in plain if c.isalnum() and not unicodedata.combining(c))


def base_name(label: str) -> str:
    """`estudiantes.csv` o `dbo.Estudiantes` → `estudiantes` / `Estudiantes`."""
    base = label.rsplit("/", 1)[-1]
    for extension in (".csv", ".xlsx"):
        if base.lower().endswith(extension):
            base = base[: -len(extension)]
    return base.rsplit(".", 1)[-1]


def stems(label: str) -> set[str]:
    """Raíces del nombre de una tabla (estudiantes, estudiante…), de tres letras o más."""
    word = normalize(base_name(label))
    found = {word}
    if word.endswith("es"):
        found.add(word[:-2])
    if word.endswith("s"):
        found.add(word[:-1])
    return {s for s in found if len(s) >= 3}


def generic(name: str, roots: set[str]) -> str | None:
    """La clave genérica de `name` si es una clave genérica combinada con una raíz de la tabla
    (`idestudiante`, `estudianteid`, `codigoalumno`); si no, None."""
    for key in KEY_NAMES:
        for root in roots:
            if name in {key + root, root + key}:
                return key
    return None


def affinity(column: str, parent: Table, key: str) -> bool:
    child, target = normalize(column), normalize(key)
    if not child or not target:
        return False
    if child == target:
        # La misma columna en las dos tablas; `id` contra `id` no dice nada.
        return target not in KEY_NAMES
    roots = stems(parent.label)
    reference = generic(child, roots)
    if reference is None:
        return False
    return target in {reference, *(reference + r for r in roots), *(r + reference for r in roots)}


def identifier(name: str) -> bool:
    """Nombre de identificador: alguna de sus palabras es una clave genérica (`id_estudiante`,
    `CodigoCliente`, `nro`)."""
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    plain = unicodedata.normalize("NFKD", words)
    tokens = [
        t.lower() for t in TOKEN.findall("".join(c for c in plain if not unicodedata.combining(c)))
    ]
    return any(t in KEY_NAMES for t in tokens)


def unique(values: list[str | None]) -> bool:
    return len(values) >= 2 and None not in values and len(set(values)) == len(values)


def keys(table: Table) -> list[int]:
    """Columnas sin vacíos ni repetidos (con dos registros o más)."""
    return [i for i in range(len(table.headers)) if unique([row[i] for row in table.rows])]


def containment(child: Table, column: int, parent: Table, key: int) -> str | None:
    """None si todos los valores de la columna están en la clave; si no, el motivo."""
    values = {row[column] for row in child.rows if row[column] is not None}
    if len(values) < 2:
        return f"«{child.headers[column]}» tiene menos de dos valores distintos."
    available = {row[key] for row in parent.rows}
    missing = len(values - available)
    if missing:
        return (
            f"{missing} valor(es) de «{child.headers[column]}» no están en "
            f"«{parent.label}.{parent.headers[key]}»: unirlas dejaría registros sin pareja."
        )
    return None


def candidates(tables: list[Table], declared: list[Declared]) -> list[Relation]:
    by_label = {t.label: t for t in tables}
    found: dict[tuple[str, str, str, str], Relation] = {}
    for item in declared:
        child, parent = by_label.get(item.table), by_label.get(item.references_table)
        if child is None or parent is None or child is parent:
            continue
        if item.column not in child.headers or item.references_column not in parent.headers:
            continue
        found[(item.table, item.column, item.references_table, item.references_column)] = Relation(
            item.table, item.column, item.references_table, item.references_column, "declared"
        )
    for parent in tables:
        for key in keys(parent):
            key_name = parent.headers[key]
            for child in tables:
                if child is parent:
                    continue
                for column in child.headers:
                    ident = (child.label, column, parent.label, key_name)
                    if ident not in found and affinity(column, parent, key_name):
                        found[ident] = Relation(
                            child.label, column, parent.label, key_name, "detected"
                        )
    relations = sorted(
        found.values(),
        key=lambda r: (r.table, r.column, r.references_table, r.references_column),
    )
    for relation in relations:
        child, parent = by_label[relation.table], by_label[relation.references_table]
        key = parent.headers.index(relation.references_column)
        if key not in keys(parent):
            relation.reason = (
                f"«{relation.references_column}» de «{parent.label}» tiene vacíos o valores "
                "repetidos: no identifica un solo registro."
            )
            continue
        index = child.headers.index(relation.column)
        problem = containment(child, index, parent, key)
        if problem:
            relation.reason = problem
            continue
        relation.valid = True
        if unique([row[index] for row in child.rows]):
            relation.cardinality = "1:1"
    # Una columna que coincide con varias tablas es ambigua.
    targets: dict[tuple[str, str], list[Relation]] = {}
    for relation in relations:
        if relation.valid:
            targets.setdefault((relation.table, relation.column), []).append(relation)
    for group in targets.values():
        if len(group) > 1:
            names = ", ".join(sorted({r.references_table for r in group}))
            for relation in group:
                relation.valid = False
                relation.reason = (
                    f"«{relation.column}» coincide con más de una tabla ({names}): no se sabe "
                    "con cuál unirla."
                )
    # Dos tablas 1:1 que se apuntan entre sí: sólo cuenta la de la tabla con más registros.
    for relation in relations:
        if not relation.valid or relation.cardinality != "1:1":
            continue
        back = [
            r
            for r in relations
            if r.valid
            and r.table == relation.references_table
            and r.references_table == relation.table
        ]
        if back:
            keep = sorted([relation, *back], key=lambda r: (-len(by_label[r.table].rows), r.table))
            for other in keep[1:]:
                other.valid = False
                other.reason = "Relación uno a uno en el otro sentido: basta con una."
    return relations


def unique_name(name: str, label: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    roots = sorted(stems(label), key=len, reverse=True)
    base = f"{name} ({roots[0] if roots else label})"
    candidate, counter = base, 2
    while candidate in taken:
        candidate, counter = f"{base} {counter}", counter + 1
    return candidate


def number_text(value: Decimal) -> str:
    """Decimal exacto en texto canónico (sin exponente ni ceros de más)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


@dataclass
class Joined:
    headers: list[str]
    rows: Cells
    tables: list[str]
    positions: dict[str, dict[str, int]]


def join_up(
    start: Table,
    valid: list[Relation],
    by_label: dict[str, Table],
    max_columns: int,
    blocked: set[str],
) -> Joined:
    """`start` con las tablas a las que apunta (muchos a uno, a dos pasos): sus registros no
    cambian. `blocked`: tablas que no se unen (las de hechos). Marca las relaciones usadas."""
    headers = list(start.headers)
    rows = [list(row) for row in start.rows]
    positions: dict[str, dict[str, int]] = {start.label: {h: i for i, h in enumerate(headers)}}
    joined: list[str] = []
    queue: deque[tuple[str, int]] = deque([(start.label, 0)])
    while queue:
        current, depth = queue.popleft()
        per_parent: dict[str, list[Relation]] = {}
        for relation in valid:
            if relation.table == current:
                per_parent.setdefault(relation.references_table, []).append(relation)
        for parent_label in sorted(per_parent):
            group = per_parent[parent_label]
            if len(group) > 1:
                columns = ", ".join(f"«{r.column}»" for r in group)
                for relation in group:
                    relation.reason = relation.reason or (
                        f"Más de una columna de «{current}» apunta a «{parent_label}» "
                        f"({columns}): no se sabe cuál usar."
                    )
                continue
            relation = group[0]
            if parent_label == start.label or parent_label in blocked:
                continue
            if parent_label in positions:
                continue  # ya unida por otro camino
            if depth + 1 > MAX_DEPTH:
                relation.reason = (
                    relation.reason or "Está a más de dos pasos de la tabla de partida."
                )
                continue
            parent = by_label[parent_label]
            key = parent.headers.index(relation.references_column)
            extra = [i for i in range(len(parent.headers)) if i != key]
            if len(headers) + len(extra) > max_columns:
                relation.reason = relation.reason or (
                    f"La vista superaría las {max_columns} columnas."
                )
                continue
            taken = set(headers)
            mapping = {relation.references_column: positions[current][relation.column]}
            added: list[str] = []
            for index in extra:
                name = unique_name(parent.headers[index], parent_label, taken)
                taken.add(name)
                mapping[parent.headers[index]] = len(headers)
                headers.append(name)
                added.append(name)
            lookup = {row[key]: row for row in parent.rows}
            source = positions[current][relation.column]
            for row in rows:
                match = lookup.get(row[source]) if row[source] is not None else None
                row.extend(match[i] if match else None for i in extra)
            positions[parent_label] = mapping
            joined.append(parent_label)
            if relation.status != "joined":
                relation.status = "joined"
                relation.added_columns = added
                relation.reason = (
                    f"Cada registro de «{current}» tiene un solo «{parent_label}» "
                    f"(«{relation.column}» → «{relation.references_column}»)."
                )
            queue.append((parent_label, depth + 1))
    return Joined(headers, rows, [start.label, *joined], positions)


def least_frequent(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts, key=lambda v: (counts[v], v))[0]


def metrics(
    fact: Table, column: str, valid: list[Relation], view_keys: list[str | None]
) -> list[tuple[str, list[str | None]]]:
    """Métricas de una tabla de hechos por cada clave de la entidad (en el orden de
    `view_keys`): registros, promedio de cada columna numérica y % de la categoría menos
    frecuente de cada columna de dos valores. Sin claves ni columnas que apuntan a otras."""
    stem = base_name(fact.label)
    link = fact.headers.index(column)
    groups: dict[str, list[list[str | None]]] = {}
    for row in fact.rows:
        value = row[link]
        if value is not None:
            groups.setdefault(value, []).append(row)
    pointing = {r.column for r in valid if r.table == fact.label}
    own_keys = {fact.headers[i] for i in keys(fact) if identifier(fact.headers[i])}
    found: list[tuple[str, list[str | None]]] = [
        (
            f"registros en {stem}",
            [str(len(groups.get(k or "", []))) if k is not None else None for k in view_keys],
        )
    ]
    for index, name in enumerate(fact.headers):
        if name in pointing or name in own_keys or index == link:
            continue
        values = [v for row in fact.rows if (v := row[index]) is not None]
        if not values or all(DATE.match(v) for v in values):
            continue
        if all(NUMBER.match(v) for v in values):
            column_values: list[str | None] = []
            for k in view_keys:
                cells = [c for r in groups.get(k or "", []) if (c := r[index]) is not None]
                column_values.append(
                    number_text(sum((Decimal(c) for c in cells), Decimal(0)) / len(cells))
                    if cells
                    else None
                )
            found.append((f"promedio de {name} ({stem})", column_values))
        elif len(set(values)) == 2:
            counted = least_frequent(values)
            column_values = []
            for k in view_keys:
                cells = [c for r in groups.get(k or "", []) if (c := r[index]) is not None]
                column_values.append(
                    number_text(
                        Decimal(sum(1 for c in cells if c == counted)) * HUNDRED / len(cells)
                    )
                    if cells
                    else None
                )
            found.append((f"% {name} = {counted} ({stem})", column_values))
    return found


def relate(tables: list[Table], declared: list[Declared], max_columns: int) -> Result:
    """Aplica `relations-v1`. Las etiquetas de las tablas deben ser distintas."""
    relations = candidates(tables, declared)
    by_label = {t.label: t for t in tables}
    valid = [r for r in relations if r.valid]
    incoming = {t.label: {r.table for r in valid if r.references_table == t.label} for t in tables}
    outgoing = {t.label: {r.references_table for r in valid if r.table == t.label} for t in tables}
    facts = [t for t in tables if outgoing[t.label] and not incoming[t.label]]
    if not facts and valid:
        facts = [t for t in tables if outgoing[t.label]][:1]
    fact_labels = {t.label for t in facts}
    views: list[View] = []
    for fact in sorted(facts, key=lambda t: (-len(t.rows), t.label)):
        view = join_up(fact, valid, by_label, max_columns, fact_labels - {fact.label})
        if len(view.tables) < 2:
            continue
        others = ", ".join(view.tables[1:])
        views.append(
            View(
                f"{base_name(fact.label)} (tablas unidas)",
                "fact",
                fact.label,
                view.tables,
                view.headers,
                view.rows,
                f"Cada registro de «{fact.label}» con los datos de {others}; los registros no "
                "cambian.",
            )
        )
    # Vista general: la entidad a la que apuntan más tablas de hechos.
    pointers: dict[str, list[Relation]] = {}
    for relation in valid:
        if relation.table in fact_labels and relation.references_table not in fact_labels:
            pointers.setdefault(relation.references_table, []).append(relation)
    entity_label = (
        sorted(
            pointers,
            key=lambda e: (-len({r.table for r in pointers[e]}), -len(by_label[e].rows), e),
        )[0]
        if pointers
        else None
    )
    entity_view: View | None = None
    if entity_label is not None:
        entity = by_label[entity_label]
        base = join_up(entity, valid, by_label, max_columns, fact_labels)
        key_name = pointers[entity_label][0].references_column
        key_index = base.positions[entity_label][key_name]
        view_keys = [row[key_index] for row in base.rows]
        headers, rows = list(base.headers), [list(r) for r in base.rows]
        sources: list[str] = []
        for relation in sorted(pointers[entity_label], key=lambda r: (r.table, r.column)):
            if sum(1 for r in pointers[entity_label] if r.table == relation.table) > 1:
                relation.reason = relation.reason or (
                    f"Más de una columna de «{relation.table}» apunta a «{entity_label}»."
                )
                continue
            if relation.references_column != key_name:
                continue
            fact = by_label[relation.table]
            added: list[str] = []
            for name, values in metrics(fact, relation.column, valid, view_keys):
                if len(headers) >= max_columns:
                    break
                final = unique_name(name, fact.label, set(headers))
                headers.append(final)
                added.append(final)
                for row, value in zip(rows, values, strict=True):
                    row.append(value)
            if added:
                sources.append(fact.label)
                if relation.status == "joined":
                    # Ya une la vista de hechos: sus columnas añadidas son las de esa vista; las
                    # métricas van a la vista general y se nombran aparte, antes de la frase de
                    # la vista de hechos (la interfaz muestra «Columnas añadidas» al final).
                    relation.reason = (
                        f"En la vista general, cada «{entity_label}» resume sus registros de "
                        f"«{fact.label}» ({', '.join(added)}). {relation.reason}"
                    ).strip()
                else:
                    relation.status = "joined"
                    relation.added_columns = added
                    relation.reason = relation.reason or (
                        f"Cada «{entity_label}» resume sus registros de «{fact.label}»."
                    )
        if sources:
            entity_view = View(
                f"{base_name(entity_label)} (vista general)",
                "entity",
                entity_label,
                [*base.tables, *sources],
                headers,
                rows,
                f"Un registro por cada «{entity_label}», con "
                + (f"los datos de {', '.join(base.tables[1:])} y " if base.tables[1:] else "")
                + f"métricas de {', '.join(sources)} (registros, promedios y porcentajes).",
            )
            views.append(entity_view)
    for relation in relations:
        if relation.status != "joined" and not relation.reason:
            relation.reason = (
                "Apunta a una tabla de hechos: unirla repetiría registros."
                if relation.references_table in fact_labels
                else "No se usó en ninguna vista."
            )
    in_views = {label for v in views for label in v.tables}
    roles: list[TableRole] = []
    for table in tables:
        role: Literal["fact", "entity", "dimension", "separate"]
        if table.label in fact_labels and table.label in in_views:
            role, reason = "fact", "Tabla de hechos: apunta a otras y nadie apunta a ella."
        elif entity_view is not None and table.label == entity_view.base:
            role, reason = "entity", "Entidad principal: a ella apuntan las tablas de hechos."
        elif table.label in in_views:
            role, reason = "dimension", "Describe a otra tabla (se une a las vistas)."
        else:
            related = [
                r for r in relations if table.label in {r.table, r.references_table} and r.reason
            ]
            role = "separate"
            reason = (
                related[0].reason
                if related
                else "No se encontró una clave común con las demás tablas."
            )
        roles.append(
            TableRole(
                table.label,
                len(table.rows),
                list(table.headers),
                [
                    table.headers[i]
                    for i in keys(table)
                    if identifier(table.headers[i])
                    or any(
                        r.valid
                        and r.references_table == table.label
                        and r.references_column == table.headers[i]
                        for r in relations
                    )
                ],
                role,
                reason,
            )
        )
    main: str | None = None
    if entity_view is not None and len([v for v in views if v.kind == "fact"]) >= 2:
        main = entity_view.name
    elif views:
        main = sorted(views, key=lambda v: (v.kind != "fact", -len(v.tables), v.name))[0].name
    return Result(roles, relations, views, main)
