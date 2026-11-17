import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_datasets, make_executions, make_ingestion, make_runner
from dataflow.modules.cleaning.repository import CleaningApprovalRecord
from dataflow.modules.datasets.infrastructure import (
    DatasetDefaultRecord,
    VersionLineageRecord,
    VersionRecord,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ArtifactRecord, AttemptRecord

CSV = (Path(__file__).resolve().parents[3] / "examples" / "ventas_calidad.csv").read_bytes()


class Scenario:
    def __init__(self, client: TestClient, db: Session, objects: LocalObjects) -> None:
        self.client, self.db, self.objects = client, db, objects
        self.headers = account(client)
        self.owner = UUID(client.get("/api/v1/auth/me").json()["user"]["id"])
        self.project_id = project(client, self.headers)
        self.version = upload(client, self.headers, self.project_id, CSV).json()
        assert make_runner(db, objects).run_once()
        self.table = client.get(f"/api/v1/versions/{self.version['id']}/representations").json()[0]
        self.columns = {c["name"]: c["id"] for c in self.table["columns"]}

    def plan(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/plans",
            json={
                "table_artifact_id": self.table["id"],
                "table_sha256": self.table["sha256"],
                "steps": steps,
            },
            headers={**self.headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        plan: dict[str, Any] = response.json()
        assert plan["validation"]["valid"], plan["validation"]
        return plan

    def trim_plan(self) -> dict[str, Any]:
        return self.plan(
            [
                {
                    "id": "trim",
                    "operation": "cleaning.trim_whitespace",
                    "version": 1,
                    "input": {"kind": "input"},
                    "parameters": {"column_ids": [self.columns["importe"]]},
                }
            ]
        )

    def enqueue(self, plan: dict[str, Any], kind: str, key: UUID | None = None) -> UUID:
        executions = make_executions(self.db)
        run = executions.enqueue_existing_plan(
            self.owner,
            UUID(self.project_id),
            UUID(self.version["id"]),
            key or uuid4(),
            hashlib.sha256(str(uuid4()).encode()).hexdigest(),
            executions.plan_revision(self.owner, UUID(plan["id"])),
            str(uuid4()),
            kind,  # type: ignore[arg-type]
        )
        self.db.commit()
        return run.id

    def run(self, run_id: UUID, **kwargs: Any) -> Any:
        assert make_runner(self.db, self.objects, **kwargs).run_once()
        return make_executions(self.db).get(self.owner, run_id)

    def effect(self, run_id: UUID) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        artifacts = {a.kind: a for a in make_executions(self.db).artifacts(self.owner, run_id)}
        return (
            json.loads(self.objects.read(artifacts["effect"].content)),
            json.loads(self.objects.read(artifacts["effect_samples"].content)),
        )

    def approve(self, plan: dict[str, Any], preview: UUID, effect_sha256: str) -> UUID:
        approval = uuid4()
        self.db.add(
            CleaningApprovalRecord(
                id=approval,
                plan_revision_id=UUID(plan["id"]),
                preview_execution_id=preview,
                effect_sha256=effect_sha256,
                input_artifact_sha256=self.table["sha256"],
                config_sha256="a" * 64,
                environment_sha256="b" * 64,
                approved_by=self.owner,
                approved_at=datetime.now(UTC),
            )
        )
        self.db.commit()
        return approval

    def previewed_and_approved(self) -> tuple[dict[str, Any], UUID, str]:
        plan = self.trim_plan()
        preview = self.enqueue(plan, "cleaning_preview")
        assert self.run(preview).state == "succeeded"
        effect, _ = self.effect(preview)
        return plan, self.approve(plan, preview, effect["effect_sha256"]), effect["effect_sha256"]

    def derived_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(VersionRecord)
                .where(VersionRecord.kind == "derived")
            )
            or 0
        )


@pytest.fixture
def scenario(client: TestClient, db: Session, objects: LocalObjects) -> Scenario:
    return Scenario(client, db, objects)


def test_preview_is_exact_deterministic_and_publishes_no_table(scenario: Scenario) -> None:
    plan = scenario.trim_plan()
    first, second = (scenario.enqueue(plan, "cleaning_preview") for _ in range(2))
    assert scenario.run(first).state == "succeeded"
    assert scenario.run(second).state == "succeeded"
    effect, samples = scenario.effect(first)
    assert effect["effect_sha256"] == scenario.effect(second)[0]["effect_sha256"]
    manifest = effect["manifest"]
    assert manifest["counts"] == {
        "input_rows": 6,
        "output_rows": 6,
        "excluded_rows": 0,
        "modified_rows": 1,
        "modified_cells": 1,
        "created_nulls": 1,
    }
    assert manifest["plan"] == {"revision_id": plan["id"], "content_sha256": plan["content_sha256"]}
    assert manifest["input"]["artifact_sha256"] == scenario.table["sha256"]
    importe = scenario.columns["importe"]
    assert samples == [
        {
            "source_row": 5,
            "change": "modified",
            "column_ids": [importe],
            "before": {importe: " "},
            "after": {importe: None},
        }
    ]
    kinds = {a.kind for a in make_executions(scenario.db).artifacts(scenario.owner, first)}
    assert kinds == {"effect", "effect_samples"}
    # La vista previa no crea representaciones, versiones ni cambia la predeterminada.
    tables = scenario.client.get(f"/api/v1/versions/{scenario.version['id']}/representations")
    assert [t["id"] for t in tables.json()] == [scenario.table["id"]]
    assert scenario.derived_count() == 0


def test_apply_publishes_derived_version_with_lineage_and_new_diagnostic(
    scenario: Scenario,
) -> None:
    db, owner = scenario.db, scenario.owner
    v1 = UUID(scenario.version["id"])
    v1_diagnostic = make_ingestion(db, scenario.objects).diagnostic(owner, v1)
    plan, approval, effect_sha = scenario.previewed_and_approved()
    apply = scenario.enqueue(plan, "cleaning_apply", approval)
    run = scenario.run(apply)
    assert run.state == "succeeded", (run.error_code, run.error_message)

    lineage = db.scalar(select(VersionLineageRecord))
    assert lineage and lineage.parent_version_id == v1 and lineage.producer_execution_id == apply
    v2 = make_datasets(db).get(owner, lineage.version_id)
    assert v2.kind == "derived" and v2.number == 2
    artifacts = {a.kind: a for a in make_executions(db).artifacts(owner, apply)}
    assert set(artifacts) == {"effect", "effect_samples", "table", "row_lineage"}
    table, rows = artifacts["table"], artifacts["row_lineage"]
    assert table.version_id == rows.version_id == v2.id and artifacts["effect"].version_id == v1
    assert v2.content.sha256 == table.content.sha256  # el contenido de la derivada es su Parquet
    assert table.columns == scenario.table["columns"]  # mismas columnas (IDs) que el origen
    assert json.loads(scenario.objects.read(artifacts["effect"].content))["effect_sha256"] == (
        effect_sha
    )
    lineage_frame = pl.read_parquet(io.BytesIO(scenario.objects.read(rows.content)))
    assert lineage_frame.get_column("source_row").to_list() == [1, 2, 3, 4, 5, 6]
    derived = pl.read_parquet(io.BytesIO(scenario.objects.read(table.content)))
    assert derived.get_column("importe").to_list() == [
        "100.50",
        None,
        "80.00",
        "100.50",
        None,
        "120.25",
    ]
    assert derived.get_column("id").to_list()[0] == "001"  # ceros iniciales intactos

    # Perfil y calidad de v2 quedan en cola; la versión no pasa a ser la predeterminada.
    versions = scenario.client.get(f"/api/v1/projects/{scenario.project_id}/versions").json()
    assert [(item["number"], item["state"]) for item in versions["items"]] == [
        (2, "queued"),
        (1, "succeeded"),
    ]
    default = db.scalar(select(DatasetDefaultRecord))
    assert default and default.version_id == v1
    analysis = make_executions(db).for_version(owner, v2.id)[0]
    assert analysis.kind == "table_analysis" and analysis.input_artifact_id == table.id
    assert scenario.run(analysis.id).state == "succeeded"
    diagnostic = make_ingestion(db, scenario.objects).diagnostic(owner, v2.id)
    assert diagnostic.quality.completeness_percent == 93.33
    assert diagnostic.quality.missing_cells == 2 and diagnostic.quality.whitespace_cells == 0
    assert diagnostic.profile.source_sha256 == v2.content.sha256
    # v1: diagnóstico y original intactos.
    assert make_ingestion(db, scenario.objects).diagnostic(owner, v1) == v1_diagnostic
    assert v1_diagnostic.quality.completeness_percent == 96.67
    name, content = make_ingestion(db, scenario.objects).original(owner, v1)
    assert content == CSV and hashlib.sha256(content).hexdigest() == scenario.version["sha256"]
    assert db.scalar(select(DatasetDefaultRecord)).version_id == v1  # type: ignore[union-attr]


def assert_nothing_published(scenario: Scenario, run: UUID) -> None:
    assert scenario.derived_count() == 0
    assert scenario.db.scalar(select(func.count()).select_from(VersionLineageRecord)) == 0
    assert (
        scenario.db.scalar(
            select(func.count())
            .select_from(ArtifactRecord)
            .where(ArtifactRecord.execution_id == run)
        )
        == 0
    )


def test_effect_different_from_approved_fails_and_publishes_nothing(scenario: Scenario) -> None:
    plan = scenario.trim_plan()
    preview = scenario.enqueue(plan, "cleaning_preview")
    assert scenario.run(preview).state == "succeeded"
    approval = scenario.approve(plan, preview, "0" * 64)
    apply = scenario.enqueue(plan, "cleaning_apply", approval)
    result = scenario.run(apply)
    assert result.state == "failed" and result.error_code == "PREVIEW_EFFECT_MISMATCH"
    assert "vista previa nueva" in (result.error_message or "")
    assert_nothing_published(scenario, apply)


def intercept(scenario: Scenario, monkeypatch: pytest.MonkeyPatch, action: Any) -> Any:
    """Runner cuya aplicación ejecuta `action` tras calcular (antes de publicar)."""
    runner = make_runner(scenario.db, scenario.objects)
    finalizer = runner.finalizers["cleaning_apply"]
    original = finalizer.finalize

    def finalize(*args: Any) -> Any:
        outputs = original(*args)
        action(args[0])
        return outputs

    monkeypatch.setattr(finalizer, "finalize", finalize)
    return runner


def test_cancel_during_apply_publishes_nothing(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, approval, _ = scenario.previewed_and_approved()
    apply = scenario.enqueue(plan, "cleaning_apply", approval)

    def cancel(lease: Any) -> None:
        make_executions(scenario.db).cancel(scenario.owner, lease.execution_id)

    assert intercept(scenario, monkeypatch, cancel).run_once()
    assert make_executions(scenario.db).get(scenario.owner, apply).state == "cancelled"
    assert_nothing_published(scenario, apply)


def test_expired_attempt_finishing_late_publishes_nothing_and_retry_publishes_once(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, approval, _ = scenario.previewed_and_approved()
    apply = scenario.enqueue(plan, "cleaning_apply", approval)

    def expire(lease: Any) -> None:
        scenario.db.execute(
            update(AttemptRecord)
            .where(AttemptRecord.id == lease.attempt_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        scenario.db.commit()

    assert intercept(scenario, monkeypatch, expire).run_once()
    assert_nothing_published(scenario, apply)
    # Otro worker recupera la lease vencida, recalcula el mismo efecto y publica una sola vez.
    result = scenario.run(apply)
    assert result.state == "succeeded" and result.attempts == 2
    assert scenario.derived_count() == 1


def test_revocation_before_publication_publishes_nothing(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, approval, _ = scenario.previewed_and_approved()
    apply = scenario.enqueue(plan, "cleaning_apply", approval)

    def revoke(_: Any) -> None:
        scenario.db.execute(
            update(CleaningApprovalRecord)
            .where(CleaningApprovalRecord.id == approval)
            .values(revoked_at=datetime.now(UTC))
        )
        scenario.db.commit()

    assert intercept(scenario, monkeypatch, revoke).run_once()
    result = make_executions(scenario.db).get(scenario.owner, apply)
    assert result.state == "failed" and result.error_code == "APPROVAL_REVOKED"
    assert_nothing_published(scenario, apply)


def test_apply_without_approval_and_plan_runs_with_cleaning_are_rejected(
    scenario: Scenario,
) -> None:
    plan = scenario.trim_plan()
    unapproved = scenario.enqueue(plan, "cleaning_apply")
    result = scenario.run(unapproved)
    assert result.state == "failed" and result.error_code == "APPROVAL_REQUIRED"
    plain = scenario.enqueue(plan, "plan")
    result = scenario.run(plain)
    assert result.state == "failed" and result.error_code == "APPROVAL_REQUIRED"
    assert_nothing_published(scenario, unapproved)
    assert_nothing_published(scenario, plain)


def test_filter_chain_excludes_rows_and_keeps_order(scenario: Scenario) -> None:
    plan = scenario.plan(
        [
            {
                "id": "trim",
                "operation": "cleaning.trim_whitespace",
                "version": 1,
                "input": {"kind": "input"},
                "parameters": {"column_ids": [scenario.columns["importe"]]},
            },
            {
                "id": "drop",
                "operation": "cleaning.filter_rows",
                "version": 1,
                "input": {"kind": "step", "step_id": "trim"},
                "parameters": {
                    "column_ids": [scenario.columns["importe"]],
                    "predicate": "is_null",
                },
            },
        ]
    )
    preview = scenario.enqueue(plan, "cleaning_preview")
    assert scenario.run(preview).state == "succeeded"
    effect, samples = scenario.effect(preview)
    assert effect["manifest"]["counts"] == {
        "input_rows": 6,
        "output_rows": 4,
        "excluded_rows": 2,  # fila 2 (nula) y fila 5 (espacio → nula → excluida)
        "modified_rows": 0,
        "modified_cells": 0,
        "created_nulls": 0,
    }
    assert [(s["source_row"], s["change"]) for s in samples] == [(2, "excluded"), (5, "excluded")]
    approval = scenario.approve(plan, preview, effect["effect_sha256"])
    apply = scenario.enqueue(plan, "cleaning_apply", approval)
    assert scenario.run(apply).state == "succeeded"
    table = next(
        a
        for a in make_executions(scenario.db).artifacts(scenario.owner, apply)
        if a.kind == "table"
    )
    derived = pl.read_parquet(io.BytesIO(scenario.objects.read(table.content)))
    assert derived.get_column("id").to_list() == ["001", "003", "001", "005"]
