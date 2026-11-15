"""Fase 30: nombres de negocio para una interfaz que se entiende sin leer (ADR-048).

- La IA (prompt de comprensión v5) propone un tema corto, un nombre para el objetivo y un nombre
  corto por columna; Python los valida (sin cifras, pocas palabras, columnas existentes).
- `business-comprehension-v6`: el objetivo de tipo tasa dice qué categoría cuenta, con la misma
  regla que la investigación (la menos frecuente; en empate, la primera alfabéticamente).
"""

import io

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload
from test_phase28_criteria import get, run_all
from test_phase29_target import roster

from dataflow.modules.comprehension.contracts import AIComprehension
from dataflow.modules.comprehension.domain import accept_ai
from dataflow.modules.comprehension.measures import least_frequent
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings

COLUMNS = ["empleado_id", "area", "salario", "activo", "dias_ausencia_2024"]


def reply(**changes: object) -> AIComprehension:
    data: dict[str, object] = {
        "domain": "Empleados de una empresa.",
        "entities": [],
        "meanings": [],
        "orders": {},
        "relationships": [],
        "questions": [],
        "target": ("activo", "La rotación es lo que preocupa."),
        "theme": "Recursos humanos",
        "target_label": "Bajas de empleados",
        "labels": {
            "salario": "Salario",
            "area": "Área",
            "dias_ausencia_2024": "Ausencias dias_ausencia_2024",
            "inventada": "Algo",
        },
    }
    data.update(changes)
    return AIComprehension.model_validate(data)


def test_short_business_names_are_validated() -> None:
    accepted, discarded = accept_ai(reply(), COLUMNS)
    assert accepted.theme == "Recursos humanos"
    assert accepted.target_label == "Bajas de empleados"
    # Las cifras de un nombre de columna se admiten; las columnas inventadas no.
    assert accepted.labels == {
        "salario": "Salario",
        "area": "Área",
        "dias_ausencia_2024": "Ausencias dias_ausencia_2024",
    }
    assert not discarded
    long, discarded = accept_ai(
        reply(
            theme="Gestión integral de las personas",
            target_label="Bajas 2024",
            labels={"salario": "Salario bruto mensual en pesos"},
        ),
        COLUMNS,
    )
    assert long.theme == "" and long.target_label == "" and long.labels == {}
    assert any("Tema" in d for d in discarded)
    assert any("Nombre del objetivo" in d for d in discarded)
    assert any("Nombre corto de «salario»" in d for d in discarded)


def test_the_counted_category_follows_the_investigation_rule() -> None:
    assert least_frequent(parquet(["Si", "No", "Si", None]), "activo") == "No"
    assert least_frequent(parquet(["Si", "No"]), "activo") == "No"  # empate: alfabético
    assert least_frequent(parquet(["A", "B", "C"]), "activo") is None


def parquet(values: list[str | None]) -> bytes:
    buffer = io.BytesIO()
    pl.DataFrame({"activo": values}).write_parquet(buffer)
    return buffer.getvalue()


def test_comprehension_publishes_business_names(
    client: TestClient, db: Session, objects: LocalObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, roster(), name="plantilla.csv").json()["id"]
    run_all(db, objects)
    understood = get(client, f"/api/v1/versions/{version}/comprehension")["comprehension"]
    assert understood["rules_version"] == "business-comprehension-v6"
    assert understood["theme"] == "Actividad"
    target = understood["target"]
    assert target["column"] == "activo" and target["origin"] == "ai"
    assert target["label"] == "Resultado de activo" and target["counted"] == "No"
    # La IA falsa da a la última columna un nombre demasiado largo: se retira con motivo.
    assert understood["labels"]["salario"] == "Salario" and "activo" not in understood["labels"]
    assert any("Nombre corto de «activo»" in d for d in understood["discarded"])
