"""Fase 19: comprensión del negocio (hipótesis de la IA contrastadas con medidas sobre todas las
filas) y valoración opcional del usuario."""

import io
from decimal import Decimal

import polars as pl
import pytest
from fastapi.testclient import TestClient
from reference_sales import reference_csv
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase16_investigation import reference_analysis
from test_phase17_delivery import investigation, source

from dataflow.bootstrap.services import make_runner
from dataflow.integrations.sources import sqlserver_reader
from dataflow.modules.comprehension.contracts import (
    AIComprehension,
    Association,
    ColumnMeaning,
    Comprehension,
    ComprehensionScope,
    Entity,
)
from dataflow.modules.comprehension.domain import (
    accept_ai,
    ordinal_order,
    relationship_key,
    relationships,
    scales,
    strength,
)
from dataflow.modules.comprehension.measures import associations, dependencies, distinct_values
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.delivery.public import build_report, render_pdf
from dataflow.platform.config import get_settings

# --- Reglas puras ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["11-20", "0-10", "más de 20"], ["0-10", "11-20", "más de 20"]),
        (["Alto", "bajo", "Medio"], ["bajo", "Medio", "Alto"]),
        (["3", "1", "2"], ["1", "2", "3"]),
        (["Norte", "Sur"], None),
    ],
)
def test_ordinal_scales_need_a_demonstrable_order(
    values: list[str], expected: list[str] | None
) -> None:
    found = ordinal_order(values)
    assert (found[0] if found else None) == expected


def test_scales_by_role_and_ai_order_only_with_exactly_the_observed_values() -> None:
    columns = [
        ("Importe", "measure"),
        ("Fecha", "time"),
        ("Talla", "dimension"),
        ("Id", "identifier"),
    ]
    distinct = {"Talla": ["S", "M", "L"]}
    plain = {s.column: s.scale for s in scales(columns, distinct)}
    assert plain == {
        "Importe": "ratio",
        "Fecha": "interval",
        "Talla": "nominal",
        "Id": "identifier",
    }
    ordered = scales(columns, distinct, {"Talla": ["S", "M", "L"]})
    talla = next(s for s in ordered if s.column == "Talla")
    assert (talla.scale, talla.order, talla.order_source) == ("ordinal", ["S", "M", "L"], "ai")
    # Un orden con categorías de más o de menos se rechaza.
    wrong = scales(columns, distinct, {"Talla": ["S", "M", "L", "XL"]})
    assert next(s for s in wrong if s.column == "Talla").scale == "nominal"


def test_ai_texts_with_their_own_figures_and_unknown_columns_are_discarded() -> None:
    reply = AIComprehension(
        domain="Ventas mensuales por región; crecieron un 12 % en 2024.",
        entities=[Entity(name="Cliente", columns=["Customer", "Inventada"])],
        meanings=[
            ColumnMeaning(column="CDG_20", meaning="Código de alumno (nota de CDG_20)."),
            ColumnMeaning(column="Inventada", meaning="No existe."),
        ],
        orders={},
        relationships=[
            ("Revenue", "Region", "asociacion", "Las ventas dependen de la región."),
            ("Revenue", "Inventada", "asociacion", "x"),
        ],
        questions=["¿Qué región vende más?", "¿Por qué bajó un 5 %?"],
    )
    accepted, discarded = accept_ai(reply, ["Customer", "CDG_20", "Revenue", "Region"])
    assert accepted.domain == ""  # tenía cifras propias
    assert accepted.entities == [Entity(name="Cliente", columns=["Customer"])]
    # Los dígitos del nombre de una columna sí se admiten.
    assert [m.column for m in accepted.meanings] == ["CDG_20"]
    assert [r[:2] for r in accepted.relationships] == [("Revenue", "Region")]
    assert accepted.questions == ["¿Qué región vende más?"]
    assert len(discarded) == 4  # la entidad sólo pierde su columna inexistente


def test_strength_thresholds() -> None:
    assert [strength(Decimal(v)) for v in ["0.05", "-0.2", "0.35", "0.9"]] == [
        "negligible",
        "weak",
        "moderate",
        "strong",
    ]


def table(data: dict[str, list[str | None]]) -> bytes:
    buffer = io.BytesIO()
    pl.DataFrame(data, schema={k: pl.String for k in data}).write_parquet(buffer)
    return buffer.getvalue()


def test_measures_on_known_data() -> None:
    n = 40
    content = table(
        {
            "x": [str(i) for i in range(n)],
            "y": [str(2 * i + 1) for i in range(n)],
            "g": ["a" if i < n // 2 else "b" for i in range(n)],
            "h": ["a" if i < n // 2 else "b" for i in range(n)],
            "k": [str(i % 4) for i in range(n)],
            "nombre": [f"N{i % 4}" for i in range(n)],
        }
    )
    found, matrix = associations(content, ["x", "y"], ["g", "h"])
    assert matrix == ["x", "y", "g", "h"]
    values = {(a.columns, a.measure): a.value for a in found}
    assert values[(("x", "y"), "pearson")] == "1.0000"
    assert values[(("x", "y"), "spearman")] == "1.0000"
    assert values[(("g", "h"), "cramers_v")] == "1.0000"
    assert Decimal(values[(("x", "g"), "eta")]) > Decimal("0.8")
    checked = dependencies(content, [("k", "nombre"), ("g", "x")])
    assert checked[("k", "nombre")].value == "1.0000"
    assert checked[("g", "x")].value == "0.0000"
    assert distinct_values(content, ["g"]) == {"g": ["a", "b"]}


def test_relationships_are_judged_and_user_verdicts_reorder_them() -> None:
    strong = Association(
        columns=("x", "y"),
        measure="spearman",
        value="0.9000",
        strength="strong",
        rows=40,
        method="m",
    )
    weak = Association(
        columns=("x", "g"),
        measure="eta",
        value="0.0500",
        strength="negligible",
        rows=40,
        method="m",
    )
    key = relationship_key("association", "x", "g")
    found = relationships(
        [("x", "g", "asociacion", "x depende de g"), ("x", "nota", "asociacion", "")],
        [strong, weak],
        {},
        [("cliente_id", "dbo.Clientes.id")],
        {key: "relevant"},
    )
    by_key = {r.key: r for r in found}
    assert by_key[key].status == "not_supported" and by_key[key].verdict == "relevant"
    assert found[0].key == key  # lo valorado como relevante va primero
    assert by_key[relationship_key("association", "x", "y")].origin == "data"
    assert by_key[relationship_key("association", "nota", "x")].status == "not_testable"
    assert by_key[relationship_key("declared", "cliente_id", "dbo.Clientes.id")].status == (
        "confirmed"
    )


def test_sqlserver_reader_keeps_declared_foreign_keys() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.result: list[tuple[object, ...]] = []

        def execute(self, operation: str) -> None:
            if "sys.partitions" in operation:
                self.result = [("dbo", "Ventas", 3)]
            elif "INFORMATION_SCHEMA.COLUMNS" in operation:
                self.result = [
                    ("dbo", "Ventas", "Id", "int"),
                    ("dbo", "Ventas", "ClienteId", "int"),
                ]
            elif "foreign_key_columns" in operation:
                self.result = [("dbo", "Ventas", "ClienteId", "dbo", "Clientes", "Id")]
            else:
                self.result = [(1, 10), (2, 11), (3, 10)]

        def fetchall(self) -> list[tuple[object, ...]]:
            return self.result

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def close(self) -> None:
            pass

    result = sqlserver_reader.read_database(Connection, 100, 128)
    assert result.tables[0].foreign_keys == [("ClienteId", "dbo.Clientes.Id")]


# --- De extremo a extremo -------------------------------------------------------------------------


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def test_upload_is_understood_with_the_fake_ai_and_feedback_carries_over(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    first = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    base = f"/api/v1/versions/{first['id']}/comprehension"
    runner = make_runner(db, objects)
    assert runner.run_once()  # carga
    assert client.get(base).json()["state"] == "queued"
    run_all(db, objects)
    view = client.get(base).json()
    assert view["state"] == "ready"
    result = view["comprehension"]
    assert result["ai_state"] == "ready" and result["domain"]
    scale = {s["column"]: s["scale"] for s in result["scales"]}
    assert scale["Revenue"] == "ratio" and scale["Year"] == "interval"
    assert scale["Region"] == "nominal"
    assert result["matrix_columns"][:3] == ["Units_Sold", "Price_per_Unit", "Revenue"]
    origins = {r["origin"] for r in result["relationships"]}
    assert {"ai", "data"} <= origins
    assert any("Columna inventada" in text for text in result["discarded"])
    # Cliente con dos nombres: la dependencia no se confirma.
    dependency = next(
        r for r in result["relationships"] if r["columns"] == ["Customer", "Customer_Name"]
    )
    assert dependency["status"] == "not_supported"
    # Valoración opcional.
    chosen = next(r for r in result["relationships"] if r["origin"] == "ai")
    judged = client.post(
        f"{base}/feedback",
        json={"relationship_key": chosen["key"], "verdict": "not_relevant"},
        headers=headers,
    )
    assert judged.status_code == 200, judged.text
    assert judged.json()["feedback"][0]["verdict"] == "not_relevant"
    missing = client.post(
        f"{base}/feedback",
        json={"relationship_key": "association:x|y", "verdict": "relevant"},
        headers=headers,
    )
    assert missing.status_code == 404
    # La siguiente carga del mismo archivo la tiene en cuenta.
    second = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    again = client.get(f"/api/v1/versions/{second['id']}/comprehension").json()["comprehension"]
    carried = next(r for r in again["relationships"] if r["key"] == chosen["key"])
    assert carried["verdict"] == "not_relevant"
    assert again["relationships"][-1]["verdict"] == "not_relevant"
    # Progreso y aislamiento por cuenta.
    stages = client.get(f"/api/v1/versions/{second['id']}/progress").json()["stages"]
    assert [s["id"] for s in stages][1] == "comprehension" and stages[1]["state"] == "done"
    account(client)
    assert client.get(base).status_code == 404


def test_without_ai_the_data_still_speaks(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, reference_csv(), name="ventas_mensuales.csv").json()
    run_all(db, objects)
    result = client.get(f"/api/v1/versions/{version['id']}/comprehension").json()["comprehension"]
    assert result["ai_state"] == "unavailable" and result["domain"] is None
    assert result["associations"] and result["relationships"]
    assert {r["origin"] for r in result["relationships"]} <= {"data", "declared"}


def test_report_includes_the_business_comprehension() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    analysis = reference_analysis()
    result = investigation(analysis)
    comprehension = Comprehension(
        scope=ComprehensionScope(
            execution_id=uuid4(),
            version_id=uuid4(),
            profile_sha256="p" * 64,
            table_sha256="t" * 64,
        ),
        ai_state="ready",
        domain="Ventas mensuales por producto y región.",
        scales=scales([("Revenue", "measure"), ("Region", "dimension")], {"Region": ["N", "S"]}),
        associations=[],
        matrix_columns=["Revenue", "Region"],
        relationships=relationships(
            [("Revenue", "Region", "asociacion", "Depende de la región.")], [], {}, [], {}
        ),
        questions=["¿Qué región vende más?"],
        limitations=[],
    )
    document = build_report(
        source(analysis, result),
        analysis,
        result,
        None,
        datetime(2026, 11, 9, tzinfo=UTC),
        None,
        comprehension,
    )
    section = next(s for s in document.sections if s.id == "comprehension")
    assert section.title == "Entendimiento del negocio"
    assert section.blocks[0].paragraphs[0] == "Ventas mensuales por producto y región."
    assert render_pdf(document).startswith(b"%PDF")
