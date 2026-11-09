"""Conecta snapshots, cola de ejecuciones y auditor textual sin acoplar sus módulos."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.ai import configured
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.contracts import CallRecord
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.copilot.overview import (
    PROMPT_ID,
    PROMPT_VERSION,
    OverviewAudit,
    OverviewAuditView,
    OverviewEvidence,
    explain_overview,
    figure,
)
from dataflow.modules.datasets.public import Datasets, ObjectStore
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
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.contracts import AutomaticOverview, DatasetProfile
from dataflow.platform.canonical import digest
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError


def enqueue_audit(
    executions: Executions,
    lease: Lease,
    profile: Artifact,
    config: ProcessingConfig,
) -> None:
    settings = get_settings()
    provider = settings.effective_ai_provider()
    if provider == "disabled" or (provider == "anthropic" and not settings.ai_key()):
        return
    key = uuid5(lease.execution_id, "automatic-overview-audit@1")
    fingerprint = digest(
        "overview_audit_request",
        {
            "profile_id": str(profile.id),
            "profile_sha256": profile.content.sha256,
            "prompt": f"{PROMPT_ID}@{PROMPT_VERSION}",
        },
    )
    if executions.find_request(
        lease.owner_id, lease.execution.project_id, "overview_audit", key, fingerprint
    ):
        return
    # Una llamada como máximo por intento; no reintentar automáticamente una llamada cuyo
    # resultado pudo facturarse antes de una caída. El dashboard no depende de este trabajo.
    assert lease.execution.plan
    content = {
        "objective": None,
        "input": {
            "kind": "overview",
            "alias": "source",
            "version_id": str(lease.version_id),
            "version_content_sha256": lease.execution.plan.content["input"][
                "version_content_sha256"
            ],
            "artifact_id": str(profile.id),
            "artifact_sha256": profile.content.sha256,
            "producer_execution_id": str(profile.execution_id),
        },
        "steps": [
            {
                "id": "audit",
                "operation": "copilot.audit_overview",
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {},
            }
        ],
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
        profile.id,
        profile.content.sha256,
        kind="overview_audit",
    )


def overview_evidence(overview: AutomaticOverview, sha256: str) -> list[OverviewEvidence]:
    cells = [
        figure(sha256, f"/kpis/{index}/value", kpi.label, kpi.value, kpi.unit)
        for index, kpi in enumerate(overview.kpis)
    ]
    for index, chart in enumerate(overview.charts):
        for point_index, point in enumerate(chart.points[:12]):
            if len(cells) >= 64:
                return cells
            # Gráficos de una medida (automatic-overview-v3): la cifra es la suma exacta.
            cells.append(
                figure(
                    sha256,
                    f"/charts/{index}/points/{point_index}/amount",
                    f"{chart.title}: {point.label}",
                    point.amount,
                    "number",
                )
                if point.amount is not None
                else figure(
                    sha256,
                    f"/charts/{index}/points/{point_index}/value",
                    f"{chart.title}: {point.label}",
                    str(point.value),
                    "count",
                )
            )
    return cells


class OverviewInput:
    def __init__(
        self, datasets: Datasets, executions: Executions, projects: ProjectPermissions
    ) -> None:
        self.datasets, self.executions, self.projects = datasets, executions, projects

    def prepare(self, lease: Lease) -> StepInput:
        assert lease.execution.plan and lease.execution.input_artifact_id
        run = lease.execution
        assert run.plan and run.input_artifact_id
        self.projects.require(run.owner_id, run.project_id, writable=True)
        version = self.datasets.get(run.owner_id, run.version_id)
        profile = self.executions.artifact(run.owner_id, run.input_artifact_id)
        source = run.plan.content["input"]
        if (
            profile.kind != "profile"
            or profile.version_id != version.id
            or str(profile.id) != source.get("artifact_id")
            or str(version.id) != source.get("version_id")
            or version.content.sha256 != source.get("version_content_sha256")
            or profile.content.sha256 != source.get("artifact_sha256")
            or profile.content.sha256 != run.input_artifact_sha256
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "El snapshot de la auditoría no coincide.", 409
            )
        if str(profile.execution_id) != source.get("producer_execution_id"):
            raise ApplicationError("INPUT_MISMATCH", "El productor del perfil no coincide.", 409)
        return StepInput("overview", profile.content, version.content.sha256)


class OverviewAuditStep:
    output_kind: ArtifactKind = "overview_audit"
    transforms_data = False

    def __init__(self, objects: ObjectStore, copilot: CopilotService) -> None:
        self.objects, self.copilot = objects, copilot
        self.prepared: dict[UUID, str | None] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        reason = None
        try:
            self.copilot.available(lease.owner_id, lease.execution.project_id)
        except ApplicationError as error:
            reason = error.code
        self.prepared[lease.attempt_id] = reason

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "overview" or step.parameters or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó la auditoría automática.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        profile = DatasetProfile.model_validate_json(self.objects.read(source.content))
        assert lease.execution.plan and lease.execution.input_artifact_id
        if profile.overview is None or profile.source_sha256 != source.source_sha256:
            raise ApplicationError(
                "INPUT_MISMATCH", "El perfil no contiene el dashboard fijado.", 409
            )
        limitations = [
            *profile.overview.limitations,
            "La explicación cubre hasta sesenta y cuatro cifras; no audita filas de detalle.",
        ]
        if profile.overview.interpretation:
            limitations.extend(profile.overview.interpretation.limitations)
        if profile.overview.analysis:
            limitations.extend(profile.overview.analysis.limitations)
            limitations.extend(
                f"{item.subject}: {item.reason}"
                for item in profile.overview.analysis.limited_analyses
            )
        cells = overview_evidence(profile.overview, source.content.sha256)
        result = explain_overview(
            lease.execution.input_artifact_id,
            source.content.sha256,
            UUID(lease.execution.plan.content["input"]["producer_execution_id"]),
            cells,
            limitations,
            self.copilot.provider,
            unavailable,
            self.copilot.config.max_output_tokens,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        stored = self.objects.put(
            f"{prefix}/overview_audit.json", result.model_dump_json().encode()
        )
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "overview_audit",
                    "overview_audit",
                    stored,
                    "application/json",
                    0,
                    0,
                )
            ]
        )


def record_audit_call(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    audit = OverviewAudit.model_validate_json(objects.read(output.content))
    if (
        audit.profile_id != lease.execution.input_artifact_id
        or audit.profile_sha256 != lease.execution.input_artifact_sha256
    ):
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "La auditoría no corresponde al perfil.", 409
        )
    call = audit.call
    if call is not None:
        SQLCopilotRepository(db).log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="overview_audit",
                provider=call.provider,
                model=call.model,
                parameters=call.parameters,
                prompt_id=audit.prompt_id,
                prompt_version=audit.prompt_version,
                context_sha256=call.context_sha256,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cache_read_tokens=call.cache_read_tokens,
                cache_write_tokens=call.cache_write_tokens,
                cost_usd=Decimal(call.cost_usd) if call.cost_usd is not None else None,
                latency_ms=call.latency_ms,
                outcome=call.outcome,
                validation={"state": audit.state, "profile_sha256": audit.profile_sha256},
                error_code=call.error_code,
            )
        )


class OverviewAuditAccess:
    def __init__(self, datasets: Datasets, executions: Executions, objects: ObjectStore) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects

    def view(self, owner: UUID, version: UUID) -> OverviewAuditView:
        self.datasets.get(owner, version)
        binding = self.datasets.binding(owner, version)
        runs = [
            run
            for run in self.executions.for_version(owner, version)
            if run.kind == "overview_audit" and run.input_artifact_id == binding.profile_artifact_id
        ]
        if not runs:
            _, config = configured()
            return OverviewAuditView(
                state="unavailable", reason=config.unavailable or "not_generated"
            )
        run = runs[0]
        if run.state in {"queued", "running"}:
            return OverviewAuditView(state=run.state, execution_id=run.id)
        if run.state != "succeeded":
            return OverviewAuditView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "overview_audit"
        )
        audit = OverviewAudit.model_validate_json(self.objects.read(artifact.content))
        if (
            audit.profile_id != binding.profile_artifact_id
            or audit.profile_sha256 != run.input_artifact_sha256
        ):
            raise ApplicationError(
                "INTEGRITY_ERROR", "La explicación no corresponde a esta versión.", 409
            )
        return OverviewAuditView(
            state=audit.state, reason=audit.reason, execution_id=run.id, audit=audit
        )

    def evidence(self, owner: UUID, version: UUID, identifier: str) -> OverviewEvidence:
        view = self.view(owner, version)
        if view.audit and view.audit.state == "ready":
            for cell in view.audit.evidence:
                if cell.id == identifier:
                    return cell
        raise ApplicationError("EVIDENCE_NOT_FOUND", "Evidencia no encontrada.", 404)
