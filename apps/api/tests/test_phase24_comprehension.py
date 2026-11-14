"""Fase 24: pestaña Comprensión (ADR-041, `business-comprehension-v3`).

- Reglas puras: grano, nombres de código, estado de las relaciones, fuentes de una fórmula,
  medidas, confianza y significados del usuario.
- Cifras conocidas: `promedio` es exactamente 0,3·parcial + 0,4·final + 0,3·prácticas,
  `aprobado` es `promedio ≥ 10,5` y `tutor_id` ↔ `tutor` nombran la misma entidad.
- Las fórmulas no se proponen como hallazgos; validar o rechazar una relación rehace la
  exploración; los significados del usuario se heredan y no cambian ningún cálculo.
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.comprehension.contracts import (
    AIComprehension,
    Association,
    ColumnMeaning,
    Formula,
    Relationship,
    UserMeaning,
)
from dataflow.modules.comprehension.domain import (
    UNKNOWN_MEANING,
    accept_ai,
    classify,
    closure,
    grain,
    measure_infos,
    opaque,
    with_user_meanings,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.platform.config import get_settings

# --- Reglas puras -------------------------------------------------------------------------------


def test_grain_names_the_entity_of_the_unique_key() -> None:
    student = grain([(["estudiante_id"], True)])
    assert student.entity == "estudiante" and student.key == ["estudiante_id"]
    assert student.sentence == "Cada fila es un registro de estudiante, único por «estudiante_id»."
    assert grain([(["CustomerID"], True)]).entity == "customer"
    pair = grain([(["fecha", "tienda"], True)])
    assert pair.entity is None and "combinación única" in pair.sentence
    none = grain([(["region"], False)])
    assert not none.unique and none.key == [] and "Ninguna columna" in none.sentence


def test_code_names_formula_sources_and_relation_states() -> None:
    assert opaque("ESTREG") and opaque("CDG_20") and opaque("X1")
    assert not opaque("nota_final") and not opaque("Customer_Name") and not opaque("estado")
    formulas = [
        Formula(
            column="promedio",
            kind="weighted_sum",
            sources=["parcial", "final"],
            weights=["0.5", "0.5"],
            expression="",
            rows=10,
            matching_rows=10,
            tolerance="0.005",
            method="",
        ),
        Formula(
            column="aprobado",
            kind="threshold",
            sources=["promedio"],
            expression="",
            rows=10,
            matching_rows=10,
            tolerance="0",
            method="",
        ),
    ]
    # Una columna calculada a partir de otra calculada hereda sus fuentes.
    assert closure(formulas) == {
        "promedio": {"parcial", "final"},
        "aprobado": {"promedio", "parcial", "final"},
    }

    def relation(strength: str, status: str = "confirmed", **extra: Any) -> Relationship:
        evidence = Association(
            columns=("a", "b"),
            measure="spearman",
            value="0.5",
            strength=strength,  # type: ignore[arg-type]
            rows=10,
            method="",
        )
        return Relationship(
            key="association:a|b",
            columns=("a", "b"),
            kind="association",
            origin="data",
            status=status,  # type: ignore[arg-type]
            evidence=evidence,
            detail="",
            **extra,
        )

    assert classify(relation("strong")).state == "pending"
    assert classify(relation("moderate")).state == "ambiguous"
    assert classify(relation("strong", "not_supported")).state == "ambiguous"
    assert classify(relation("weak", verdict="relevant")).state == "validated"
    assert classify(relation("strong", verdict="not_relevant")).state == "rejected"
    assert classify(relation("strong")).family == "statistical"


def test_measures_are_never_summed_unless_proven_additive() -> None:
    infos = {
        m.column: m
        for m in measure_infos(
            [
                ("ventas", "measure", "additive", "S/", True),
                ("precio", "measure", "non_additive", "S/", True),
                ("nota", "measure", "unknown", None, False),
                ("region", "dimension", None, None, False),
            ],
            {"nota"},
        )
    }
    assert set(infos) == {"ventas", "precio", "nota"}
    assert (infos["ventas"].aggregation, infos["precio"].aggregation) == ("sum", "mean")
    assert infos["nota"].aggregation == "mean" and infos["nota"].derived
    assert "no comprobada" in infos["nota"].reason


def test_ai_confidence_is_capped_for_code_names_and_unknown_is_admitted() -> None:
    reply = AIComprehension(
        domain="Registro académico",
        entities=[],
        meanings=[
            ColumnMeaning(column="ESTREG", meaning="Estado del registro", confidence="high"),
            ColumnMeaning(column="nota_final", meaning="Nota del examen final", confidence="high"),
            ColumnMeaning(column="CDG_20", meaning="", confidence="medium"),
        ],
        orders={},
        relationships=[],
        questions=[],
    )
    accepted, _ = accept_ai(reply, ["ESTREG", "nota_final", "CDG_20"])
    found = {m.column: m for m in accepted.meanings}
    assert found["ESTREG"].confidence == "low" and found["nota_final"].confidence == "high"
    assert found["CDG_20"].meaning == UNKNOWN_MEANING and found["CDG_20"].confidence == "low"
    mixed = with_user_meanings(
        accepted.meanings,
        {
            "ESTREG": UserMeaning("Estado de matrícula", False),
            "nota_final": UserMeaning(None, True),
        },
    )
    by = {m.column: m for m in mixed}
    assert by["ESTREG"].source == "user" and by["ESTREG"].meaning == "Estado de matrícula"
    assert by["nota_final"].source == "ai" and by["nota_final"].confirmed
    assert [m.column for m in mixed] == ["ESTREG", "nota_final", "CDG_20"]


# --- Cifras conocidas -----------------------------------------------------------------------------


def students() -> bytes:
    """30 estudiantes: `promedio` = 0,3·parcial + 0,4·final + 0,3·prácticas (exacto a dos
    decimales), `aprobado` = «Sí» desde 10,5 y dos tutores que se repiten con su nombre."""
    lines = [
        "estudiante_id,carrera,tutor_id,tutor,horas,nota_parcial,nota_final,nota_practicas,"
        "promedio,aprobado"
    ]
    careers = ["Derecho", "Medicina", "Arquitectura"]
    tutors = [("T1", "Ríos"), ("T2", "Paz"), ("T3", "Soto")]
    for i in range(1, 31):
        p = Decimal(6 + (i * 7) % 10) + Decimal(i % 3) / 10
        f = Decimal(5 + (i * 3) % 12) + Decimal(i % 5) / 10
        pr = Decimal(7 + (i * 5) % 9) + Decimal(i % 4) / 10
        avg = (Decimal("0.3") * p + Decimal("0.4") * f + Decimal("0.3") * pr).quantize(
            Decimal("0.01")
        )
        hours = 3 + (i * 7) % 11
        tutor_id, tutor = tutors[i % 3]
        lines.append(
            f"E{i:03d},{careers[(i * 2) % 3]},{tutor_id},{tutor},{hours},{p},{f},{pr},{avg},"
            f"{'Sí' if avg >= Decimal('10.5') else 'No'}"
        )
    return ("\n".join(lines) + "\n").encode()


def run_all(db: Session, objects: LocalObjects) -> None:
    runner = make_runner(db, objects)
    while runner.run_once():
        pass


def get(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def runs(db: Session, version: str, kind: str) -> list[ExecutionRecord]:
    return list(
        db.scalars(
            select(ExecutionRecord)
            .where(ExecutionRecord.version_id == version, ExecutionRecord.kind == kind)
            .order_by(ExecutionRecord.created_at)
        )
    )


def test_grain_formulas_entities_and_measures_on_known_data(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, students(), name="notas.csv").json()["id"]
    run_all(db, objects)
    found = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert found["rules_version"] == "business-comprehension-v4"
    assert found["grain"]["entity"] == "estudiante"
    assert found["grain"]["key"] == ["estudiante_id"]
    formulas = {f["column"]: f for f in found["formulas"]}
    average = formulas["promedio"]
    assert average["kind"] == "weighted_sum"
    assert dict(zip(average["sources"], average["weights"], strict=True)) == {
        "nota_parcial": "0.3",
        "nota_final": "0.4",
        "nota_practicas": "0.3",
    }
    assert average["matching_rows"] == average["rows"] == 30
    passed = formulas["aprobado"]
    assert (passed["kind"], passed["sources"], passed["category"]) == (
        "threshold",
        ["promedio"],
        "Sí",
    )
    assert Decimal(passed["threshold"]) >= Decimal("10.5")
    relations = {r["key"]: r for r in found["relationships"]}
    derived = [r for r in relations.values() if r["kind"] == "derived"]
    assert {frozenset(r["columns"]) for r in derived} == {
        frozenset(("promedio", "nota_parcial")),
        frozenset(("promedio", "nota_final")),
        frozenset(("promedio", "nota_practicas")),
        frozenset(("aprobado", "promedio")),
    }
    assert all(r["family"] == "structural" for r in derived)
    # Una fórmula no es un hallazgo: no hay asociaciones entre una calculada y sus fuentes.
    sources = {"promedio": {"nota_parcial", "nota_final", "nota_practicas"}}
    sources["aprobado"] = sources["promedio"] | {"promedio"}
    for r in relations.values():
        if r["kind"] == "association":
            a, b = r["columns"]
            assert b not in sources.get(a, set()) and a not in sources.get(b, set()), r
    entity = relations["same_entity:tutor|tutor_id"]
    assert entity["family"] == "structural" and entity["state"] == "pending"
    measures = {m["column"]: m for m in found["measures"]}
    assert measures["promedio"]["derived"] and measures["promedio"]["aggregation"] == "mean"
    dimensions = {d["column"]: d for d in found["dimensions"]}
    assert dimensions["aprobado"]["groupable"] and dimensions["carrera"]["distinct"] == 3
    # La exploración no propone ninguna fórmula como consulta.
    explored = get(client, f"/api/v1/versions/{version}/exploration")["exploration"]
    for proposal in explored["proposals"]:
        query = proposal["query"]
        used = {query.get("measure"), query.get("measure_b"), *query.get("dimensions", [])}
        for target, inputs in sources.items():
            assert not (target in used and used & inputs), proposal


def test_validations_redo_the_exploration_and_meanings_are_inherited(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = students()
    version = upload(client, headers, pid, content, name="notas.csv").json()["id"]
    run_all(db, objects)
    view = get(client, f"/api/v1/versions/{version}/comprehension")
    statistical = next(
        r
        for r in view["comprehension"]["relationships"]
        if r["kind"] == "association" and r["status"] == "confirmed"
    )
    # Rechazar una relación cuenta ya: se rehacen la exploración y el dashboard.
    judged = client.post(
        f"/api/v1/versions/{version}/comprehension/feedback",
        json={"relationship_key": statistical["key"], "verdict": "not_relevant"},
        headers=headers,
    )
    assert judged.status_code == 200, judged.text
    assert judged.json()["recalculating"]
    state = {r["key"]: r["state"] for r in judged.json()["comprehension"]["relationships"]}
    assert state[statistical["key"]] == "rejected"
    run_all(db, objects)
    assert len(runs(db, version, "exploration")) == 2
    assert len(runs(db, version, "dashboard")) == 2
    pair = set(statistical["columns"])
    latest = get(client, f"/api/v1/versions/{version}/exploration")["exploration"]
    for proposal in latest["proposals"]:
        if proposal["origin"] != "rule":
            continue
        query = proposal["query"]
        used = {query.get("measure"), query.get("measure_b"), *query.get("dimensions", [])}
        assert not pair <= used, proposal
    assert not get(client, f"/api/v1/versions/{version}/comprehension")["recalculating"]

    # Significados del usuario: no cambian ningún cálculo y los heredan las versiones siguientes.
    path = f"/api/v1/versions/{version}/comprehension/meanings"
    assert client.post(path, json={"column": "otra"}, headers=headers).status_code == 404
    empty = client.post(path, json={"column": "horas", "meaning": "  "}, headers=headers)
    assert empty.status_code == 422
    described = client.post(
        path, json={"column": "horas", "meaning": "Horas de estudio por semana"}, headers=headers
    )
    assert described.status_code == 200, described.text
    meaning = {m["column"]: m for m in described.json()["comprehension"]["meanings"]}["horas"]
    assert (meaning["source"], meaning["confidence"]) == ("user", "high")
    explorations = len(runs(db, version, "exploration"))
    assert len(runs(db, version, "exploration")) == explorations  # nada se recalcula
    second = upload(client, headers, pid, content, name="notas.csv").json()["id"]
    run_all(db, objects)
    inherited = get(client, f"/api/v1/versions/{second}/comprehension")["comprehension"]
    assert {m["column"]: m for m in inherited["meanings"]}["horas"]["source"] == "user"
    # La relación rechazada también llega rechazada a la versión siguiente.
    states = {r["key"]: r["state"] for r in inherited["relationships"]}
    assert states.get(statistical["key"]) == "rejected"
    # Volver al de la IA: sin texto y sin confirmar.
    client.post(path, json={"column": "horas"}, headers=headers)
    back = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert all(m["source"] == "ai" for m in back["meanings"] if m["column"] == "horas")


def test_with_the_fake_ai_meanings_carry_a_confidence(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, students(), name="notas.csv").json()["id"]
    run_all(db, objects)
    found = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert found["ai_state"] == "ready", found["ai_reason"]
    assert found["meanings"] and all(m["confidence"] for m in found["meanings"])
    assert found["formulas"]  # las reglas siguen mandando con o sin IA
