"""Investigación automática (Fase 16, ADR-033): une la cola de ejecuciones, el motor de
analytics, la IA y el módulo `investigation` sin acoplarlos entre sí.

Tras publicar una carga con `analytics.automatic@1` se encola un trabajo `investigation` cuyo
input fija el análisis y la tabla de esa carga (ids y hashes). Siempre se ejecuta: sin IA hace
los seguimientos por reglas. Sustituye, para esas cargas, a la explicación del dashboard (C2).
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.integrations.ai import AIProvider
from dataflow.modules.analytics.contracts import (
    AutomaticAnalysis,
    AutomaticEvidence,
    AutomaticScope,
    FollowUpQuery,
    FollowUpResult,
)
from dataflow.modules.analytics.steps import FollowUpComputer
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.contracts import CallRecord
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.copilot.investigation import (
    FINDINGS_PROMPT_ID,
    FINDINGS_PROMPT_VERSION,
    PROPOSAL_PROMPT_ID,
    PROPOSAL_PROMPT_VERSION,
    Figure,
    explain_findings,
    propose,
    wrap_proposal_context,
)
from dataflow.modules.copilot.overview import OverviewCall
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.executions.public import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Executions,
    Lease,
    PlanRevision,
    PlanStepSpec,
    ProcessingConfig,
    StepInput,
    StepResult,
)
from dataflow.modules.investigation.contracts import (
    ExplainedFigure,
    ExplanationReply,
    Investigation,
    InvestigationLimits,
    InvestigationScope,
    InvestigationView,
    ModelCall,
    ProposalContext,
    ProposalReply,
    RawProposal,
)
from dataflow.modules.investigation.public import Investigator
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.platform.canonical import digest
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

STEP = "investigation.investigate"


def limits() -> InvestigationLimits:
    settings = get_settings()
    return InvestigationLimits(
        max_iterations=settings.investigation_max_iterations,
        max_ai_calls=settings.investigation_max_ai_calls,
        max_seconds=settings.investigation_max_seconds,
        max_cost_usd=str(settings.investigation_max_cost_usd),
    )


def enqueue_investigation(
    executions: Executions,
    lease: Lease,
    analysis: Artifact,
    table: Artifact,
    config: ProcessingConfig,
) -> None:
    key = uuid5(lease.execution_id, "investigation@1")
    fingerprint = digest(
        "investigation_request",
        {
            "analysis_id": str(analysis.id),
            "analysis_sha256": analysis.content.sha256,
            "table_id": str(table.id),
            "table_sha256": table.content.sha256,
            "operation": f"{STEP}@1",
        },
    )
    if executions.find_request(
        lease.owner_id, lease.execution.project_id, "investigation", key, fingerprint
    ):
        return
    assert lease.execution.plan
    content = {
        "objective": None,
        "input": {
            "kind": "automatic",
            "alias": "source",
            "version_id": str(lease.version_id),
            "version_content_sha256": lease.execution.plan.content["input"][
                "version_content_sha256"
            ],
            "artifact_id": str(analysis.id),
            "artifact_sha256": analysis.content.sha256,
            "producer_execution_id": str(analysis.execution_id),
            "table_artifact_id": str(table.id),
            "table_key": table.content.key,
            "table_sha256": table.content.sha256,
            "table_byte_size": table.content.byte_size,
        },
        "steps": [
            {
                "id": "investigate",
                "operation": STEP,
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {"limits": limits().model_dump(mode="json")},
            }
        ],
        # Una llamada facturable no se reintenta: un solo intento.
        "config": config.model_copy(update={"max_attempts": 1}).model_dump(),
    }
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), lease.owner_id, datetime.now(UTC)
    )
    executions.enqueue_followup(
        lease.owner_id,
        lease.execution.project_id,
        lease.version_id,
        key,
        fingerprint,
        plan,
        str(lease.execution_id),
        analysis.id,
        analysis.content.sha256,
        kind="investigation",
    )


class InvestigationInput:
    """Comprueba que el análisis y la tabla fijados en el plan son los de la carga."""

    def __init__(
        self, datasets: Datasets, executions: Executions, projects: ProjectPermissions
    ) -> None:
        self.datasets, self.executions, self.projects = datasets, executions, projects

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        self.projects.require(run.owner_id, run.project_id, writable=True)
        version = self.datasets.get(run.owner_id, run.version_id)
        source = run.plan.content["input"]
        analysis = self.executions.artifact(run.owner_id, run.input_artifact_id)
        table = self.executions.artifact(run.owner_id, UUID(source["table_artifact_id"]))
        if (
            analysis.kind != "automatic_analysis"
            or table.kind != "table"
            or analysis.version_id != version.id
            or table.version_id != version.id
            or analysis.execution_id != table.execution_id
            or str(analysis.id) != source.get("artifact_id")
            or str(analysis.execution_id) != source.get("producer_execution_id")
            or str(version.id) != source.get("version_id")
            or version.content.sha256 != source.get("version_content_sha256")
            or analysis.content.sha256 != source.get("artifact_sha256")
            or analysis.content.sha256 != run.input_artifact_sha256
            or table.content.key != source.get("table_key")
            or table.content.sha256 != source.get("table_sha256")
            or table.content.byte_size != source.get("table_byte_size")
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "El análisis fijado para la investigación no coincide.", 409
            )
        return StepInput("automatic", analysis.content, table.content.sha256)


def model_call(
    call: OverviewCall, purpose: str, iteration: int, prompt: tuple[str, str]
) -> ModelCall:
    return ModelCall.model_validate(
        {
            **call.model_dump(mode="json"),
            "purpose": purpose,
            "iteration": iteration,
            "prompt_id": prompt[0],
            "prompt_version": prompt[1],
        }
    )


class AIProposer:
    def __init__(self, provider: AIProvider, max_output_tokens: int) -> None:
        self.provider, self.max_output_tokens = provider, max_output_tokens

    def propose(self, context: ProposalContext) -> ProposalReply:
        wrapped = wrap_proposal_context(
            context.iteration,
            context.measure,
            {str(kind): text for kind, text in context.kinds.items()},
            context.dimensions,
            context.months,
            context.years,
            context.groups,
            [(item.id, item.title, item.statement) for item in context.findings],
            context.done,
            context.max_proposals,
        )
        items, call, error = propose(self.provider, wrapped, self.max_output_tokens)
        return ProposalReply(
            proposals=[
                RawProposal(
                    kind=item.tipo,
                    dimension=item.dimension,
                    month=item.mes,
                    year=item.anio,
                    group=item.grupo,
                    motive=item.motivo,
                )
                for item in items
            ],
            call=model_call(
                call, "proposal", context.iteration, (PROPOSAL_PROMPT_ID, PROPOSAL_PROMPT_VERSION)
            )
            if call
            else None,
            error=error,
        )


class AIExplainer:
    def __init__(self, provider: AIProvider, max_output_tokens: int) -> None:
        self.provider, self.max_output_tokens = provider, max_output_tokens

    def explain(
        self, figures: list[ExplainedFigure], limitations: list[str], iteration: int
    ) -> ExplanationReply:
        state, reason, content, call = explain_findings(
            self.provider,
            [
                Figure(item.evidence_id, item.label, item.value, item.unit, item.execution_id)
                for item in figures
            ],
            limitations,
            self.max_output_tokens,
        )
        return ExplanationReply.model_validate(
            {
                "state": state,
                "reason": reason,
                "content": content,
                "call": model_call(
                    call, "explanation", iteration, (FINDINGS_PROMPT_ID, FINDINGS_PROMPT_VERSION)
                )
                if call
                else None,
            }
        )


class Computed:
    def __init__(
        self,
        computer: FollowUpComputer,
        table: StoredObject,
        scope: AutomaticScope,
        max_rows: int,
        max_columns: int,
    ) -> None:
        self.computer, self.table, self.scope = computer, table, scope
        self.max_rows, self.max_columns = max_rows, max_columns

    def compute(self, queries: list[FollowUpQuery], timeout: float) -> list[FollowUpResult]:
        return self.computer.compute(
            self.table, self.scope, queries, timeout, self.max_rows, self.max_columns
        ).results


class InvestigationStep:
    output_kind: ArtifactKind = "investigation"
    transforms_data = False

    def __init__(self, objects: ObjectStore, computer: FollowUpComputer, copilot: CopilotService):
        self.objects, self.computer, self.copilot = objects, computer, copilot
        self.prepared: dict[UUID, str | None] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        reason = None
        try:
            self.copilot.available(lease.owner_id, lease.execution.project_id)
        except ApplicationError as error:
            reason = (
                error.code
                if error.code != "COPILOT_UNAVAILABLE"
                else (self.copilot.config.unavailable or "disabled")
            )
        self.prepared[lease.attempt_id] = reason

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "automatic" or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó la investigación.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        plan = lease.execution.plan
        assert plan and lease.execution.input_artifact_id
        bounds = InvestigationLimits.model_validate(step.parameters.get("limits", {}))
        analysis = AutomaticAnalysis.model_validate_json(self.objects.read(source.content))
        given = plan.content["input"]
        if analysis.scope.table_sha256 != given["table_sha256"]:
            raise ApplicationError("INPUT_MISMATCH", "El análisis no es el de esta tabla.", 409)
        table = StoredObject(given["table_key"], given["table_sha256"], given["table_byte_size"])
        scope = InvestigationScope(
            execution_id=lease.execution_id,
            version_id=lease.version_id,
            analysis_artifact_id=lease.execution.input_artifact_id,
            analysis_sha256=source.content.sha256,
            analysis_execution_id=analysis.scope.execution_id,
            table_sha256=table.sha256,
        )
        provider = self.copilot.provider
        tokens = self.copilot.config.max_output_tokens
        active = provider is not None and unavailable is None
        investigator = Investigator(
            Computed(
                self.computer,
                table,
                AutomaticScope(
                    execution_id=lease.execution_id,
                    step_id=step.id,
                    version_id=lease.version_id,
                    table_sha256=table.sha256,
                ),
                plan.config.max_rows,
                plan.config.max_columns,
            ),
            AIProposer(provider, tokens) if active and provider else None,
            AIExplainer(provider, tokens) if active and provider else None,
            bounds.model_copy(update={"max_seconds": min(bounds.max_seconds, int(timeout))}),
            time.monotonic,
            unavailable,
        )
        result = investigator.run(analysis, scope)
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        stored = self.objects.put(f"{prefix}/investigation.json", result.model_dump_json().encode())
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "investigation",
                    "investigation",
                    stored,
                    "application/json",
                    len(result.results),
                    len(result.proposals),
                )
            ]
        )


def record_investigation_calls(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    """Registra cada llamada en el consumo de IA (presupuestos durables) al publicar."""
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    result = Investigation.model_validate_json(objects.read(output.content))
    if (
        result.scope.execution_id != lease.execution_id
        or result.scope.analysis_artifact_id != lease.execution.input_artifact_id
        or result.scope.analysis_sha256 != lease.execution.input_artifact_sha256
    ):
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "La investigación no corresponde a su análisis.", 409
        )
    repository = SQLCopilotRepository(db)
    for call in result.calls:
        repository.log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="investigation_proposal" if call.purpose == "proposal" else "findings_audit",
                provider=call.provider,
                model=call.model,
                parameters=dict(call.parameters),
                prompt_id=call.prompt_id,
                prompt_version=call.prompt_version,
                context_sha256=call.context_sha256,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cache_read_tokens=call.cache_read_tokens,
                cache_write_tokens=call.cache_write_tokens,
                cost_usd=Decimal(call.cost_usd) if call.cost_usd is not None else None,
                latency_ms=call.latency_ms,
                outcome=call.outcome,
                validation={
                    "investigation": str(lease.execution_id),
                    "iteration": call.iteration,
                    "explanation_state": result.explanation_state,
                },
                error_code=call.error_code,
            )
        )


class InvestigationAccess:
    """Lectura de la investigación de una versión; nunca recalcula ni llama al proveedor."""

    def __init__(self, datasets: Datasets, executions: Executions, objects: ObjectStore) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects

    def view(self, owner: UUID, version: UUID) -> InvestigationView:
        self.datasets.get(owner, version)
        runs = [
            run
            for run in self.executions.for_version(owner, version)
            if run.kind == "investigation"
        ]
        if not runs:
            raise ApplicationError(
                "INVESTIGATION_NOT_AVAILABLE",
                "Esta versión no tiene investigación automática: se procesó antes de la Fase 16.",
                404,
            )
        run = runs[0]
        if run.state in {"queued", "running"}:
            return InvestigationView(state=run.state, execution_id=run.id)
        if run.state != "succeeded":
            return InvestigationView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "investigation"
        )
        result = Investigation.model_validate_json(self.objects.read(artifact.content))
        if (
            result.scope.execution_id != run.id
            or result.scope.version_id != version
            or result.scope.analysis_sha256 != run.input_artifact_sha256
        ):
            raise ApplicationError(
                "INTEGRITY_ERROR", "La investigación no corresponde a esta versión.", 409
            )
        return InvestigationView(state="ready", execution_id=run.id, investigation=result)

    def evidence(self, owner: UUID, version: UUID, identifier: str) -> AutomaticEvidence:
        view = self.view(owner, version)
        if view.investigation is not None:
            for item in view.investigation.results:
                for evidence in item.evidence:
                    if evidence.evidence_id == identifier:
                        return evidence
            analysis = self.executions.artifact(
                owner, view.investigation.scope.analysis_artifact_id
            )
            parsed = AutomaticAnalysis.model_validate_json(self.objects.read(analysis.content))
            for evidence in parsed.evidence:
                if evidence.evidence_id == identifier:
                    return evidence
        raise ApplicationError(
            "EVIDENCE_NOT_FOUND", "Esa cifra no existe en la investigación.", 404
        )
