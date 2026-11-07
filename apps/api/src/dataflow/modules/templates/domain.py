"""Reglas puras de los moldes (Fase 11D): detección de candidatos, validación de un mapeo,
compatibilidad con una carga nueva y la interpretación semántica que confirma. Sin SQL."""

import re
import unicodedata
from typing import Any

from dataflow.modules.templates.contracts import (
    CandidateRole,
    CastRequest,
    Compatibility,
    MappingContent,
    RoleSpec,
    TableColumn,
    TemplateCandidate,
    TemplateSpec,
)

TEMPLATES: dict[str, TemplateSpec] = {
    "inventory@1": TemplateSpec(
        id="inventory@1",
        label="Inventario",
        roles=(
            RoleSpec(
                "product",
                "Producto",
                "dimension",
                ("string",),
                True,
                patterns=(r"producto", r"sku", r"articulo", r"item", r"nombre", r"product"),
            ),
            RoleSpec(
                "quantity",
                "Cantidad",
                "measure",
                ("integer", "decimal"),
                True,
                quantity=True,
                patterns=(r"stock", r"existencia", r"cantidad", r"inventario", r"qty", r"quantity"),
            ),
            RoleSpec(
                "cut_date",
                "Fecha de corte",
                "business_date",
                ("date",),
                True,
                patterns=(r"corte", r"fecha", r"date"),
                fallback=True,
            ),
            RoleSpec(
                "unit_cost",
                "Costo unitario",
                "measure",
                ("decimal", "integer"),
                False,
                money=True,
                patterns=(r"costo", r"coste", r"precio", r"cost", r"price"),
            ),
            RoleSpec(
                "location",
                "Ubicación",
                "dimension",
                ("string",),
                False,
                patterns=(r"ubicacion", r"almacen", r"bodega", r"tienda", r"location"),
            ),
        ),
        grains=None,
        grain_required=True,
    ),
    "sales@1": TemplateSpec(
        id="sales@1",
        label="Ventas",
        roles=(
            RoleSpec(
                "date",
                "Fecha de negocio",
                "business_date",
                ("date",),
                True,
                patterns=(r"fecha", r"date", r"dia"),
                fallback=True,
            ),
            RoleSpec(
                "amount",
                "Importe",
                "measure",
                ("decimal", "integer"),
                True,
                money=True,
                patterns=(r"importe", r"monto", r"venta", r"total", r"amount", r"revenue"),
                fallback=True,
            ),
            RoleSpec(
                "dimension",
                "Dimensión",
                "dimension",
                ("string",),
                True,
                patterns=(r"region", r"categoria", r"cliente", r"canal", r"vendedor", r"tienda"),
                fallback=True,
            ),
        ),
        grains=("venta", "pedido", "linea"),
        grain_required=True,
    ),
    "generic@1": TemplateSpec(
        id="generic@1", label="Genérico", roles=(), grains=None, grain_required=False
    ),
}
# Inventario antes que Ventas: un inventario también tiene importes y fechas.
ORDER = ("inventory@1", "sales@1", "generic@1")


def normalized(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def fits(column: TableColumn, spec: RoleSpec) -> bool:
    """El tipo actual (o el sugerido por el perfil, si es texto) admite el rol."""
    if column.technical_type in spec.types:
        return True
    return column.technical_type == "string" and (column.suggested_type or "string") in spec.types


def target(column: TableColumn, spec: RoleSpec) -> tuple[str, int | None]:
    kind = column.technical_type if column.technical_type in spec.types else spec.types[0]
    if column.technical_type == "string" and column.suggested_type in spec.types:
        kind = column.suggested_type
    scale = (
        (column.scale if column.technical_type == "decimal" else 2) if kind == "decimal" else None
    )
    return kind, scale


def pick(spec: RoleSpec, columns: list[TableColumn], used: set[str]) -> TableColumn | None:
    for pattern in spec.patterns:
        for column in columns:
            if column.name in used or not fits(column, spec):
                continue
            if re.search(pattern, normalized(column.name)):
                return column
    if not spec.fallback:
        return None
    for column in columns:  # sin coincidencia de nombre: el rol sugerido por el perfil
        if (
            column.name not in used
            and column.suggested_role == spec.semantic_role
            and fits(column, spec)
        ):
            return column
    return None


def candidates(columns: list[TableColumn]) -> list[TemplateCandidate]:
    """Candidatos por molde (nunca confirmaciones), completos primero y en el orden fijo."""
    result: list[TemplateCandidate] = []
    for template in ORDER:
        spec = TEMPLATES[template]
        used: set[str] = set()
        roles: list[CandidateRole] = []
        for role in spec.roles:
            column = pick(role, columns, used)
            if column is not None:
                used.add(column.name)
                kind, scale = target(column, role)
            roles.append(
                CandidateRole(
                    role=role.role,
                    label=role.label,
                    required=role.required,
                    column=column.name if column else None,
                    target_type=kind if column else None,
                    scale=scale if column else None,
                )
            )
        missing = [r.role for r in roles if r.required and r.column is None]
        result.append(
            TemplateCandidate(
                template=template,
                label=spec.label,
                complete=not missing,
                roles=roles,
                missing_required=missing,
                grains=list(spec.grains) if spec.grains else None,
            )
        )
    return sorted(result, key=lambda c: (not c.complete, ORDER.index(c.template)))


def validate(content: MappingContent) -> list[str]:
    """Problemas de un mapeo frente a su molde (vacío si es válido)."""
    spec = TEMPLATES[content.template]
    roles = {role.role: role for role in spec.roles}
    problems: list[str] = []
    seen_roles = [r.role for r in content.roles]
    columns = [r.column for r in content.roles]
    if len(set(seen_roles)) != len(seen_roles):
        problems.append("Cada rol sólo puede asignarse una vez.")
    if len(set(columns)) != len(columns):
        problems.append("Una columna no puede cumplir dos roles.")
    for item in content.roles:
        role_spec = roles.get(item.role)
        if role_spec is None:
            problems.append(f"El rol «{item.role}» no existe en el molde {spec.label}.")
        elif item.target_type not in role_spec.types:
            problems.append(f"«{role_spec.label}» admite {', '.join(role_spec.types)}.")
    for role_spec in spec.roles:
        if role_spec.required and role_spec.role not in seen_roles:
            problems.append(f"Falta el rol obligatorio «{role_spec.label}».")
    used = {r.role for r in content.roles}
    if any(roles[r].money for r in used if r in roles) and not content.currency:
        problems.append("Indica la moneda de los importes.")
    if any(roles[r].quantity for r in used if r in roles) and not content.unit:
        problems.append("Indica la unidad de la cantidad.")
    if spec.grain_required and not content.grain:
        problems.append("Indica el grano: qué representa cada fila.")
    if spec.grains and content.grain and content.grain not in spec.grains:
        problems.append(f"El grano debe ser uno de: {', '.join(spec.grains)}.")
    return problems


def compatibility(content: MappingContent, columns: list[TableColumn]) -> Compatibility:
    """Contrato de compatibilidad: columnas requeridas presentes por nombre, tipos compatibles
    (texto convertible con la conversión confirmada, o el mismo tipo y escala), unidades y moneda
    definidas y grano conservado. Nombre o esquema iguales no bastan por sí solos."""
    by_name = {column.name: column for column in columns}
    problems = validate(content)
    casts: list[CastRequest] = []
    for item in content.roles:
        column = by_name.get(item.column)
        if column is None:
            problems.append(f"Falta la columna «{item.column}» ({item.role}).")
            continue
        if column.technical_type == item.target_type:
            if item.target_type == "decimal" and column.scale != item.scale:
                problems.append(f"«{item.column}» tiene otra escala decimal ({column.scale}).")
            continue
        if column.technical_type == "string" and item.target_type != "string":
            casts.append(CastRequest(item.column, item.target_type, item.scale))
            continue
        problems.append(
            f"«{item.column}» es {column.technical_type}; el mapeo espera {item.target_type}."
        )
    return Compatibility(compatible=not problems, problems=problems, casts=casts)


def semantic_draft(
    content: MappingContent, columns: list[TableColumn], base: dict[str, Any]
) -> dict[str, Any]:
    """Borrador semántico que confirma los roles del mapeo sobre la tabla (ya convertida),
    partiendo del borrador vigente: no toca las columnas que el mapeo no nombra."""
    spec = TEMPLATES[content.template]
    roles = {role.role: role for role in spec.roles}
    ids = {column.name: str(column.id) for column in columns}
    mapped = {ids[item.column]: item for item in content.roles if item.column in ids}
    draft = dict(base)
    updated: list[dict[str, Any]] = []
    for column in base["columns"]:
        item = mapped.get(str(column["column_id"]))
        if item is None:
            updated.append(column)
            continue
        role_spec = roles[item.role]
        updated.append(
            {
                **column,
                "role": role_spec.semantic_role,
                "interpretation_type": item.target_type,
                "currency": content.currency if role_spec.money else None,
                "unit": content.unit if role_spec.quantity else None,
                "review_state": "confirmed",
            }
        )
    draft["columns"] = updated
    if content.grain:
        draft["row_grain"] = {"description": content.grain, "review_state": "confirmed"}
    return draft
