import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project

from dataflow.bootstrap.operations import DESCRIPTORS, OperationCatalog, OperationRegistry
from dataflow.bootstrap.services import (
    make_datasets,
    make_executions,
    make_operations,
    make_runner,
    processing_config,
)
from dataflow.modules.cleaning.engine import IsolatedCleaner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.application import ExecutionRunner
from dataflow.modules.executions.contracts import PlanRevision, PlanStepSpec, StepResult
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.plans import build_plan
from dataflow.modules.planning.contracts import PlanDraft, PlanningFacts
from dataflow.modules.planning.domain import validate_plan
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase4_regression"
CASES = sorted(path.name.removesuffix(".golden.json") for path in FIXTURES.glob("*.golden.json"))


def owner_id(client: TestClient) -> UUID:
    return UUID(client.get("/api/v1/auth/me").json()["user"]["id"])


def import_csv(client: TestClient, headers: dict[str, str], name: str, requested: str) -> Any:
    response = client.post(
        f"/api/v1/projects/{project(client, headers)}/imports",
        params={"file_name": f"{name}.csv", "separator": requested},
        content=(FIXTURES / f"{name}.csv").read_bytes(),
        headers={**headers, "Content-Type": "text/csv", "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    return response.json()


def published(db: Session, objects: LocalObjects, owner: UUID, run: UUID) -> dict[str, Any]:
    result = {}
    for artifact in make_executions(db).artifacts(owner, run):
        if artifact.kind in {"profile", "quality"}:
            value = json.loads(objects.read(artifact.content))
            if artifact.kind == "profile":
                # La versión de Polars la fija requirements.lock; se comprueba aparte.
                assert value.pop("polars_version") == pl.__version__
            result[artifact.kind] = value
    return result


def expected(golden: dict[str, Any]) -> dict[str, Any]:
    return {
        kind: {k: v for k, v in value.items() if k != "polars_version"}
        for kind, value in golden.items()
    }


@pytest.mark.parametrize("name", CASES)
def test_step_runner_reproduces_single_process_outputs(
    name: str, client: TestClient, db: Session, objects: LocalObjects
) -> None:
    """Regresión Fase 4: un subproceso por paso publica exactamente lo mismo que el proceso
    único anterior (referencias generadas antes del cambio), incluida la procedencia del perfil
    (separador efectivo y hash del original) tomada del paso de lectura."""
    golden = json.loads((FIXTURES / f"{name}.golden.json").read_text(encoding="utf-8"))
    headers = account(client)
    owner = owner_id(client)
    version = import_csv(client, headers, name, golden["requested_separator"])
    assert make_runner(db, objects).run_once()
    assert published(db, objects, owner, UUID(version["execution_id"])) == expected(
        golden["csv_import"]
    )
    table = next(
        a
        for a in make_executions(db).artifacts(owner, UUID(version["execution_id"]))
        if a.kind == "table"
    )
    runs = {}
    for kind in ["profile_quality", "quality_only"]:
        response = client.post(
            f"/api/v1/versions/{version['id']}/analyses",
            json={
                "table_artifact_id": str(table.id),
                "table_sha256": table.content.sha256,
                "analysis_kind": kind,
            },
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 202, response.text
        assert make_runner(db, objects).run_once()
        runs[kind] = UUID(response.json()["id"])
    assert published(db, objects, owner, runs["profile_quality"]) == expected(
        golden["table_profile_quality"]
    )
    assert published(db, objects, owner, runs["quality_only"]) == expected(
        golden["table_quality_only"]
    )
    # Adaptador: los planes 0.5 existentes siguen siendo válidos en el catálogo vigente.
    for run in make_executions(db).for_version(owner, UUID(version["id"])):
        assert run.state == "succeeded" and run.plan
        content = run.plan.content
        facts = PlanningFacts(input_kind=content["input"]["kind"], column_ids=frozenset())
        draft = PlanDraft(steps=content["steps"])
        assert validate_plan(draft, OperationCatalog(), facts) == []


def enqueue_plan(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    steps: list[dict[str, Any]] | None = None,
) -> tuple[UUID, UUID]:
    headers = account(client)
    owner = owner_id(client)
    version = import_csv(client, headers, CASES[0], "auto")
    assert make_runner(db, objects).run_once()
    table = next(
        a
        for a in make_executions(db).artifacts(owner, UUID(version["execution_id"]))
        if a.kind == "table"
    )
    dataset_version = make_datasets(db).get(owner, UUID(version["id"]))
    plan = build_plan(owner, dataset_version, processing_config(), table=table)
    if steps is not None:
        content = {**plan.content, "steps": steps}
        plan = PlanRevision(
            uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
        )
    run = make_executions(db).enqueue(
        owner,
        dataset_version.project_id,
        dataset_version.id,
        "plan",
        uuid4(),
        "c" * 64,
        plan,
        str(uuid4()),
        table.id,
        table.content.sha256,
    )
    db.commit()
    return owner, run.id


def test_worker_without_plan_kind_does_not_claim_plan_runs(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    owner, run = enqueue_plan(client, db, objects)
    legacy_worker = make_runner(db, objects, kinds={"csv_import", "table_analysis"})
    assert legacy_worker.run_once() is False
    assert make_executions(db).get(owner, run).state == "queued"
    assert make_runner(db, objects).run_once()
    assert make_executions(db).get(owner, run).state == "succeeded"
    kinds = sorted(a.kind for a in make_executions(db).artifacts(owner, run))
    assert kinds == ["profile", "quality"]


def test_unknown_operation_fails_without_publishing(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    owner, run = enqueue_plan(
        client,
        db,
        objects,
        [
            {
                "id": "trim",
                "operation": "cleaning.deduplicate",
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {},
            }
        ],
    )
    assert make_runner(db, objects).run_once()
    result = make_executions(db).get(owner, run)
    assert result.state == "failed" and result.error_code == "UNSUPPORTED_OPERATION"
    assert make_executions(db).artifacts(owner, run) == []


def test_steps_share_one_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("dataflow.modules.executions.application.time.monotonic", lambda: clock.now)

    class Step:
        output_kind = "quality"

        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def compute(self, lease: Any, step: Any, source: Any, timeout: float) -> StepResult:
            self.timeouts.append(timeout)
            clock.now += 4
            return StepResult([])

    executor = Step()
    lease: Any = SimpleNamespace(
        execution=SimpleNamespace(plan=SimpleNamespace(config=SimpleNamespace(timeout_seconds=10)))
    )
    steps: Any = [
        (PlanStepSpec(f"s{i}", "quality.evaluate", 1, None, {}), executor) for i in range(3)
    ]
    ExecutionRunner.compute(lease, steps, SimpleNamespace())
    assert executor.timeouts == [10, 6, 2]
    with pytest.raises(ApplicationError, match="tiempo permitido") as error:
        ExecutionRunner.compute(lease, steps + steps[:1], SimpleNamespace())
    assert error.value.code == "PROCESSING_TIMEOUT"


def test_registry_pairs_every_descriptor_with_a_matching_executor(tmp_path: Path) -> None:
    analyzer = IsolatedAnalyzer(tmp_path, 5, 10, 10)
    registry = make_operations(LocalObjects(tmp_path), analyzer, IsolatedCleaner(tmp_path))
    assert [d.key for d in registry.descriptors()] == [d.key for d in DESCRIPTORS]
    assert all(registry.executor(d.name, d.version) for d in DESCRIPTORS)
    assert registry.executor("cleaning.deduplicate", 1) is None
    executors = dict(registry.executors)
    with pytest.raises(ValueError, match="incompleto"):
        OperationRegistry({k: v for k, v in executors.items() if k != "quality.evaluate@1"})
    executors["quality.evaluate@1"] = executors["understanding.profile@1"]
    with pytest.raises(ValueError, match="incoherente"):
        OperationRegistry(executors)
