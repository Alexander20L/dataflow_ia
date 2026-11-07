"""Fase 11C: pipeline automático durable (worker + reconciliador) de punta a punta."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_pipeline, make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ExecutionRecord
from dataflow.platform.config import get_settings

CSV = (Path(__file__).resolve().parents[3] / "examples" / "ventas_calidad.csv").read_bytes()
CLEAN = b"id,importe\n001,10\n002,20\n"
# ventas_calidad.csv: recortar, excluir importe nulo y deduplicar quitan 3 de 6 filas (50 %).
FULL_POLICY: dict[str, Any] = {
    "enabled": True,
    "allowed_operations": [
        "cleaning.trim_whitespace",
        "cleaning.filter_rows",
        "cleaning.deduplicate",
    ],
    "column_scopes": [
        {"operation": "cleaning.trim_whitespace", "columns": ["*"]},
        {"operation": "cleaning.filter_rows", "columns": ["importe"]},
        {"operation": "cleaning.deduplicate", "columns": ["*"]},
    ],
    "max_excluded_rows_pct": "50",
    "max_nulls_created_pct": "50",
}


class Pipeline:
    def __init__(self, client: TestClient, db: Session, objects: LocalObjects) -> None:
        self.client, self.db, self.objects = client, db, objects
        self.headers = account(client)
        self.project_id = project(client, self.headers)
        self.policy_revision = 0

    def policy(self, content: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/automation-policy",
            json={"expected_revision": self.policy_revision, "content": content},
            headers={**self.headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 200, response.text
        self.policy_revision = response.json()["revision"]
        return response.json()  # type: ignore[no-any-return]

    def load(self, content: bytes = CSV) -> dict[str, Any]:
        return upload(self.client, self.headers, self.project_id, content).json()  # type: ignore[no-any-return]

    def tick(self) -> None:
        make_runner(self.db, self.objects).run_once()
        make_pipeline(self.db, self.objects).reconcile()

    def run(self, version: str) -> dict[str, Any] | None:
        return self.client.get(f"/api/v1/versions/{version}/automation-run").json()["run"]  # type: ignore[no-any-return]

    def drive(self, version: str, limit: int = 12) -> dict[str, Any]:
        for _ in range(limit):
            self.tick()
            current = self.run(version)
            if current and current["state"] != "running":
                return current
        current = self.run(version)
        assert current is not None
        return current

    def active(self) -> dict[str, Any] | None:
        session = self.client.get(f"/api/v1/projects/{self.project_id}/analysis-session")
        return session.json()["active"] if session.status_code == 200 else None


@pytest.fixture
def pipe(client: TestClient, db: Session, objects: LocalObjects) -> Pipeline:
    return Pipeline(client, db, objects)


def steps(run: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item["step"], item["outcome"]) for item in run["attempts"]]


def test_full_pipeline_cleans_publishes_and_activates_the_derived_version(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load()
    run = pipe.drive(version["id"])
    assert run["state"] == "completed", run
    assert run["step"] == "done" and run["reasons"] == []
    assert run["derived_version_id"] and run["result_version_id"] == run["derived_version_id"]
    derived = pipe.client.get(f"/api/v1/versions/{run['derived_version_id']}").json()
    assert derived["kind"] == "derived" and derived["parent_version_id"] == version["id"]
    assert derived["row_count"] == 3
    active = pipe.active()
    assert active and active["version_id"] == run["derived_version_id"]
    origin = pipe.client.get(f"/api/v1/approvals/{run['approval_id']}/origin").json()
    assert origin["automatic"] and origin["executor"] == "pipeline"
    assert origin["pipeline_run_id"] == run["id"]
    assert ("quality_rules", "succeeded") in steps(run)
    assert steps(run)[-1] == ("select", "succeeded")
    # El original no cambia y queda seleccionable.
    assert pipe.client.get(f"/api/v1/versions/{version['id']}").json()["state"] == "succeeded"


def test_policy_block_stops_for_review_without_changes(pipe: Pipeline) -> None:
    pipe.policy(
        {
            "enabled": True,
            "allowed_operations": ["cleaning.trim_whitespace"],
            "column_scopes": [{"operation": "cleaning.trim_whitespace", "columns": ["*"]}],
        }
    )
    version = pipe.load()
    run = pipe.drive(version["id"])
    assert run["state"] == "needs_review" and run["step"] == "approve"
    # Excluir filas y deduplicar no están autorizadas, y el límite por defecto es 0 %.
    assert {r["code"] for r in run["reasons"]} == {
        "OPERATION_NOT_AUTHORIZED",
        "EXCLUDED_ROWS_ABOVE_LIMIT",
    }
    assert run["approval_id"] is None and run["derived_version_id"] is None
    assert pipe.active() is None
    notices = pipe.client.get("/api/v1/notifications").json()["items"]
    assert [item["id"] for item in notices] == [run["id"]]
    # Detenido: el reconciliador no lo vuelve a intentar.
    pipe.tick()
    assert pipe.run(version["id"])["state"] == "needs_review"  # type: ignore[index]


def test_nothing_to_clean_activates_the_imported_version(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load(CLEAN)
    run = pipe.drive(version["id"])
    assert run["state"] == "completed" and run["plan_revision_id"] is None
    assert run["result_version_id"] == version["id"]
    assert pipe.active()["version_id"] == version["id"]  # type: ignore[index]


def test_disabled_or_missing_policy_starts_nothing(pipe: Pipeline) -> None:
    version = pipe.load()
    pipe.tick()
    assert pipe.run(version["id"]) is None
    pipe.policy({**FULL_POLICY, "enabled": False})
    second = pipe.load(CLEAN)
    pipe.tick()
    assert pipe.run(second["id"]) is None


def test_steps_are_idempotent_under_repeated_reconciliation(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load()
    make_runner(pipe.db, pipe.objects).run_once()  # importación → crea el pipeline
    service = make_pipeline(pipe.db, pipe.objects)
    for _ in range(3):  # tres reconciliaciones seguidas antes de que el worker procese nada
        service.reconcile()
    previews = pipe.db.scalar(
        select(func.count())
        .select_from(ExecutionRecord)
        .where(
            ExecutionRecord.version_id == version["id"],
            ExecutionRecord.kind == "cleaning_preview",
        )
    )
    assert previews == 1
    run = pipe.drive(version["id"])
    assert run["state"] == "completed"
    assert [s for s in steps(run) if s == ("preview", "started")] == [("preview", "started")]


def test_cancel_stops_the_pipeline(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load()
    make_runner(pipe.db, pipe.objects).run_once()
    run = pipe.run(version["id"])
    assert run and run["state"] == "running"
    cancelled = pipe.client.post(
        f"/api/v1/automation-runs/{run['id']}/cancel", headers=pipe.headers
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    pipe.tick()
    assert pipe.run(version["id"])["state"] == "cancelled"  # type: ignore[index]
    assert pipe.active() is None


def test_policy_changed_mid_run_requires_review(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load()
    make_runner(pipe.db, pipe.objects).run_once()  # importación
    make_pipeline(pipe.db, pipe.objects).reconcile()  # propone y encola la vista previa
    pipe.policy({**FULL_POLICY, "max_excluded_rows_pct": "60"})
    run = pipe.drive(version["id"])
    assert run["state"] == "needs_review"
    assert [r["code"] for r in run["reasons"]] == ["POLICY_CHANGED"]


def test_running_limit_leaves_extra_loads_for_review(
    pipe: Pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "automation_max_running_per_owner", 1)
    pipe.policy(FULL_POLICY)
    runner = make_runner(pipe.db, pipe.objects)
    first = pipe.load()
    runner.run_once()  # el primer pipeline queda en curso (sin reconciliar)
    second = pipe.load(CLEAN)
    runner.run_once()
    states = {pipe.run(v["id"])["state"] for v in (first, second)}  # type: ignore[index]
    assert states == {"running", "needs_review"}
    limited = next(
        run
        for v in (first, second)
        if (run := pipe.run(v["id"]))["state"] == "needs_review"  # type: ignore[index]
    )
    assert [r["code"] for r in limited["reasons"]] == ["AUTOMATION_LIMIT"]


def test_runs_are_private(pipe: Pipeline) -> None:
    pipe.policy(FULL_POLICY)
    version = pipe.load()
    run = pipe.drive(version["id"])
    listed = pipe.client.get(f"/api/v1/projects/{pipe.project_id}/automation-runs").json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == run["id"]
    account(pipe.client)
    assert pipe.client.get(f"/api/v1/automation-runs/{run['id']}").status_code == 404
    assert pipe.client.get("/api/v1/notifications").json()["items"] == []
