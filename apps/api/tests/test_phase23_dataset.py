"""Fase 23: cierre de la pestaña Dataset (ADR-040).

- `dataset-inspection-v2`: dominio evidente de los valores, atípicos (vallas de Tukey), filas
  repetidas sin los identificadores, columnas dicotómicas, escalas ordinales candidatas y datos
  personales, con cifras conocidas.
- Las correcciones del Diccionario cuentan: recalculan la comprensión (y, tras ella, exploración,
  dashboard e informe), las columnas personales no llegan a la IA y los textos declarados como
  nulos crean una versión derivada que se analiza entera. El original nunca cambia.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.comprehension_job import ai_columns
from dataflow.bootstrap.services import make_runner
from dataflow.modules.comprehension.domain import classified_roles, scales
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.modules.inspection.domain import (
    domain_kind,
    ordinal_hint,
    personal_hint,
    words,
)
from dataflow.modules.understanding.contracts import DatasetProfile

# --- Reglas puras -------------------------------------------------------------------------------


def test_names_ranges_scales_and_personal_data_rules() -> None:
    assert words("Asistencia_Pct") == ["asistencia", "pct"]
    assert words("horasEstudioSem") == ["horas", "estudio", "sem"]
    assert words("Dirección") == ["direccion"]
    assert domain_kind("asistencia_pct")[0] == "percent"  # type: ignore[index]
    assert domain_kind("% avance")[0] == "percent"  # type: ignore[index]
    assert domain_kind("edad")[0] == "non_negative"  # type: ignore[index]
    # Un importe puede ser negativo (devoluciones): no se le exige rango.
    assert domain_kind("importe") is None and domain_kind("nota_final") is None
    ten = [str(n) for n in range(1, 11)]
    hint = ordinal_hint("ciclo", "integer", "measure", ten)
    assert hint is not None and hint.order == ten
    likert = ordinal_hint("p1", "integer", "measure", ["1", "2", "3", "4", "5"])
    assert likert is not None and "valoración" in likert.reason
    # Una cantidad con pocos valores no es una escala; un identificador o un texto, tampoco.
    assert ordinal_hint("unidades", "integer", "measure", ["2", "5", "9"]) is None
    assert ordinal_hint("nivel", "integer", "identifier", ["1", "2", "3"]) is None
    assert ordinal_hint("nivel", "string", "dimension", ["a", "b", "c"]) is None
    assert ordinal_hint("ciclo", "integer", "measure", [str(n) for n in range(1, 30)]) is None
    name = personal_hint("nombre", "string", ["Ana Ríos", "Luis Paz"])
    assert name is not None and name.kind == "name"
    assert personal_hint("nombre_producto", "string", ["Laptop"]) is None
    assert personal_hint("product_name", "string", ["Laptop"]) is None
    mail = personal_hint("contacto", "string", ["a@x.com", "b@y.org"])
    assert mail is not None and mail.kind == "email"
    assert personal_hint("dni", "string", ["12345678", "87654321"]) is not None
    # Un código con nombre de documento pero sin forma de documento no se marca.
    assert personal_hint("documento", "string", ["Factura", "Boleta"]) is None
    assert personal_hint("telefono", "string", ["+51 987 654 321", "01-555-1234"]) is not None
    assert personal_hint("ciudad", "string", ["Lima"]) is None
    # Un nombre que agrupa registros (clientes en ventas) es una dimensión, no texto personal.
    assert personal_hint("Customer_Name", "string", ["Acme"], "dimension") is None
    assert personal_hint("Customer_Email", "string", ["a@x.com"], "dimension") is not None


def test_corrections_set_roles_and_scales_for_the_comprehension() -> None:
    analysis = [("id", "identifier"), ("nombre", "text"), ("ciclo", "measure"), ("nota", "measure")]
    items = [
        ("id", "identifier", "nominal", False, False),
        ("nombre", "text", "unknown", True, False),
        ("ciclo", "dimension", "ordinal", False, True),
        ("nota", "measure", "continuous", False, False),
    ]
    roles, declared, corrected, personal = classified_roles(analysis, items)
    assert roles == [
        ("id", "identifier"),
        ("nombre", "text"),
        ("ciclo", "dimension"),
        ("nota", "measure"),
    ]
    assert declared == {"ciclo": "ordinal"} and corrected == ["ciclo"] and personal == ["nombre"]
    values = {"ciclo": ["10", "2", "1"]}
    [ciclo] = [s for s in scales(roles, values, None, declared) if s.column == "ciclo"]
    assert ciclo.scale == "ordinal" and ciclo.order == ["1", "2", "10"]
    assert ciclo.order_source == "user"
    # Sin corrección, mismas escalas que antes de la Fase 23 (sin regresiones).
    assert scales(analysis, {}) == scales(analysis, {}, None, {})
    # Una dimensión que el usuario dice nominal no se ordena aunque las reglas sepan hacerlo.
    [level] = scales(
        [("nivel", "dimension")], {"nivel": ["bajo", "alto"]}, None, {"nivel": "nominal"}
    )
    assert level.scale == "nominal" and level.order == []


def test_personal_columns_never_reach_the_ai_context() -> None:
    profile = DatasetProfile.model_validate(
        {
            "engine_version": "test",
            "polars_version": "test",
            "source_sha256": "0" * 64,
            "separator": ",",
            "row_count": 2,
            "column_count": 2,
            "columns": [
                {
                    "name": "nombre",
                    "suggested_type": "string",
                    "null_count": 0,
                    "unique_count": 2,
                    "examples": ["Ana Ríos", "Luis Paz"],
                },
                {
                    "name": "nota",
                    "suggested_type": "decimal",
                    "null_count": 0,
                    "unique_count": 2,
                    "examples": ["12", "15"],
                },
            ],
        }
    )
    sent = ai_columns(profile, {}, {"nombre": "text", "nota": "measure"}, {"nombre"})
    assert [c.name for c in sent] == ["nota"]
    assert "Ana" not in str([c.model_dump() for c in sent])


# --- Cifras conocidas -----------------------------------------------------------------------------


def students() -> bytes:
    """40 estudiantes: un porcentaje fuera de 0–100, horas negativas, un atípico, textos de «sin
    dato» en dos escrituras y una fila igual a la primera salvo el identificador."""
    careers = ["Derecho", "Medicina", "Arquitectura"]
    lines = ["estudiante_id,nombre,carrera,ciclo,asistencia_pct,horas_estudio,nota,estado,aprobado"]
    for i in range(1, 40):
        attendance = "130" if i == 7 else str(70 + i % 25)
        hours = "-3" if i == 11 else str(5 + i % 15)
        grade = "2" if i == 13 else f"{10 + (i % 8) + (i % 3) / 2:.1f}"
        state = (
            "N/A" if i in {4, 9, 21} else "n/a" if i == 30 else "Activo" if i % 2 else "Inactivo"
        )
        lines.append(
            f"S{i:03d},Persona {i} Apellido{i},{careers[i % 3]},{1 + i % 10},{attendance},"
            f"{hours},{grade},{state},{'Sí' if i % 3 else 'No'}"
        )
    first = lines[1].split(",")
    lines.append(",".join(["S040", *first[1:]]))
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


def test_inspection_v2_finds_ranges_outliers_repeats_scales_and_personal_data(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = students()
    version = upload(client, headers, pid, content, name="estudiantes.csv").json()["id"]
    run_all(db, objects)
    view = get(client, f"/api/v1/versions/{version}/inspection")
    inspection = view["inspection"]
    assert inspection["scope"]["rules"] == "dataset-inspection-v2"
    found = {c["name"]: c for c in inspection["columns"]}
    findings = {(f["kind"], tuple(f["columns"])): f for f in inspection["findings"]}
    # Porcentaje fuera de 0–100 (fila 7) y horas negativas (fila 11): avisos de validez.
    attendance = found["asistencia_pct"]["domain"]
    assert (attendance["kind"], attendance["outside"]) == ("percent", 1)
    out = findings[("out_of_range", ("asistencia_pct",))]
    assert out["dimension"] == "validity" and out["sample_rows"] == [7]
    assert out["examples"] == ["130"]
    assert found["horas_estudio"]["domain"]["outside"] == 1
    assert findings[("out_of_range", ("horas_estudio",))]["sample_rows"] == [11]
    # El 2 de «nota» es atípico; se avisa y no se elimina.
    nota = found["nota"]["numeric"]["outliers"]
    assert nota["count"] >= 1 and float(nota["mild_lower"]) > 2
    atypical = findings[("outliers", ("nota",))]
    assert atypical["severity"] == "info" and 13 in atypical["sample_rows"]
    assert "2" in atypical["examples"]
    # La fila 40 repite la 1 salvo el identificador: no es un duplicado exacto, pero se avisa.
    summary = inspection["summary"]
    assert summary["duplicate_rows"] == 0 and summary["duplicate_rows_without_ids"] == 1
    assert "estudiante_id" in summary["identifier_columns"]
    repeated = findings[("duplicate_rows_without_ids", tuple(summary["identifier_columns"]))]
    assert repeated["sample_rows"] == [40]
    # Dicotómica, escala candidata y datos personales.
    assert found["aprobado"]["dichotomous"] and not found["carrera"]["dichotomous"]
    assert found["ciclo"]["ordinal_candidate"]["order"] == [str(n) for n in range(1, 11)]
    assert found["nombre"]["personal"]["kind"] == "name"
    assert summary["personal_columns"] == ["nombre"]
    # «N/A» y «n/a» son el mismo texto de «sin dato», con sus dos escrituras exactas.
    [token] = found["estado"]["missing"]["tokens"]
    assert (token["token"], token["count"], token["variants"]) == ("n/a", 4, ["N/A", "n/a"])
    entry = {e["name"]: e for e in view["dictionary"]}
    assert entry["nombre"]["personal"] and entry["nombre"]["personal_status"] == "automatic"
    assert entry["ciclo"]["ordinal_candidate"] is not None
    # Nada cambia el original.
    assert client.get(f"/api/v1/versions/{version}/original").content == content


def test_corrections_recalculate_the_analysis_and_declared_nulls_create_a_derived_version(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = students()
    version = upload(client, headers, pid, content, name="estudiantes.csv").json()["id"]
    run_all(db, objects)
    view = get(client, f"/api/v1/versions/{version}/inspection")
    ids = {c["name"]: c["id"] for c in view["inspection"]["columns"]}
    first = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert first["rules_version"] == "business-comprehension-v2"
    assert first["personal_columns"] == ["nombre"] and first["corrected_columns"] == []
    scale = {s["column"]: s for s in first["scales"]}
    assert scale["ciclo"]["scale"] == "ratio" and scale["nombre"]["scale"] == "text"
    assert view["recalculation"] is None
    path = f"/api/v1/versions/{version}/dictionary"

    # 1. «ciclo» es una escala ordinal: la comprensión se recalcula con esa clasificación.
    saved = client.post(
        path,
        json={"column_id": ids["ciclo"], "role": "dimension", "nature": "ordinal"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    pending = saved.json()["recalculation"]
    assert pending["kind"] == "comprehension" and pending["state"] == "queued"
    # Guardar lo mismo otra vez no encola nada nuevo.
    client.post(
        path,
        json={"column_id": ids["ciclo"], "role": "dimension", "nature": "ordinal"},
        headers=headers,
    )
    assert len(runs(db, version, "comprehension")) == 2
    run_all(db, objects)
    second = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    scale = {s["column"]: s for s in second["scales"]}
    assert scale["ciclo"]["scale"] == "ordinal" and scale["ciclo"]["order_source"] == "user"
    assert scale["ciclo"]["order"] == [str(n) for n in range(1, 11)]
    assert second["corrected_columns"] == ["ciclo"]
    # Tras la comprensión se rehacen la exploración y el dashboard; lo anterior se conserva.
    assert len(runs(db, version, "exploration")) == 2
    assert len(runs(db, version, "dashboard")) == 2
    explored = get(client, f"/api/v1/versions/{version}/exploration")
    assert explored["state"] == "ready"
    assert get(client, f"/api/v1/versions/{version}/inspection")["recalculation"]["state"] == (
        "succeeded"
    )

    # 2. «nombre» no es un dato personal (decisión del usuario): deja de estar excluida.
    client.post(path, json={"column_id": ids["nombre"], "personal": False}, headers=headers)
    run_all(db, objects)
    third = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert third["personal_columns"] == []
    entry = {
        e["name"]: e for e in get(client, f"/api/v1/versions/{version}/inspection")["dictionary"]
    }
    assert entry["nombre"]["personal"] is False and entry["nombre"]["personal_status"] == "rejected"

    # 3. Sólo se declaran textos que la inspección encontró en la columna.
    bad = client.post(
        path, json={"column_id": ids["estado"], "null_tokens": ["Inactivo"]}, headers=headers
    )
    assert bad.status_code == 422 and bad.json()["code"] == "ANNOTATION_INVALID"
    declared = client.post(
        path, json={"column_id": ids["estado"], "null_tokens": ["N/A", "n/a"]}, headers=headers
    )
    assert declared.status_code == 200, declared.text
    cleaning = declared.json()["recalculation"]
    assert cleaning["kind"] == "null_cleaning" and cleaning["state"] == "queued"
    run_all(db, objects)
    done = get(client, f"/api/v1/versions/{version}/inspection")["recalculation"]
    assert done["state"] == "succeeded" and done["derived_version_id"]
    derived = done["derived_version_id"]
    # La versión derivada tiene los textos como nulos y se analizó entera.
    child = get(client, f"/api/v1/versions/{derived}/inspection")
    assert child["state"] == "ready", child
    estado = {c["name"]: c for c in child["inspection"]["columns"]}["estado"]
    assert estado["nulls"] == 4 and estado["missing"]["tokens"] == []
    inherited = {e["name"]: e for e in child["dictionary"]}
    assert inherited["ciclo"]["status"] == "corrected" and inherited["ciclo"]["inherited"]
    assert inherited["estado"]["null_tokens"] == ["N/A", "n/a"]
    understood = get(client, f"/api/v1/versions/{derived}/comprehension")["comprehension"]
    # Descartar el aviso de datos personales también es una corrección (heredada).
    assert understood["corrected_columns"] == ["nombre", "ciclo"]
    for kind in ("comprehension", "investigation", "exploration", "dashboard"):
        assert [r.state for r in runs(db, derived, kind)] == ["succeeded"], kind
    # Re-enviar los textos ya aplicados en la derivada se acepta y no crea otra versión.
    again = client.post(
        f"/api/v1/versions/{derived}/dictionary",
        json={"column_id": ids["estado"], "null_tokens": ["N/A", "n/a"], "notes": "Estado"},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert runs(db, derived, "null_cleaning") == []
    # El original y su versión no cambian.
    assert client.get(f"/api/v1/versions/{version}/original").content == content
    original = {c["name"]: c for c in view["inspection"]["columns"]}["estado"]
    assert original["nulls"] == 0
