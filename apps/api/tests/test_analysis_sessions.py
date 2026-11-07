"""Fase 11A: sesión de análisis con una sola fuente activa por proyecto."""

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.audit.infrastructure import AuditRecord
from dataflow.modules.datasets.objects import LocalObjects

VALID_A = b"id,importe,region\n001,10.50,Norte\n002,20.00,Sur\n"
VALID_C = b"id,importe,region\n003,5.00,Este\n"
INVALID = b"id,nombre\n1\n"  # CSV_SHAPE: el procesamiento falla


class Workspace:
    def __init__(self, client: TestClient, db: Session, objects: LocalObjects) -> None:
        self.client, self.db, self.objects = client, db, objects
        self.headers = account(client)
        self.project_id = project(client, self.headers)

    def load(self, content: bytes, process: bool = True) -> dict[str, Any]:
        version = upload(self.client, self.headers, self.project_id, content).json()
        if process:
            assert make_runner(self.db, self.objects).run_once()
        return version  # type: ignore[no-any-return]

    def open(self) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/analysis-sessions", headers=self.headers
        )
        assert response.status_code in {200, 201}, response.text
        return response.json()  # type: ignore[no-any-return]

    def select(self, session: dict[str, Any], version: str, expected: int) -> Any:
        return self.client.post(
            f"/api/v1/analysis-sessions/{session['id']}/inputs",
            json={"version_id": version, "expected_revision": expected},
            headers=self.headers,
        )


def test_one_session_per_project_starts_empty(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    ws = Workspace(client, db, objects)
    missing = client.get(f"/api/v1/projects/{ws.project_id}/analysis-session")
    assert missing.status_code == 404 and missing.json()["code"] == "ANALYSIS_SESSION_NOT_FOUND"
    created = client.post(f"/api/v1/projects/{ws.project_id}/analysis-sessions", headers=ws.headers)
    assert created.status_code == 201
    session = created.json()
    assert (session["status"], session["revision"], session["active"]) == ("empty", 0, None)
    again = client.post(f"/api/v1/projects/{ws.project_id}/analysis-sessions", headers=ws.headers)
    assert again.status_code == 200 and again.json()["id"] == session["id"]
    assert client.get(f"/api/v1/projects/{ws.project_id}/analysis-session").json() == session
    assert client.get(f"/api/v1/analysis-sessions/{session['id']}").json() == session


def test_invalid_candidate_keeps_the_active_source(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    ws = Workspace(client, db, objects)
    a = ws.load(VALID_A)
    session = ws.open()
    selected = ws.select(session, a["id"], 0)
    assert selected.status_code == 200, selected.text
    active = selected.json()
    assert active["status"] == "ready" and active["revision"] == 1
    assert active["active"]["version_id"] == a["id"]
    assert active["active"]["version_number"] == 1
    table = client.get(f"/api/v1/versions/{a['id']}/representations").json()[0]
    assert active["active"]["table_artifact_id"] == table["id"]
    assert active["active"]["table_sha256"] == table["sha256"]

    # B no se puede procesar: no sustituye a A.
    b = ws.load(INVALID)
    rejected = ws.select(session, b["id"], 1)
    assert rejected.status_code == 409 and rejected.json()["code"] == "INPUT_INVALID"
    # B2 todavía en cola: tampoco.
    pending = ws.load(VALID_C, process=False)
    waiting = ws.select(session, pending["id"], 1)
    assert waiting.status_code == 409 and waiting.json()["code"] == "INPUT_NOT_READY"
    current = client.get(f"/api/v1/analysis-sessions/{session['id']}").json()
    assert current == active


def test_switching_source_keeps_history_and_previous_analyses(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    ws = Workspace(client, db, objects)
    a = ws.load(VALID_A)
    session = ws.open()
    assert ws.select(session, a["id"], 0).status_code == 200
    table_a = client.get(f"/api/v1/versions/{a['id']}/representations").json()[0]
    plan = client.post(
        f"/api/v1/projects/{ws.project_id}/plans",
        json={
            "table_artifact_id": table_a["id"],
            "table_sha256": table_a["sha256"],
            "steps": [
                {
                    "id": "profile",
                    "operation": "understanding.profile",
                    "version": 1,
                    "input": {"kind": "input"},
                    "parameters": {"algorithm": "column-profile-v1"},
                }
            ],
        },
        headers={**ws.headers, "Idempotency-Key": str(uuid4())},
    )
    assert plan.status_code == 201, plan.text

    c = ws.load(VALID_C)
    switched = ws.select(session, c["id"], 1)
    assert switched.status_code == 200, switched.text
    assert switched.json()["revision"] == 2 and switched.json()["active"]["version_id"] == c["id"]
    # El plan sobre A sigue fijado a la tabla de A.
    kept = client.get(f"/api/v1/plans/{plan.json()['id']}").json()
    assert kept["input"]["artifact_id"] == table_a["id"]

    # Mismo origen otra vez: sin revisión nueva.
    same = ws.select(session, c["id"], 2)
    assert same.status_code == 200 and same.json()["revision"] == 2
    # Revisión esperada antigua: conflicto, sin cambios.
    stale = ws.select(session, a["id"], 1)
    assert stale.status_code == 409 and stale.json()["code"] == "ANALYSIS_SESSION_CONFLICT"

    history = client.get(f"/api/v1/analysis-sessions/{session['id']}/inputs").json()
    assert history["total"] == 2
    assert [item["version_id"] for item in history["items"]] == [c["id"], a["id"]]
    assert [item["revision"] for item in history["items"]] == [2, 1]
    page = client.get(
        f"/api/v1/analysis-sessions/{session['id']}/inputs", params={"limit": 1, "offset": 1}
    ).json()
    assert [item["revision"] for item in page["items"]] == [1]
    actions = db.scalars(
        select(AuditRecord.action).where(AuditRecord.entity_id == session["id"])
    ).all()
    assert actions == ["analysis_session.input_selected"] * 2


def test_access_rules(client: TestClient, db: Session, objects: LocalObjects) -> None:
    ws = Workspace(client, db, objects)
    a = ws.load(VALID_A)
    session = ws.open()
    other_project = project(client, ws.headers)
    foreign = upload(client, ws.headers, other_project, VALID_C).json()
    assert make_runner(db, objects).run_once()
    wrong = ws.select(session, foreign["id"], 0)
    assert wrong.status_code == 404 and wrong.json()["code"] == "INPUT_NOT_FOUND"
    unknown = ws.select(session, str(uuid4()), 0)
    assert unknown.status_code == 404

    archived = client.post(
        f"/api/v1/projects/{ws.project_id}/archive",
        json={"expected_revision": 1},
        headers=ws.headers,
    )
    assert archived.status_code == 200, archived.text
    blocked = ws.select(session, a["id"], 0)
    assert blocked.status_code == 409 and blocked.json()["code"] == "PROJECT_ARCHIVED"
    assert client.get(f"/api/v1/analysis-sessions/{session['id']}").status_code == 200

    stranger = account(client)
    assert client.get(f"/api/v1/analysis-sessions/{session['id']}").status_code == 404
    denied = client.post(
        f"/api/v1/analysis-sessions/{session['id']}/inputs",
        json={"version_id": a["id"], "expected_revision": 0},
        headers=stranger,
    )
    assert denied.status_code == 404
    other = client.post(f"/api/v1/projects/{ws.project_id}/analysis-sessions", headers=stranger)
    assert other.status_code == 404
