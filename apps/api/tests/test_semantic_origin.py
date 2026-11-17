"""Fase 7A · A5: una derivada puede partir de la revisión semántica de su origen."""

from uuid import uuid4

import pytest
from analytics_support import typed_table
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_analytics_runner import confirm_semantics
from test_cleaning_runner import Scenario

from dataflow.modules.datasets.objects import LocalObjects


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def test_derived_version_offers_origin_decisions_without_confirming_them(
    scenario: Scenario,
) -> None:
    s, c = scenario, scenario.columns
    origin = confirm_semantics(
        s, s.table, importe=("measure", "EUR"), fecha=("business_date", None)
    )
    original = s.client.get(f"/api/v1/representations/{s.table['id']}/understanding").json()
    assert original["origin"] is None  # una importación no tiene origen

    typed = typed_table(s)
    context = s.client.get(f"/api/v1/representations/{typed['id']}/understanding").json()
    # Nada confirmado en v2 por heredar: la familia de v2 no tiene revisiones.
    assert context["head"] is None and context["revision_count"] == 0
    assert context["origin"]["version_number"] == 1
    assert context["origin"]["revision"] == origin
    columns = {col["column_id"]: col for col in context["origin"]["draft"]["columns"]}
    assert (columns[c["importe"]]["role"], columns[c["importe"]]["currency"]) == ("measure", "EUR")
    assert columns[c["importe"]]["review_state"] == "confirmed"
    assert columns[c["fecha"]]["role"] == "business_date"
    assert [col["column_id"] for col in context["origin"]["draft"]["columns"]] == [
        col["column_id"] for col in context["editable"]["columns"]
    ]

    # Guardar el borrador de origen es una acción explícita que crea la revisión 1 de v2.
    saved = s.client.post(
        f"/api/v1/representations/{typed['id']}/semantic-contracts",
        json={
            "table_sha256": typed["sha256"],
            "expected_revision": 0,
            "draft": context["origin"]["draft"],
        },
        headers={**s.headers, "Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text
    revision = saved.json()["revision"]
    assert revision["revision"] == 1
    assert revision["content"]["table_ref"]["artifact_id"] == typed["id"]
    by_id = {col["id"]: col for col in revision["content"]["columns"]}
    assert by_id[c["importe"]]["technical_type"] == "decimal"  # hechos de la tabla de v2
    assert by_id[c["importe"]]["role"] == "measure"
