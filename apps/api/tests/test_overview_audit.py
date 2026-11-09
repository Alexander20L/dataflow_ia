"""Explicación independiente sobre un perfil inmutable, sin llamadas externas (C2, cargas
anteriores a analysis-v12)."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap import services
from dataflow.bootstrap.ai import configured
from dataflow.bootstrap.overview_audit import OverviewInput
from dataflow.bootstrap.provenance import environment_snapshot
from dataflow.bootstrap.services import make_runner
from dataflow.integrations.ai import AIProviderError, FakeProvider
from dataflow.modules.copilot.infrastructure import AICallRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import SQLExecutionRepository
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError


@pytest.fixture(autouse=True)
def catalog_v11(monkeypatch: pytest.MonkeyPatch) -> None:
    """La explicación del dashboard (C2) se conserva para cargas anteriores a analysis-v12; desde
    la Fase 16 las cargas con hallazgos se explican en la investigación."""
    original = services.processing_config
    monkeypatch.setattr(
        services,
        "processing_config",
        lambda: original().model_copy(update={"operation_catalog": "analysis-v11"}),
    )


@pytest.mark.parametrize("provider", ["fake", "disabled"])
def test_automatic_audit_is_saved_separately_and_reads_do_not_call_ai(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", provider)
    headers = account(client)
    pid = project(client, headers)
    original = b"region,importe,secreto\nNorte,10,NO_ENVIAR\nSur,20,PRIVADO\n"
    version = upload(client, headers, pid, original).json()
    runner = make_runner(db, objects)
    assert runner.run_once()
    endpoint = f"/api/v1/versions/{version['id']}/overview-audit"
    diagnostic = client.get(f"/api/v1/versions/{version['id']}/diagnostic").json()
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    if provider == "disabled":
        assert response.json()["state"] == "unavailable"
        assert not runner.run_once()
        return
    assert response.json()["state"] == "queued"
    assert runner.run_once()
    response = client.get(endpoint)
    assert response.json()["state"] == "ready", response.text
    audit = response.json()["audit"]
    assert audit["content"]["resumen_ejecutivo"]
    assert len(audit["content"]["recomendaciones"]) == 2
    assert audit["producer_execution_id"] != response.json()["execution_id"]
    assert all(
        s["execution_id"] == audit["producer_execution_id"]
        for s in audit["content"]["resumen_ejecutivo"]
        if s["kind"] == "evidence"
    )
    assert "NO_ENVIAR" not in response.text
    assert "PRIVADO" not in response.text
    assert client.get(endpoint).json() == response.json()
    assert not runner.run_once()
    assert (
        db.scalar(
            select(func.count())
            .select_from(AICallRecord)
            .where(AICallRecord.task == "overview_audit")
        )
        == 1
    )
    assert client.get(f"/api/v1/versions/{version['id']}/diagnostic").json() == diagnostic
    assert client.get(f"/api/v1/versions/{version['id']}/original").content == original
    evidence = audit["evidence"][0]
    evidence_url = endpoint + "/evidence/" + evidence["id"]
    assert client.get(evidence_url).json() == evidence
    assert client.get(endpoint + "/evidence/inventada").status_code == 404
    account(client)
    assert client.get(endpoint).status_code == 404
    assert client.get(evidence_url).status_code == 404


@pytest.mark.parametrize("failure", ["provider", "reference", "budget", "numbers"])
def test_ai_failures_never_invalidate_dashboard(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    _, config = configured()
    if failure == "budget":
        config = replace(config, user_daily_tokens=0)
    output = {
        "resumen_ejecutivo": "Hay 999 registros."
        if failure == "numbers"
        else "{{evidence:inventada}}",
        "alertas_criticas": [],
        "recomendaciones": ["Revisar cobertura.", "Conservar el original."],
    }
    provider = FakeProvider(
        script=[AIProviderError("AI_UNAVAILABLE", "Caído")] if failure == "provider" else [output]
    )
    monkeypatch.setattr(services, "configured", lambda *_, **__: (provider, config))
    headers = account(client)
    pid = project(client, headers)
    version = upload(client, headers, pid, b"valor,nota\n10,NO_ENVIAR\n20,PRIVADO\n").json()
    runner = make_runner(db, objects)
    assert runner.run_once()
    assert runner.run_once()
    endpoint = f"/api/v1/versions/{version['id']}/overview-audit"
    result = client.get(endpoint).json()
    if failure == "budget":
        assert result["state"] == "unavailable"
        assert result["reason"] == "AI_BUDGET_EXCEEDED"
        assert not provider.requests
    else:
        assert len(provider.requests) == 1
        context = str(provider.requests[0].context)
        assert "NO_ENVIAR" not in context and "PRIVADO" not in context
        assert "table_detail" not in context and "examples" not in context
        assert result["state"] == ("ready" if failure == "numbers" else "failed")
        if failure == "numbers":
            assert result["audit"]["content"]["unverified_numbers"] == 1
            assert "999" not in str(result["audit"]["content"])
    assert not runner.run_once()
    assert client.get(f"/api/v1/versions/{version['id']}/diagnostic").status_code == 200


@pytest.mark.parametrize(
    "field", ["producer_execution_id", "artifact_sha256", "version_content_sha256", "version_id"]
)
def test_audit_refuses_a_different_source_snapshot(
    client: TestClient,
    db: Session,
    objects: LocalObjects,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    headers = account(client)
    pid = project(client, headers)
    upload(client, headers, pid, b"valor\n10\n20\n")
    assert make_runner(db, objects).run_once()
    datasets, executions = services.make_datasets(db), services.make_executions(db)
    lease = SQLExecutionRepository(db, datasets).claim({"overview_audit"}, environment_snapshot())
    assert lease and lease.execution.plan
    resolver = OverviewInput(datasets, executions, ProjectPermissions(db))
    assert resolver.prepare(lease).kind == "overview"
    content = deepcopy(lease.execution.plan.content)
    content["input"][field] = "00000000-0000-0000-0000-000000000000"
    wrong = replace(
        lease,
        execution=replace(lease.execution, plan=replace(lease.execution.plan, content=content)),
    )
    with pytest.raises(ApplicationError, match="no coincide"):
        resolver.prepare(wrong)
