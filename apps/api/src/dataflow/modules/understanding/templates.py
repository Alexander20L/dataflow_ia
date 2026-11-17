"""Detección pura de contextos de negocio (moldes `sales@1`, `inventory@1`, `generic@1`).

Procede del antiguo módulo `templates` (Fase 11D), retirado en la Fase 13 junto con los mapeos
confirmados por una persona. Sólo queda la detección de candidatos que usa la interpretación
automática (`automatic-interpretation-v1`): produce candidatos, nunca confirmaciones. El código es
el mismo para no cambiar los perfiles `understanding.profile@3` ya publicados.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

TemplateId = Literal["sales@1", "inventory@1", "generic@1"]
SemanticRoleName = Literal["dimension", "identifier", "measure", "business_date"]


@dataclass(frozen=True)
class RoleSpec:
    role: str  # nombre del rol en el molde (p. ej. «amount»)
    label: str
    semantic_role: SemanticRoleName
    types: tuple[str, ...]  # tipos destino admitidos
    required: bool
    money: bool = False
    quantity: bool = False
    patterns: tuple[str, ...] = ()
    # Sin coincidencia de nombre, ¿vale el rol sugerido por el perfil? Sólo donde no es ambiguo.
    fallback: bool = False


@dataclass(frozen=True)
class TemplateSpec:
    id: TemplateId
    label: str
    roles: tuple[RoleSpec, ...]


@dataclass(frozen=True)
class TableColumn:
    id: UUID
    name: str
    technical_type: str
    scale: int | None
    suggested_role: str | None = None
    suggested_type: str | None = None


@dataclass(frozen=True)
class CandidateRole:
    role: str
    label: str
    required: bool
    column: str | None
    target_type: str | None
    scale: int | None = None


@dataclass(frozen=True)
class TemplateCandidate:
    template: TemplateId
    label: str
    complete: bool
    roles: list[CandidateRole]
    missing_required: list[str]


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
    ),
    "generic@1": TemplateSpec(id="generic@1", label="Genérico", roles=()),
}
# Inventario antes que Ventas: un inventario también tiene importes y fechas.
ORDER: tuple[TemplateId, ...] = ("inventory@1", "sales@1", "generic@1")


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
            )
        )
    return sorted(result, key=lambda c: (not c.complete, ORDER.index(c.template)))
