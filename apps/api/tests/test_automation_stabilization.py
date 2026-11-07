"""Regresiones del pipeline antes del nuevo recorrido automático sin formularios."""

from copy import deepcopy
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from dataflow.modules.automation.pipeline import PipelineService
from dataflow.modules.automation.pipeline_contracts import (
    MatchResult,
    PipelinePort,
    PipelineRun,
    RunRepository,
)
from dataflow.modules.automation.pipeline_infrastructure import SQLRunRepository
from dataflow.platform.transactions import UnitOfWork


def pipeline_run(step: str) -> PipelineRun:
    return PipelineRun(
        id=uuid4(),
        owner_id=uuid4(),
        project_id=uuid4(),
        version_id=uuid4(),
        policy_revision_id=uuid4(),
        state="running",
        step=step,
        result_version_id=uuid4(),
        mapping_revision_id=uuid4(),
    )


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_unsuccessful_query_never_advances_to_dashboard_publication(state: str) -> None:
    runs = create_autospec(RunRepository, instance=True)
    port = create_autospec(PipelinePort, instance=True)
    service = PipelineService(runs, port, create_autospec(UnitOfWork, instance=True))
    run = pipeline_run("analyze")
    execution = uuid4()
    runs.analysis.return_value = {"queries": [{"execution_id": str(execution)}]}
    port.execution_state.return_value = (state, "QUERY_ERROR")

    service.step(run)

    assert run.step == "analyze"
    assert run.state == "needs_review"
    expected = "EXECUTION_CANCELLED" if state == "cancelled" else "ANALYSIS_FAILED"
    assert run.reasons[0]["code"] == expected
    assert run.reasons[0]["measured"] == "QUERY_ERROR"
    port.publish_dashboard.assert_not_called()


@pytest.mark.parametrize("state", ["queued", "running", "succeeded"])
def test_query_only_advances_when_succeeded(state: str) -> None:
    runs = create_autospec(RunRepository, instance=True)
    port = create_autospec(PipelinePort, instance=True)
    service = PipelineService(runs, port, create_autospec(UnitOfWork, instance=True))
    run = pipeline_run("analyze")
    runs.analysis.return_value = {"queries": [{"execution_id": str(uuid4())}]}
    port.execution_state.return_value = (state, None)

    service.step(run)

    assert run.state == "running"
    assert run.step == ("publish" if state == "succeeded" else "analyze")


def test_no_cleaning_still_evaluates_quality_rules_on_original() -> None:
    runs = create_autospec(RunRepository, instance=True)
    port = create_autospec(PipelinePort, instance=True)
    service = PipelineService(runs, port, create_autospec(UnitOfWork, instance=True))
    run = pipeline_run("propose")
    artifact, ruleset, execution = uuid4(), uuid4(), uuid4()
    port.table_of.return_value = (artifact, "a" * 64)
    port.mapping_match.return_value = MatchResult("none", None, [], [])
    port.proposal.return_value = ([], None)
    port.evaluate_rules.return_value = True
    port.applicable_ruleset.return_value = (ruleset, "b" * 64)
    port.start_rules.return_value = execution
    port.execution_state.return_value = ("succeeded", None)

    service.step(run)

    assert run.step == "quality_rules"
    assert run.result_version_id == run.version_id
    assert run.derived_version_id is None
    service.step(run)
    port.start_rules.assert_called_once()
    assert run.rules_execution_id == execution
    assert run.step == "select"
    port.start_apply.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_dashboard_publication_retries_identical_target_after_crash(existing: bool) -> None:
    runs = create_autospec(RunRepository, instance=True)
    port = create_autospec(PipelinePort, instance=True)
    uow = create_autospec(UnitOfWork, instance=True)
    service = PipelineService(runs, port, uow)
    run = pipeline_run("publish")
    family, revision = uuid4(), uuid4()
    stored = {"template": "sales@1", "queries": []}
    runs.analysis.side_effect = lambda _: deepcopy(stored)

    def save_analysis(*args: object) -> None:
        stored.clear()
        stored.update(deepcopy(args[2]))  # type: ignore[arg-type]

    runs.save_analysis.side_effect = save_analysis
    runs.dashboard_family.return_value = family if existing else None
    port.dashboard_head_revision.return_value = 3
    port.publish_dashboard.side_effect = [RuntimeError("worker interrupted"), (family, revision)]

    with pytest.raises(RuntimeError, match="worker interrupted"):
        service.step(run)
    uow.commit.assert_called_once()  # El destino quedó guardado ANTES de publicar.
    first_args = deepcopy(port.publish_dashboard.call_args.args)
    first_kwargs = deepcopy(port.publish_dashboard.call_args.kwargs)
    runs.dashboard_family.return_value = uuid4()  # otra publicación ya cambió el proyecto
    port.dashboard_head_revision.return_value = 4

    service.step(run)

    assert port.publish_dashboard.call_args.args == first_args
    assert port.publish_dashboard.call_args.kwargs == first_kwargs
    assert runs.dashboard_family.call_count == 1
    assert run.state == "completed"
    assert stored["dashboard_revision_id"] == str(revision)


def test_run_lock_uses_pinned_connection_across_commits_and_rollbacks(
    committed_engine: Engine,
) -> None:
    run = uuid4()
    with Session(committed_engine) as first, Session(committed_engine) as second:
        repository = SQLRunRepository(first)
        competitor = SQLRunRepository(second)
        assert repository.try_lock(run)
        try:
            # La conexión de trabajo no posee el lock: sus commits/rollbacks pueden devolverla
            # al pool sin perder la exclusión. El lock está en otra conexión fijada.
            assert (
                first.scalar(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype='advisory' "
                        "AND pid=pg_backend_pid()"
                    )
                )
                == 0
            )
            first.commit()
            assert not competitor.try_lock(run)
            first.execute(text("SELECT 1"))
            first.rollback()
            assert not competitor.try_lock(run)
            # No incrementar el contador reentrante de PostgreSQL por una adquisición repetida.
            assert not repository.try_lock(run)
        finally:
            repository.unlock(run)
        assert competitor.try_lock(run)
        competitor.unlock(run)
        assert repository.try_lock(run)
        repository.unlock(run)
