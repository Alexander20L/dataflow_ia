from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import CSV, account, process, project, upload

from dataflow.bootstrap.services import make_ingestion, make_runner, make_semantics
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.identity.infrastructure import UserRecord
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.understanding.semantic_repository import (
    SemanticFamilyRecord,
    SemanticRevisionRecord,
    SemanticSaveRequest,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


def prepared(client: TestClient, db: Session, objects: LocalObjects):
    headers = account(client)
    project_id = project(client, headers)
    version = upload(client, headers, project_id).json()
    assert process(db, objects)
    table = client.get(f"/api/v1/versions/{version['id']}/representations").json()[0]
    context = client.get(f"/api/v1/representations/{table['id']}/understanding")
    assert context.status_code == 200, context.text
    return headers, version, table, context.json()


def save(
    client: TestClient,
    headers: dict,
    table: dict,
    draft: dict,
    expected: int,
    key: str | None = None,
):
    return client.post(
        f"/api/v1/representations/{table['id']}/semantic-contracts",
        json={"table_sha256": table["sha256"], "expected_revision": expected, "draft": draft},
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def test_semantic_revisions_are_partial_immutable_and_do_not_transform_data(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, version, table, context = prepared(client, db, objects)
    assert context["head"] is None and context["revision_count"] == 0
    assert db.scalar(select(func.count()).select_from(SemanticFamilyRecord)) == 0
    assert all(
        s["origin"] == "heuristic" and s["state"] == "pending" for s in context["suggestions"]
    )
    assert all(c["review_state"] == "pending" for c in context["editable"]["columns"])
    original = client.get(f"/api/v1/versions/{version['id']}/original").content
    diagnostic = client.get(f"/api/v1/versions/{version['id']}/diagnostic").json()
    draft = context["editable"]
    draft["dataset_description"] = "Ventas para revisar"
    draft["row_grain"] = {"description": "Una operación comercial", "review_state": "confirmed"}
    draft["columns"][0].update(
        role="identifier", interpretation_type="string", parse_format=None, review_state="confirmed"
    )
    draft["columns"][1].update(
        role="measure",
        currency="EUR",
        description="Importe declarado por el usuario",
        review_state="confirmed",
    )
    draft["key"] = {
        "column_ids": [draft["columns"][0]["column_id"]],
        "null_policy": "reject",
        "review_state": "confirmed",
    }
    key = str(uuid4())
    response = save(client, headers, table, draft, 0, key)
    assert response.status_code == 200, response.text
    first = response.json()["revision"]
    assert first["revision"] == 1 and first["previous_revision_id"] is None
    assert first["content_sha256"] == digest("semantic", first["content"])
    for column in first["content"]["columns"][:2]:
        assert (
            column["review"]["origin"] == "user"
            and column["review"]["actor_id"] == first["created_by"]
        )
        assert column["review"]["reviewed_at"]
    refreshed = client.get(f"/api/v1/representations/{table['id']}/understanding").json()
    assert refreshed["key_assessment"]["duplicate_key_rows"] == 1
    assert any(w["code"] == "KEY_DUPLICATES" for w in refreshed["warnings"])
    assert save(client, headers, table, draft, 1).json()["changed"] is False
    assert db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) == 1
    changed = refreshed["editable"]
    changed["columns"][1]["description"] = "Descripción corregida"
    second_response = save(client, headers, table, changed, 1)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()["revision"]
    assert second["revision"] == 2 and second["previous_revision_id"] == first["id"]
    assert second["content"]["columns"][0]["review"] == first["content"]["columns"][0]["review"]
    replay = save(client, headers, table, draft, 0, key).json()
    assert replay["revision"]["id"] == first["id"] and replay["head_revision"] == 2
    assert save(client, headers, table, changed, 1, key).status_code == 409
    history = client.get(f"/api/v1/representations/{table['id']}/semantic-contracts").json()
    assert [r["revision"] for r in history["items"]] == [2, 1]
    assert client.get(f"/api/v1/semantic-contracts/{first['id']}").json() == first
    assert client.get(f"/api/v1/versions/{version['id']}/original").content == original
    assert client.get(f"/api/v1/versions/{version['id']}/diagnostic").json() == diagnostic
    assert (
        client.get(f"/api/v1/versions/{version['id']}/preview").json()["rows"][0]["values"]["id"]
        == "001"
    )


def test_semantic_reference_is_optional_exact_and_historical(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, version, table, context = prepared(client, db, objects)
    first = save(client, headers, table, context["editable"], 0).json()["revision"]
    ref = {k: first[k] for k in ["id", "revision", "content_sha256"]}
    body = {
        "table_artifact_id": table["id"],
        "table_sha256": table["sha256"],
        "analysis_kind": "profile_quality",
        "semantic_ref": ref,
    }
    key = str(uuid4())
    run = client.post(
        f"/api/v1/versions/{version['id']}/analyses",
        json=body,
        headers={**headers, "Idempotency-Key": key},
    )
    assert run.status_code == 202, run.text
    assert run.json()["plan"]["content"]["semantic_ref"] == ref
    draft = context["editable"]
    draft["dataset_description"] = "Otra revisión"
    assert save(client, headers, table, draft, 1).json()["revision"]["revision"] == 2
    assert process(db, objects)
    detail = client.get(f"/api/v1/executions/{run.json()['id']}").json()
    assert detail["state"] == "succeeded" and detail["plan"]["content"]["semantic_ref"] == ref
    invalid = {**body, "semantic_ref": {**ref, "content_sha256": "0" * 64}}
    assert (
        client.post(
            f"/api/v1/versions/{version['id']}/analyses",
            json=invalid,
            headers={**headers, "Idempotency-Key": str(uuid4())},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/versions/{version['id']}/analyses",
            json={**body, "semantic_ref": None},
            headers={**headers, "Idempotency-Key": key},
        ).status_code
        == 409
    )
    other_version = upload(client, headers, version["project_id"]).json()
    assert process(db, objects)
    other_table = client.get(f"/api/v1/versions/{other_version['id']}/representations").json()[0]
    other_context = client.get(f"/api/v1/representations/{other_table['id']}/understanding").json()
    assert other_context["head"] is None
    wrong_table = {
        **body,
        "table_artifact_id": other_table["id"],
        "table_sha256": other_table["sha256"],
    }
    assert (
        client.post(
            f"/api/v1/versions/{other_version['id']}/analyses",
            json=wrong_table,
            headers={**headers, "Idempotency-Key": str(uuid4())},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "currency",
        "unit",
        "format",
        "tokens",
        "missing_column",
        "duplicate_column",
        "unknown_key",
        "empty_grain",
        "empty_key",
        "forged_review",
    ],
)
def test_invalid_semantic_metadata_rejected_without_writes(
    client: TestClient, db: Session, objects: LocalObjects, invalid: str
) -> None:
    headers, _, table, context = prepared(client, db, objects)
    draft = context["editable"]
    if invalid == "currency":
        draft["columns"][1]["currency"] = "ABC"
    elif invalid == "unit":
        draft["columns"][0]["unit"] = "kg"
    elif invalid == "format":
        draft["columns"][0].update(interpretation_type="string", parse_format="iso_date")
    elif invalid == "tokens":
        draft["columns"][0]["null_policy"] = {"mode": "explicit_tokens", "tokens": []}
    elif invalid == "missing_column":
        draft["columns"].pop()
    elif invalid == "duplicate_column":
        draft["columns"][1]["column_id"] = draft["columns"][0]["column_id"]
    elif invalid == "unknown_key":
        draft["key"]["column_ids"] = [str(uuid4())]
    elif invalid == "empty_grain":
        draft["row_grain"] = {"description": "  ", "review_state": "confirmed"}
    elif invalid == "empty_key":
        draft["key"]["review_state"] = "confirmed"
    elif invalid == "forged_review":
        draft["columns"][0]["review"] = {"origin": "user", "actor_id": str(uuid4())}
    assert save(client, headers, table, draft, 0).status_code == 422
    assert db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) == 0
    assert db.scalar(select(func.count()).select_from(SemanticFamilyRecord)) == 0


def test_semantic_permissions_archive_and_conflict(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers, version, table, context = prepared(client, db, objects)
    first = save(client, headers, table, context["editable"], 0).json()["revision"]
    assert save(client, headers, table, context["editable"], 0).status_code == 409
    assert (
        client.post(
            f"/api/v1/projects/{version['project_id']}/archive",
            json={"expected_revision": 1},
            headers=headers,
        ).status_code
        == 200
    )
    assert save(client, headers, table, context["editable"], 1).status_code == 409
    assert client.get(f"/api/v1/representations/{table['id']}/understanding").status_code == 200
    other = account(client)
    for suffix in ["understanding", "semantic-contracts"]:
        assert client.get(f"/api/v1/representations/{table['id']}/{suffix}").status_code == 404
    assert client.get(f"/api/v1/semantic-contracts/{first['id']}").status_code == 404
    assert save(client, other, table, context["editable"], 1).status_code == 404


def test_semantic_saves_are_serialized_with_idempotent_replay(
    committed_engine: Engine, tmp_path: Path
) -> None:
    objects = LocalObjects(tmp_path / "semantic_objects")
    owner = uuid4()
    with Session(committed_engine, expire_on_commit=False) as db:
        db.add(
            UserRecord(
                id=owner,
                email="semantic-concurrency@example.com",
                name="Semantic",
                password_hash="not-an-account",
            )
        )
        db.commit()
        project_record = ProjectService(SQLProjectRepository(db, str(uuid4()))).create(
            owner, "Semantic concurrency", "", None
        )
        version = make_ingestion(db, objects).submit(
            owner, project_record.id, "test.csv", CSV, ",", uuid4(), str(uuid4())
        )
        assert make_runner(db, objects).run_once()
        from dataflow.bootstrap.services import make_executions

        table = next(
            a
            for a in make_executions(db).artifacts(owner, version.execution_id)
            if a.kind == "table"
        )
        draft = make_semantics(db, objects).context(owner, table.id).editable
    barrier = Barrier(2)

    def concurrent_save(key: UUID):
        with Session(committed_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            try:
                return make_semantics(db, objects).save(
                    owner, table.id, table.content.sha256, 0, draft, key, str(uuid4())
                )
            except ApplicationError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(concurrent_save, uuid4()) for _ in range(2)]
        values = [future.result(timeout=30) for future in futures]
    assert (
        sum(isinstance(value, str) and value == "SEMANTIC_REVISION_CONFLICT" for value in values)
        == 1
    )
    with Session(committed_engine) as db:
        assert db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) == 1
        assert db.scalar(select(func.count()).select_from(SemanticSaveRequest)) == 1
    barrier = Barrier(2)
    same_key = uuid4()
    changed_draft = draft.model_copy(
        update={"dataset_description": "Guardado concurrente idempotente"}
    )

    def replay_save():
        with Session(committed_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            return make_semantics(db, objects).save(
                owner, table.id, table.content.sha256, 1, changed_draft, same_key, str(uuid4())
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(replay_save) for _ in range(2)]
        replayed = [future.result(timeout=30) for future in futures]
    assert replayed[0].revision.id == replayed[1].revision.id
    with Session(committed_engine) as db:
        assert db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) == 2
        assert db.scalar(select(func.count()).select_from(SemanticSaveRequest)) == 2
