from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import CSV, account, project, upload

from dataflow.bootstrap.services import (
    make_executions,
    make_ingestion,
    make_planning,
    make_runner,
    make_semantics,
)
from dataflow.modules.datasets.infrastructure import DatasetDefaultRecord, VersionRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import PlanBindingRecord, PlanRecord
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.planning.contracts import PlanDraft
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.platform.errors import ApplicationError

PROFILE = {
    "id": "profile",
    "operation": "understanding.profile",
    "version": 1,
    "input": {"kind": "input"},
}
QUALITY = {
    "id": "quality",
    "operation": "quality.evaluate",
    "version": 1,
    "input": {"kind": "input"},
}


def key(headers: dict[str, str], value: str | None = None) -> dict[str, str]:
    return {**headers, "Idempotency-Key": value or str(uuid4())}


def prepared(
    client: TestClient, db: Session, objects: LocalObjects, content: bytes = CSV
) -> tuple[dict[str, str], str, dict[str, Any], dict[str, Any]]:
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id, content).json()
    assert make_runner(db, objects).run_once()
    table = client.get(f"/api/v1/versions/{version['id']}/representations").json()[0]
    return headers, project_id, version, table


def create(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    table: dict[str, Any],
    steps: list[dict[str, Any]],
    idempotency: str | None = None,
    **extra: Any,
) -> Any:
    return client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={
            "table_artifact_id": table["id"],
            "table_sha256": table["sha256"],
            "steps": steps,
            **extra,
        },
        headers=key(headers, idempotency),
    )


def codes(plan: dict[str, Any]) -> list[str]:
    return [problem["code"] for problem in plan["validation"]["problems"]]


def test_catalog_and_applicable_operations(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    _, _, _, table = prepared(client, db, objects)
    catalog = client.get("/api/v1/operations").json()
    assert catalog["catalog_version"] == "analysis-v12"
    operations = {op["key"]: op for op in catalog["operations"]}
    assert set(operations) == {
        "ingestion.read_csv@1",
        "ingestion.read_xlsx@1",
        "understanding.profile@1",
        "understanding.profile@2",
        "understanding.profile@3",
        "understanding.profile@4",
        "quality.evaluate@1",
        "quality.evaluate@2",
        "quality.evaluate@3",
        "analytics.automatic@1",
        "analytics.query@1",
        "analytics.query@2",
        "analytics.query@3",
        "cleaning.trim_whitespace@1",
        "cleaning.filter_rows@1",
        "cleaning.normalize_null_tokens@1",
        "cleaning.cast@1",
        "cleaning.deduplicate@1",
    }
    assert operations["ingestion.read_csv@1"]["input_kind"] == "source"
    assert operations["quality.evaluate@1"]["output_kind"] == "quality"
    assert {key for key, op in operations.items() if op["transforms_data"]} == {
        key for key in operations if key.startswith("cleaning.")
    }
    assert not any(op["requirements"] for op in operations.values())
    trim_schema = operations["cleaning.trim_whitespace@1"]["parameters_schema"]
    assert trim_schema["properties"]["column_ids"]["x-dataflow-column-ref"] is True
    assert operations["understanding.profile@1"]["parameters_schema"]["properties"]["algorithm"]
    applicable = {
        item["key"]: item
        for item in client.get(
            f"/api/v1/representations/{table['id']}/applicable-operations"
        ).json()
    }
    assert applicable["ingestion.read_csv@1"]["applicable"] is False
    assert applicable["ingestion.read_csv@1"]["reason"]
    assert applicable["understanding.profile@1"]["applicable"] is True
    assert all(not item["missing_requirements"] for item in applicable.values())
    client.cookies.clear()
    assert client.get("/api/v1/operations").status_code == 401


def test_save_reload_and_execute_exact_table_after_default_changes(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, version, table = prepared(client, db, objects)
    empty = create(client, headers, project_id, table, [])
    assert empty.status_code == 201, empty.text
    first = empty.json()
    assert first["revision"] == 1 and first["validation"]["status"] == "incomplete"
    assert codes(first) == ["EMPTY_PLAN"]
    assert first["input"]["artifact_id"] == table["id"]
    assert first["input"]["artifact_sha256"] == table["sha256"]
    blocked = client.post(f"/api/v1/plans/{first['id']}/executions", headers=key(headers))
    assert blocked.status_code == 422 and blocked.json()["code"] == "PLAN_INCOMPLETE"

    revised = client.post(
        f"/api/v1/plans/{first['family_id']}/revisions",
        json={"expected_revision": 1, "steps": [PROFILE, QUALITY]},
        headers=headers,
    )
    assert revised.status_code == 201, revised.text
    second = revised.json()
    assert second["revision"] == 2 and second["validation"]["valid"] is True
    # Los parámetros se guardan explícitos (valores por defecto del catálogo incluidos).
    assert second["steps"][0]["parameters"] == {"algorithm": "column-profile-v1"}
    assert second["steps"][1]["parameters"]["rules"] == ["Q-001", "Q-002", "Q-003"]
    assert client.get(f"/api/v1/plans/{second['id']}").json() == second
    old = client.get(f"/api/v1/plans/{first['id']}").json()
    assert old["revision"] == 1 and old["head_revision"] == 2 and codes(old) == ["EMPTY_PLAN"]
    stale = client.post(
        f"/api/v1/plans/{first['family_id']}/revisions",
        json={"expected_revision": 1, "steps": [QUALITY]},
        headers=headers,
    )
    assert stale.status_code == 409 and stale.json()["code"] == "PLAN_REVISION_CONFLICT"
    same = client.post(
        f"/api/v1/plans/{first['family_id']}/revisions",
        json={"expected_revision": 2, "steps": [PROFILE, QUALITY]},
        headers=headers,
    ).json()
    assert same["id"] == second["id"]  # sin cambios: no se crea una revisión vacía
    page = client.get(f"/api/v1/projects/{project_id}/plans").json()
    assert page["total"] == 1 and [item["id"] for item in page["items"]] == [second["id"]]

    # Nueva carga en el proyecto: cambia la versión predeterminada del dataset.
    newer = upload(client, headers, project_id, CSV + b"004,1.00,Este,9\r\n").json()
    assert make_runner(db, objects).run_once()
    default = db.scalar(select(DatasetDefaultRecord))
    assert default and default.version_id == UUID(newer["id"])
    assert default.table_artifact_id != UUID(table["id"])

    request_key = str(uuid4())
    queued = client.post(
        f"/api/v1/plans/{second['id']}/executions", headers=key(headers, request_key)
    )
    assert queued.status_code == 202, queued.text
    run = queued.json()
    assert run["kind"] == "plan" and run["state"] == "queued"
    assert run["version_id"] == version["id"] and run["input_artifact_id"] == table["id"]
    assert run["input_artifact_sha256"] == table["sha256"] and run["plan"]["id"] == second["id"]
    replay = client.post(
        f"/api/v1/plans/{second['id']}/executions", headers=key(headers, request_key)
    )
    assert replay.status_code == 202 and replay.json()["id"] == run["id"]
    # Encolar referencia la revisión guardada: 2 planes de importación + 2 revisiones de usuario.
    assert db.scalar(select(func.count()).select_from(PlanRecord)) == 4
    assert db.scalar(select(func.count()).select_from(PlanBindingRecord)) == 2
    assert make_runner(db, objects).run_once()
    done = client.get(f"/api/v1/executions/{run['id']}").json()
    assert (
        done["state"] == "succeeded" and done["plan"]["content_sha256"] == second["content_sha256"]
    )
    kinds = sorted(
        a["kind"] for a in client.get(f"/api/v1/executions/{run['id']}/artifacts").json()
    )
    assert kinds == ["profile", "quality"]
    quality = client.get(f"/api/v1/executions/{run['id']}/quality").json()
    assert quality["row_count"] == 4
    listed = client.get(f"/api/v1/versions/{version['id']}/executions").json()
    assert run["id"] in [item["id"] for item in listed]


def test_problems_are_reported_not_raised(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, _, table = prepared(client, db, objects)
    plan = create(
        client,
        headers,
        project_id,
        table,
        [
            {**PROFILE, "parameters": {"algorithm": "otro"}},
            {
                "id": "read",
                "operation": "ingestion.read_csv",
                "version": 1,
                "input": {"kind": "input"},
                "parameters": {"separator": ","},
            },
            {
                "id": "trim",
                "operation": "cleaning.impute",
                "version": 1,
                "input": {"kind": "input"},
            },
            {**QUALITY, "input": {"kind": "step", "step_id": "profile"}},
        ],
    ).json()
    assert codes(plan) == [
        "INVALID_PARAMETERS",
        "INPUT_KIND_MISMATCH",
        "UNSUPPORTED_OPERATION",
        "INVALID_STEP_REFERENCE",
    ]
    # Parámetros incompletos se conservan tal cual para poder corregirlos.
    assert plan["steps"][0]["parameters"] == {"algorithm": "otro"}
    problem = plan["validation"]["problems"][0]
    assert problem["step_id"] == "profile" and problem["resolve_in"] == "plan_steps"
    response = create(
        client, headers, project_id, table, [{**PROFILE, "parameters": {"Bad-Key": 1}}]
    )
    assert response.status_code == 422 and response.json()["code"] == "PLAN_NOT_CANONICAL"
    too_many = create(
        client, headers, project_id, table, [{**QUALITY, "id": f"q{i}"} for i in range(17)]
    )
    assert codes(too_many.json()) == ["TOO_MANY_STEPS"]


def test_idempotency_access_and_input_checks(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, _, table = prepared(client, db, objects)
    request_key = str(uuid4())
    plan = create(client, headers, project_id, table, [QUALITY], request_key).json()
    replay = create(client, headers, project_id, table, [QUALITY], request_key)
    assert replay.status_code == 201 and replay.json()["id"] == plan["id"]
    conflict = create(client, headers, project_id, table, [PROFILE], request_key)
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    wrong_hash = create(client, headers, project_id, {**table, "sha256": "0" * 64}, [QUALITY])
    assert wrong_hash.status_code == 409 and wrong_hash.json()["code"] == "INPUT_MISMATCH"
    other_project = project(client, headers)
    misplaced = create(client, headers, other_project, table, [QUALITY])
    assert misplaced.status_code == 409 and misplaced.json()["code"] == "INPUT_MISMATCH"
    missing_csrf = client.post(
        f"/api/v1/plans/{plan['id']}/executions", headers={"Idempotency-Key": str(uuid4())}
    )
    assert missing_csrf.status_code == 403 and missing_csrf.json()["code"] == "CSRF_INVALID"
    foreign_origin = client.post(
        f"/api/v1/plans/{plan['id']}/executions",
        headers={**key(headers), "Origin": "https://evil.example"},
    )
    assert foreign_origin.status_code == 403 and foreign_origin.json()["code"] == "ORIGIN_FORBIDDEN"

    intruder = account(client)
    for response in [
        client.get(f"/api/v1/plans/{plan['id']}"),
        client.get(f"/api/v1/projects/{project_id}/plans"),
        client.get(f"/api/v1/representations/{table['id']}/applicable-operations"),
        client.post(f"/api/v1/plans/{plan['id']}/executions", headers=key(intruder)),
        client.post(
            f"/api/v1/plans/{plan['family_id']}/revisions",
            json={"expected_revision": 1, "steps": [PROFILE]},
            headers=intruder,
        ),
        create(client, intruder, project_id, table, [QUALITY]),
    ]:
        assert response.status_code == 404, response.text
    assert db.scalar(select(func.count()).select_from(PlanBindingRecord)) == 1


def test_archived_project_plans_are_read_only(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, _, table = prepared(client, db, objects)
    plan = create(client, headers, project_id, table, [QUALITY]).json()
    revision = client.get(f"/api/v1/projects/{project_id}").json()["revision"]
    archived = client.post(
        f"/api/v1/projects/{project_id}/archive",
        json={"expected_revision": revision},
        headers=headers,
    )
    assert archived.status_code == 200, archived.text
    assert client.get(f"/api/v1/plans/{plan['id']}").status_code == 200
    for response in [
        create(client, headers, project_id, table, [QUALITY]),
        client.post(f"/api/v1/plans/{plan['id']}/executions", headers=key(headers)),
        client.post(
            f"/api/v1/plans/{plan['family_id']}/revisions",
            json={"expected_revision": 1, "steps": [PROFILE]},
            headers=headers,
        ),
    ]:
        assert response.status_code == 409 and response.json()["code"] == "PROJECT_ARCHIVED"


def test_semantic_revision_is_pinned_and_verified(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, _, table = prepared(client, db, objects)
    owner = UUID(client.get("/api/v1/auth/me").json()["user"]["id"])
    semantics = make_semantics(db, objects)
    context = semantics.context(owner, UUID(table["id"]))
    saved = semantics.save(
        owner, UUID(table["id"]), table["sha256"], 0, context.editable, uuid4(), str(uuid4())
    ).revision
    reference = {
        "id": str(saved.id),
        "revision": saved.revision,
        "content_sha256": saved.content_sha256,
    }
    plan = create(client, headers, project_id, table, [QUALITY], semantic_ref=reference).json()
    assert plan["validation"]["valid"] and plan["semantic_ref"] == reference
    binding = db.get(PlanBindingRecord, UUID(plan["id"]))
    assert binding and binding.semantic_revision_id == saved.id
    applicable = client.get(
        f"/api/v1/representations/{table['id']}/applicable-operations",
        params={"semantic_revision_id": str(saved.id)},
    )
    assert applicable.status_code == 200
    forged = create(
        client, headers, project_id, table, [QUALITY], semantic_ref={**reference, "revision": 2}
    )
    assert forged.status_code == 409 and forged.json()["code"] == "SEMANTIC_REFERENCE_MISMATCH"
    run = client.post(f"/api/v1/plans/{plan['id']}/executions", headers=key(headers)).json()
    assert make_runner(db, objects).run_once()
    assert client.get(f"/api/v1/executions/{run['id']}").json()["state"] == "succeeded"


def test_legacy_05_executions_are_unchanged_and_not_listed_as_plans(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, project_id, version, table = prepared(client, db, objects)
    response = client.post(
        f"/api/v1/versions/{version['id']}/analyses",
        json={
            "table_artifact_id": table["id"],
            "table_sha256": table["sha256"],
            "analysis_kind": "quality_only",
        },
        headers=key(headers),
    )
    assert response.status_code == 202, response.text
    assert make_runner(db, objects).run_once()
    run = client.get(f"/api/v1/executions/{response.json()['id']}").json()
    assert run["kind"] == "table_analysis" and run["state"] == "succeeded"
    assert [step["id"] for step in run["plan"]["content"]["steps"]] == ["quality"]
    assert client.get(f"/api/v1/executions/{run['id']}/quality").status_code == 200
    baseline = client.get(f"/api/v1/executions/{version['execution_id']}").json()
    assert (
        baseline["kind"] == "csv_import"
        and baseline["plan"]["content"]["input"]["kind"] == "source"
    )
    assert client.get(f"/api/v1/projects/{project_id}/plans").json()["total"] == 0
    assert db.scalar(select(func.count()).select_from(VersionRecord)) == 1


def test_concurrent_revisions_with_same_expected_revision_conflict(
    committed_engine: Engine, tmp_path: Path
) -> None:
    objects = LocalObjects(tmp_path / "planning_objects")
    owner = uuid4()
    with Session(committed_engine, expire_on_commit=False) as db:
        db.add(
            UserRecord(
                id=owner,
                email="planning-concurrency@example.com",
                name="Planning",
                password_hash="not-an-account",
            )
        )
        db.commit()
        project_record = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
            owner, "Planning concurrency", "", None
        )
        version = make_ingestion(db, objects).submit(
            owner, project_record.id, "test.csv", CSV, ",", uuid4(), str(uuid4())
        )
        assert make_runner(db, objects).run_once()
        table = next(
            a
            for a in make_executions(db).artifacts(owner, version.execution_id)
            if a.kind == "table"
        )
        plan = make_planning(db, objects).create(
            owner,
            project_record.id,
            table.id,
            table.content.sha256,
            PlanDraft(steps=[]),
            uuid4(),
            str(uuid4()),
        )
    barrier = Barrier(2)

    def concurrent_revise(steps: list[dict[str, Any]]) -> int | str:
        with Session(committed_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            try:
                draft = PlanDraft.model_validate({"steps": steps})
                return make_planning(db, objects).revise(owner, plan.family_id, 1, draft).revision
            except ApplicationError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(concurrent_revise, steps) for steps in ([PROFILE], [QUALITY])]
        values = sorted(str(future.result(timeout=30)) for future in futures)
    assert values == ["2", "PLAN_REVISION_CONFLICT"]
    with Session(committed_engine) as db:
        assert db.scalar(select(func.count()).select_from(PlanBindingRecord)) == 2
