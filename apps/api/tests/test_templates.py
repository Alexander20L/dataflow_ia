"""Fase 11D: moldes (candidatos), mapeos confirmados y compatibilidad (reglas puras y API)."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_api import Flow

from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.templates.contracts import MappingContent, TableColumn
from dataflow.modules.templates.domain import (
    candidates,
    compatibility,
    semantic_draft,
    validate,
)


def column(name: str, kind: str = "string", **extra: Any) -> TableColumn:
    return TableColumn(
        id=uuid4(), name=name, technical_type=kind, scale=extra.pop("scale", None), **extra
    )


# Columnas de examples/ventas_calidad.csv tal como las ve la importación (texto + sugerencias).
VENTAS = [
    column("id", suggested_role="identifier"),
    column("fecha", suggested_role="business_date", suggested_type="date"),
    column("region", suggested_role="dimension"),
    column("importe", suggested_role="measure", suggested_type="decimal"),
    column("unidades", suggested_role="dimension", suggested_type="integer"),
]
SALES: dict[str, Any] = {
    "template": "sales@1",
    "roles": [
        {"role": "date", "column": "fecha", "target_type": "date"},
        {"role": "amount", "column": "importe", "target_type": "decimal", "scale": 2},
        {"role": "dimension", "column": "region", "target_type": "string"},
    ],
    "currency": "PEN",
    "grain": "venta",
}


def by_template(found: list[Any]) -> dict[str, Any]:
    return {candidate.template: candidate for candidate in found}


def test_sales_csv_is_a_complete_sales_candidate_not_an_inventory() -> None:
    found = candidates(VENTAS)
    assert [c.template for c in found][0] == "sales@1"
    sales = by_template(found)["sales@1"]
    assert sales.complete and sales.missing_required == []
    roles = {r.role: (r.column, r.target_type, r.scale) for r in sales.roles}
    assert roles == {
        "date": ("fecha", "date", None),
        "amount": ("importe", "decimal", 2),
        "dimension": ("region", "string", None),
    }
    inventory = by_template(found)["inventory@1"]
    assert not inventory.complete and set(inventory.missing_required) >= {"product", "quantity"}
    assert by_template(found)["generic@1"].complete


def test_inventory_columns_make_an_inventory_candidate_first() -> None:
    columns = [
        column("sku"),
        column("existencias", "integer"),
        column("fecha_corte", "date"),
        column("costo_unitario", "decimal", scale=2),
        column("almacen"),
    ]
    first = candidates(columns)[0]
    assert first.template == "inventory@1" and first.complete
    roles = {r.role: r.column for r in first.roles}
    assert roles == {
        "product": "sku",
        "quantity": "existencias",
        "cut_date": "fecha_corte",
        "unit_cost": "costo_unitario",
        "location": "almacen",
    }


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"currency": None}, "moneda"),
        ({"grain": "factura"}, "grano"),
        ({"grain": None}, "grano"),
        (
            {"roles": [{"role": "date", "column": "fecha", "target_type": "date"}]},
            "obligatorio",
        ),
        (
            {
                "roles": [
                    *SALES["roles"],
                    {"role": "otro", "column": "id", "target_type": "string"},
                ]
            },
            "no existe",
        ),
        (
            {
                "roles": [
                    {"role": "date", "column": "fecha", "target_type": "date"},
                    {"role": "amount", "column": "fecha", "target_type": "decimal", "scale": 2},
                    {"role": "dimension", "column": "region", "target_type": "string"},
                ]
            },
            "dos roles",
        ),
    ],
)
def test_invalid_mappings_explain_the_problem(change: dict[str, Any], problem: str) -> None:
    problems = validate(MappingContent.model_validate({**SALES, **change}))
    assert any(problem in text for text in problems), problems


def test_compatibility_needs_columns_types_and_scale() -> None:
    mapping = MappingContent.model_validate(SALES)
    text = compatibility(mapping, VENTAS)
    assert text.compatible and {c.column for c in text.casts} == {"fecha", "importe"}
    typed = [
        column("fecha", "date"),
        column("importe", "decimal", scale=2),
        column("region"),
    ]
    assert compatibility(mapping, typed).compatible and compatibility(mapping, typed).casts == []
    scale = compatibility(mapping, [*typed[:1], column("importe", "decimal", scale=3), typed[2]])
    assert not scale.compatible and "escala" in scale.problems[0]
    missing = compatibility(mapping, [typed[0], typed[2]])
    assert not missing.compatible and "importe" in missing.problems[0]
    wrong = compatibility(mapping, [column("fecha", "integer"), *typed[1:]])
    assert not wrong.compatible and "fecha" in wrong.problems[0]


def test_semantic_draft_confirms_only_mapped_columns() -> None:
    typed = [
        column("fecha", "date"),
        column("importe", "decimal", scale=2),
        column("region"),
        column("id"),
    ]
    base = {
        "dataset_description": None,
        "row_grain": {"description": None, "review_state": "pending"},
        "columns": [
            {"column_id": str(c.id), "role": "unknown", "review_state": "pending"} for c in typed
        ],
        "key": {"column_ids": [], "null_policy": "reject", "review_state": "pending"},
    }
    draft = semantic_draft(MappingContent.model_validate(SALES), typed, base)
    cols = {UUID(c["column_id"]): c for c in draft["columns"]}
    assert cols[typed[1].id]["role"] == "measure" and cols[typed[1].id]["currency"] == "PEN"
    assert cols[typed[0].id]["role"] == "business_date"
    assert cols[typed[2].id]["role"] == "dimension"
    assert all(cols[c.id]["review_state"] == "confirmed" for c in typed[:3])
    assert cols[typed[3].id] == base["columns"][3]  # sin tocar
    assert draft["row_grain"] == {"description": "venta", "review_state": "confirmed"}


# --- API (PostgreSQL) ---


@pytest.fixture
def flow(client: TestClient, db: Session, objects: LocalObjects) -> Flow:
    return Flow(client, db, objects)


def test_api_candidates_and_versioned_mappings(flow: Flow) -> None:
    client = flow.client
    found = client.get(f"/api/v1/representations/{flow.table['id']}/template-candidates").json()
    assert found["candidates"][0]["template"] == "sales@1" and found["candidates"][0]["complete"]
    path = f"/api/v1/projects/{flow.project_id}/template-mappings"
    saved = client.post(
        path,
        json={"expected_revision": 0, "content": SALES},
        headers=flow.keyed(),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1 and saved.json()["template"] == "sales@1"
    stale = client.post(
        path,
        json={"expected_revision": 0, "content": {**SALES, "grain": "pedido"}},
        headers=flow.keyed(),
    )
    assert stale.status_code == 409 and stale.json()["code"] == "TEMPLATE_MAPPING_CONFLICT"
    invalid = client.post(
        path,
        json={"expected_revision": 1, "content": {**SALES, "currency": None}},
        headers=flow.keyed(),
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "TEMPLATE_MAPPING_INVALID"
    assert [m["id"] for m in client.get(path).json()["items"]] == [saved.json()["id"]]
    again = client.get(f"/api/v1/representations/{flow.table['id']}/template-candidates").json()
    sales = next(c for c in again["candidates"] if c["template"] == "sales@1")
    assert sales["mapping_revision_id"] == saved.json()["id"] and sales["compatible"] is True
