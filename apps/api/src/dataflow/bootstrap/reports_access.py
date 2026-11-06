"""Puerto de informes y entrada `report` del worker (Fase 9).

reports no importa planning, executions, analytics ni dashboards (salvo sus contratos):
bootstrap le da planes, ejecuciones, versiones, tarjetas y resultados, encola el PDF como
ejecución `report_render` y, en el worker, prepara la instantánea del informe."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from dataflow.bootstrap.dashboards_access import DashboardAccess
from dataflow.modules.analytics.application import MetricService
from dataflow.modules.dashboards.application import DashboardService
from dataflow.modules.dashboards.contracts import ExecutionFacts, PlanFacts, TargetTable
from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import (
    Executions,
    Lease,
    PlanRevision,
    ProcessingConfig,
    StepExecutor,
    StepInput,
    StepRegistry,
)
from dataflow.modules.reports.application import ReportService
from dataflow.modules.reports.contracts import (
    RENDER_OPERATION,
    CardFacts,
    PdfRender,
    ReportRevision,
    VersionFacts,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class ReportAccess:
    def __init__(
        self,
        dashboards_access: DashboardAccess,
        dashboards: DashboardService,
        metrics: MetricService,
        executions: Executions,
        datasets: Datasets,
        objects: ObjectStore,
        config: ProcessingConfig,
    ) -> None:
        self.access, self.dashboards, self.metrics = dashboards_access, dashboards, metrics
        self.executions, self.datasets, self.objects = executions, datasets, objects
        self.config = config

    # Delegados del puerto de dashboards (mismas reglas de planes y ejecuciones).
    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None:
        self.access.require_project(owner, project, writable)

    def plan(self, owner: UUID, revision: UUID) -> PlanFacts:
        return self.access.plan(owner, revision)

    def execution(self, owner: UUID, execution: UUID) -> ExecutionFacts:
        return self.access.execution(owner, execution)

    def target(self, owner: UUID, version: UUID) -> TargetTable:
        return self.access.target(owner, version)

    def create_plan(
        self,
        owner: UUID,
        table: TargetTable,
        steps: list[dict[str, Any]],
        key: UUID,
        correlation: str,
    ) -> PlanFacts:
        return self.access.create_plan(owner, table, steps, key, correlation)

    def execute(self, owner: UUID, plan_revision: UUID, key: UUID, correlation: str) -> UUID:
        return self.access.execute(owner, plan_revision, key, correlation)

    def version(self, owner: UUID, version: UUID) -> VersionFacts:
        record = self.datasets.get(owner, version)
        return VersionFacts(
            project_id=record.project_id, number=record.number, dataset=record.file_name
        )

    def card(self, owner: UUID, dashboard_revision: UUID, card: UUID) -> CardFacts:
        revision = self.dashboards.revision(owner, dashboard_revision)
        found = next((c for c in revision.content.cards if c.id == card), None)
        if found is None:
            raise ApplicationError(
                "CARD_NOT_FOUND", "La tarjeta no existe en esa revisión del dashboard.", 422
            )
        return CardFacts(
            dashboard_revision_id=revision.id,
            family_id=revision.family_id,
            project_id=revision.project_id,
            card_id=card,
            plan_revision_id=found.plan_revision_id,
            execution_id=found.execution_id,
            view=found.view,
            metric=found.metric,
        )

    def latest_card(self, owner: UUID, family: UUID, card: UUID) -> CardFacts | None:
        head = self.dashboards.head(owner, family)
        if not any(c.id == card for c in head.content.cards):
            return None
        return self.card(owner, head.id, card)

    def analysis_result(self, owner: UUID, execution: UUID) -> dict[str, Any] | None:
        return self.metrics.result(owner, execution).model_dump(mode="json")

    def enqueue_render(
        self, owner: UUID, revision: ReportRevision, key: UUID, correlation: str
    ) -> ExecutionFacts:
        """Ejecución `report_render` con un plan de sistema: entrada `report` (revisión exacta y
        su hash) y la operación interna reports.render_pdf@1."""
        operation, version = RENDER_OPERATION
        fingerprint = digest(
            "report_render_request",
            {"report_revision_id": str(revision.id), "content_sha256": revision.content_sha256},
        )
        existing = self.executions.find_request(
            owner, revision.project_id, "report_render", key, fingerprint
        )
        if existing is None:
            content = {
                "objective": None,
                "input": {
                    "kind": "report",
                    "alias": "source",
                    "report_revision_id": str(revision.id),
                    "content_sha256": revision.content_sha256,
                },
                "semantic_ref": None,
                "steps": [
                    {
                        "id": "pdf",
                        "operation": operation,
                        "version": version,
                        "input": {"kind": "input", "alias": "source"},
                        "parameters": {"report_revision_id": str(revision.id)},
                    }
                ],
                "config": self.config.model_dump(),
            }
            plan = PlanRevision(
                uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
            )
            existing = self.executions.enqueue(
                owner,
                revision.project_id,
                revision.content.version_id,
                "report_render",
                key,
                fingerprint,
                plan,
                correlation,
            )
        return self.execution(owner, existing.id)

    def render(self, owner: UUID, execution: UUID, revision: UUID) -> PdfRender:
        run = self.executions.get(owner, execution)
        pdf = next(
            (a for a in self.executions.artifacts(owner, execution) if a.kind == "report_pdf"),
            None,
        )
        return PdfRender(
            execution_id=run.id,
            report_revision_id=revision,
            state=run.state,
            created_at=run.created_at,
            finished_at=run.finished_at,
            sha256=pdf.content.sha256 if pdf else None,
            error_message=run.error_message,
        )

    def pdf(self, owner: UUID, execution: UUID) -> tuple[bytes, str]:
        pdf = next(
            (a for a in self.executions.artifacts(owner, execution) if a.kind == "report_pdf"),
            None,
        )
        if pdf is None:
            raise ApplicationError("REPORT_PDF_NOT_READY", "El PDF todavía no está listo.", 409)
        return self.objects.read(pdf.content), pdf.content.sha256


class ReportInputResolver:
    """Entrada `report` del worker: verifica la revisión exacta y prepara su instantánea
    (bloques, procedencia y resultados) antes de cerrar la transacción de metadatos."""

    def __init__(self, reports: Callable[[], ReportService], objects: ObjectStore) -> None:
        self.reports, self.objects = reports, objects

    def prepare(self, lease: Lease) -> StepInput:
        assert lease.execution.plan
        source = lease.execution.plan.content["input"]
        snapshot = self.reports().snapshot(lease.owner_id, UUID(source["report_revision_id"]))
        if snapshot.content_sha256 != source["content_sha256"]:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El informe no coincide con la revisión fijada.", 409
            )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}"
        stored = self.objects.put(
            f"{prefix}/report-snapshot.json", snapshot.model_dump_json().encode("utf-8")
        )
        return StepInput("report", stored, snapshot.content_sha256)


class WorkerRegistry:
    """Catálogo de usuario más operaciones internas del worker (no planificables)."""

    def __init__(self, catalog: StepRegistry, internal: dict[str, StepExecutor]) -> None:
        self.catalog, self.internal = catalog, internal

    def executor(self, operation: str, version: int) -> StepExecutor | None:
        return self.catalog.executor(operation, version) or self.internal.get(
            f"{operation}@{version}"
        )
