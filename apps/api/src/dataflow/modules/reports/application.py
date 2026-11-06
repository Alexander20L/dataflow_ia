"""Casos de uso de informes: revisiones inmutables, procedencia automática de cada bloque de
datos, «Actualizar bloques» explícito, generación del PDF en el worker e instantánea para él."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from dataflow.modules.dashboards.contracts import ExecutionFacts, PlanFacts, TargetTable
from dataflow.modules.reports.contracts import (
    AnalysisBlock,
    Block,
    DashboardCardBlock,
    PdfRender,
    Provenance,
    RenderResponse,
    ReportContent,
    ReportDraft,
    ReportRepository,
    ReportRevision,
    ReportSnapshot,
    ReportSources,
    ReportSummary,
    ReportView,
    RevisionCause,
    RevisionItem,
    SaveReportResponse,
    SnapshotBlock,
    TextBlock,
)
from dataflow.modules.reports.domain import analysis_problem, block_status
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def content_sha256(content: ReportContent) -> str:
    return digest("report", content.model_dump(mode="json"))


CONFLICT = ("REPORT_CONFLICT", "El informe cambió: recárgalo antes de guardar.", 409)


class ReportService:
    def __init__(
        self, repository: ReportRepository, sources: ReportSources, uow: UnitOfWork
    ) -> None:
        self.repository, self.sources, self.uow = repository, sources, uow

    # --- Lectura ---------------------------------------------------------------------------

    def summaries(self, owner: UUID, project: UUID) -> list[ReportSummary]:
        self.sources.require_project(owner, project)
        result = []
        for family in self.repository.families(owner, project):
            head, count = self.repository.head(owner, family)
            result.append(ReportSummary(family_id=family, head=head, revision_count=count))
        return result

    def revision(self, owner: UUID, revision: UUID) -> ReportRevision:
        value = self.repository.revision(owner, revision)
        self.sources.require_project(owner, value.project_id)
        return value

    def revisions(self, owner: UUID, family: UUID) -> list[RevisionItem]:
        head, _ = self.repository.head(owner, family)
        self.sources.require_project(owner, head.project_id)
        return [
            RevisionItem(
                id=r.id,
                revision=r.revision,
                cause=r.cause,
                created_at=r.created_at,
                content_sha256=r.content_sha256,
            )
            for r in self.repository.revisions(owner, family)
        ]

    def view(self, owner: UUID, family: UUID, revision: UUID | None = None) -> ReportView:
        head, count = self.repository.head(owner, family)
        shown = self.repository.revision(owner, revision) if revision else head
        if shown.family_id != family:
            raise ApplicationError("REPORT_NOT_FOUND", "Informe no encontrado.", 404)
        self.sources.require_project(owner, shown.project_id)
        return ReportView(
            family_id=family,
            head=shown,
            revision_count=count,
            provenance=[
                self.provenance(owner, block)
                for block in shown.content.blocks
                if not isinstance(block, TextBlock)
            ],
        )

    def provenance(self, owner: UUID, block: AnalysisBlock | DashboardCardBlock) -> Provenance:
        """Procedencia automática: dataset, versión, ejecución, filtros y fecha."""
        dashboard_revision = None
        view, metric = "table", None
        if isinstance(block, DashboardCardBlock):
            card = self.sources.card(owner, block.dashboard_revision_id, block.card_id)
            plan_id, execution_id = card.plan_revision_id, card.execution_id
            dashboard_revision, view, metric = card.dashboard_revision_id, card.view, card.metric
        else:
            plan_id, execution_id = block.plan_revision_id, block.execution_id
        plan = self.sources.plan(owner, plan_id)
        execution = self.sources.execution(owner, execution_id) if execution_id else None
        status, message = block_status(plan, execution)
        version_id = execution.version_id if execution else plan.version_id
        version = self.sources.version(owner, version_id)
        parameters = plan.parameters
        return Provenance(
            block_id=block.id,
            status=status,
            message=message,
            dataset=version.dataset,
            version_id=version_id,
            version_number=version.number,
            plan_revision_id=plan_id,
            execution_id=execution_id,
            execution_state=execution.state if execution else None,
            executed_at=execution.finished_at if execution else None,
            filters=list(parameters.get("filters") or []),
            time_range=parameters.get("time_range"),
            dimensions=[UUID(str(d)) for d in parameters.get("dimensions") or []],
            time_grain=parameters.get("time_grain"),
            result_rows=execution.result_rows if execution else None,
            view=view,
            metric=metric,
            dashboard_revision_id=dashboard_revision,
        )

    def snapshot(self, owner: UUID, revision: UUID) -> ReportSnapshot:
        """Lo que el worker necesita para dibujar el PDF sin abrir la base de datos."""
        report = self.revision(owner, revision)
        version = self.sources.version(owner, report.content.version_id)
        blocks = []
        for block in report.content.blocks:
            if isinstance(block, TextBlock):
                blocks.append(SnapshotBlock(kind=block.kind, text=block.text))
                continue
            provenance = self.provenance(owner, block)
            result = (
                self.sources.analysis_result(owner, provenance.execution_id)
                if provenance.status == "ready" and provenance.execution_id
                else None
            )
            blocks.append(
                SnapshotBlock(
                    kind=block.kind, title=block.title, provenance=provenance, result=result
                )
            )
        return ReportSnapshot(
            report_title=report.content.title,
            family_id=report.family_id,
            revision_id=report.id,
            revision=report.revision,
            content_sha256=report.content_sha256,
            dataset=version.dataset,
            version_number=version.number,
            generated_at=datetime.now(UTC),
            blocks=blocks,
        )

    # --- Escritura -------------------------------------------------------------------------

    def create(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        draft: ReportDraft,
        key: UUID,
        correlation: str,
    ) -> SaveReportResponse:
        try:
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "report_create_request",
                {
                    "project_id": str(project),
                    "version_id": str(version),
                    "draft": draft.model_dump(mode="json"),
                },
            )
            self.repository.lock_scope(project)
            replayed = self.repository.replay(owner, project, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveReportResponse(revision=replayed, changed=True)
            if self.sources.version(owner, version).project_id != project:
                raise ApplicationError(
                    "VERSION_NOT_FOUND", "La versión no pertenece al proyecto.", 404
                )
            content = self.validated(owner, project, version, draft)
            family = self.repository.create_family(owner, project)
            revision = self.append(owner, family, 0, None, content, "create", None, correlation)
            self.repository.remember(owner, project, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveReportResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def revise(
        self,
        owner: UUID,
        family: UUID,
        expected: int,
        draft: ReportDraft,
        key: UUID,
        correlation: str,
    ) -> SaveReportResponse:
        try:
            project, head = self.repository.lock_family(owner, family)
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "report_revise_request",
                {
                    "family_id": str(family),
                    "expected_revision": expected,
                    "draft": draft.model_dump(mode="json"),
                },
            )
            replayed = self.repository.replay(owner, family, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveReportResponse(revision=replayed, changed=True)
            if head != expected:
                raise ApplicationError(*CONFLICT)
            current, _ = self.repository.head(owner, family)
            content = self.validated(owner, project, current.content.version_id, draft)
            if content == current.content:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return SaveReportResponse(revision=current, changed=False)
            revision = self.append(
                owner, family, head, current.id, content, "edit", None, correlation
            )
            self.repository.remember(owner, family, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveReportResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def refresh(
        self,
        owner: UUID,
        family: UUID,
        expected: int,
        version: UUID,
        key: UUID,
        correlation: str,
    ) -> SaveReportResponse:
        """«Actualizar bloques» sobre la versión elegida: los análisis se vuelven a ejecutar (se
        reutiliza su plan si la tabla y la semántica coinciden; si no, plan nuevo con los mismos
        pasos) y las tarjetas pasan a la revisión vigente de su dashboard. Revisión nueva; las
        claves derivan de `key`, así que repetir la solicitud no crea nada nuevo."""
        try:
            project, head = self.repository.lock_family(owner, family)
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "report_refresh_request",
                {"family_id": str(family), "expected_revision": expected, "version": str(version)},
            )
            replayed = self.repository.replay(owner, family, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveReportResponse(revision=replayed, changed=True)
            if head != expected:
                raise ApplicationError(*CONFLICT)
            current, _ = self.repository.head(owner, family)
            target = self.sources.target(owner, version)
            if target.project_id != project:
                raise ApplicationError(
                    "VERSION_NOT_FOUND", "La versión no pertenece al proyecto del informe.", 404
                )
            self.uow.rollback()  # crear y ejecutar planes confirma por su cuenta
            reran: dict[UUID, tuple[PlanFacts, UUID | None]] = {}
            blocks: list[Block] = []
            for block in current.content.blocks:
                if isinstance(block, AnalysisBlock):
                    if block.plan_revision_id not in reran:
                        reran[block.plan_revision_id] = self.rerun(
                            owner, block.plan_revision_id, target, key, correlation
                        )
                    plan, execution = reran[block.plan_revision_id]
                    blocks.append(
                        block.model_copy(
                            update={"plan_revision_id": plan.revision_id, "execution_id": execution}
                        )
                    )
                elif isinstance(block, DashboardCardBlock):
                    card = self.sources.card(owner, block.dashboard_revision_id, block.card_id)
                    latest = self.sources.latest_card(owner, card.family_id, block.card_id)
                    blocks.append(
                        block.model_copy(
                            update={"dashboard_revision_id": latest.dashboard_revision_id}
                        )
                        if latest
                        else block
                    )
                else:
                    blocks.append(block)
            content = current.content.model_copy(update={"blocks": blocks, "version_id": version})
            _, head = self.repository.lock_family(owner, family)
            if head != expected:
                raise ApplicationError(*CONFLICT)
            revision = self.append(
                owner, family, head, current.id, content, "refresh", version, correlation
            )
            self.repository.remember(owner, family, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveReportResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def render(self, owner: UUID, revision: UUID, key: UUID, correlation: str) -> RenderResponse:
        """Encola el PDF de una revisión exacta del informe (ejecución `report_render`)."""
        try:
            report = self.revision(owner, revision)
            self.sources.require_project(owner, report.project_id, writable=True)
            run = self.sources.enqueue_render(owner, report, key, correlation)
            self.repository.add_render(owner, report.family_id, report.id, run.id)
            self.uow.commit()
            return RenderResponse(
                execution_id=run.id, state=run.state, report_revision_id=report.id
            )
        except Exception:
            self.uow.rollback()
            raise

    def renders(self, owner: UUID, family: UUID) -> list[PdfRender]:
        head, _ = self.repository.head(owner, family)
        self.sources.require_project(owner, head.project_id)
        return [
            self.sources.render(owner, execution, revision)
            for execution, revision in self.repository.renders(owner, family)
        ]

    def pdf(self, owner: UUID, execution: UUID) -> tuple[str, bytes, str]:
        found = self.repository.render_owner(owner, execution)
        if not found:
            raise ApplicationError("REPORT_PDF_NOT_FOUND", "PDF no encontrado.", 404)
        family, revision = found
        head, _ = self.repository.head(owner, family)
        self.sources.require_project(owner, head.project_id)
        state = self.sources.render(owner, execution, revision)
        if state.state != "succeeded":
            raise ApplicationError("REPORT_PDF_NOT_READY", "El PDF todavía no está listo.", 409)
        content, sha256 = self.sources.pdf(owner, execution)
        number = self.repository.revision(owner, revision).revision
        return f"informe-r{number}-{str(execution)[:8]}.pdf", content, sha256

    # --- Internos --------------------------------------------------------------------------

    def rerun(
        self, owner: UUID, plan_id: UUID, target: TargetTable, key: UUID, correlation: str
    ) -> tuple[PlanFacts, UUID | None]:
        plan = self.sources.plan(owner, plan_id)
        if plan.artifact_id != target.artifact_id or plan.semantic_ref != target.semantic_ref:
            plan = self.sources.create_plan(
                owner, target, plan.steps, uuid5(key, f"plan:{plan_id}"), correlation
            )
        if not plan.valid:
            return plan, None
        run = self.sources.execute(
            owner, plan.revision_id, uuid5(key, f"run:{plan.revision_id}"), correlation
        )
        return plan, run

    def validated(
        self, owner: UUID, project: UUID, version: UUID, draft: ReportDraft
    ) -> ReportContent:
        problems: list[str] = []
        for block in draft.blocks:
            if isinstance(block, AnalysisBlock):
                plan = self.sources.plan(owner, block.plan_revision_id)
                if plan.project_id != project:
                    problems.append(f"«{block.title}»: el análisis es de otro proyecto.")
                    continue
                problem = analysis_problem(plan)
                if problem:
                    problems.append(f"«{block.title}»: {problem}")
                if block.execution_id is not None:
                    execution: ExecutionFacts = self.sources.execution(owner, block.execution_id)
                    if execution.plan_revision_id != block.plan_revision_id:
                        problems.append(
                            f"«{block.title}»: la ejecución no corresponde a ese análisis."
                        )
            elif isinstance(block, DashboardCardBlock):
                card = self.sources.card(owner, block.dashboard_revision_id, block.card_id)
                if card.project_id != project:
                    problems.append(f"«{block.title}»: el dashboard es de otro proyecto.")
        if problems:
            raise ApplicationError("REPORT_INVALID", " ".join(problems), 422)
        return ReportContent(**draft.model_dump(), project_id=project, version_id=version)

    def append(
        self,
        owner: UUID,
        family: UUID,
        head: int,
        previous: UUID | None,
        content: ReportContent,
        cause: RevisionCause,
        version: UUID | None,
        correlation: str,
    ) -> ReportRevision:
        revision = ReportRevision(
            id=uuid4(),
            family_id=family,
            project_id=content.project_id,
            revision=head + 1,
            previous_revision_id=previous,
            cause=cause,
            refreshed_version_id=version,
            content=content,
            content_sha256=content_sha256(content),
            created_by=owner,
            created_at=datetime.now(UTC),
        )
        self.repository.append(family, head, revision, correlation)
        return revision
