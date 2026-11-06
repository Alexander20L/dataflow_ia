"""Casos de uso de dashboards: revisiones inmutables, vista con el estado de cada tarjeta y
«Actualizar» explícito sobre una versión elegida."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from dataflow.modules.dashboards.contracts import (
    Card,
    CardRefresh,
    CardState,
    DashboardContent,
    DashboardDraft,
    DashboardRepository,
    DashboardRevision,
    DashboardSources,
    DashboardSummary,
    DashboardView,
    ExecutionFacts,
    PlanFacts,
    RefreshDashboardResponse,
    RevisionCause,
    SaveDashboardResponse,
    TargetTable,
)
from dataflow.modules.dashboards.domain import (
    card_problems,
    card_status,
    filter_applicability,
    query_shape,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def content_sha256(content: DashboardContent) -> str:
    return digest("dashboard", content.model_dump(mode="json"))


class DashboardService:
    def __init__(
        self, repository: DashboardRepository, sources: DashboardSources, uow: UnitOfWork
    ) -> None:
        self.repository, self.sources, self.uow = repository, sources, uow

    # --- Lectura ---------------------------------------------------------------------------

    def summaries(self, owner: UUID, project: UUID) -> list[DashboardSummary]:
        self.sources.require_project(owner, project)
        result = []
        for family in self.repository.families(owner, project):
            head, count = self.repository.head(owner, family)
            result.append(DashboardSummary(family_id=family, head=head, revision_count=count))
        return result

    def head(self, owner: UUID, family: UUID) -> DashboardRevision:
        value, _ = self.repository.head(owner, family)
        self.sources.require_project(owner, value.project_id)
        return value

    def revision(self, owner: UUID, revision: UUID) -> DashboardRevision:
        value = self.repository.revision(owner, revision)
        self.sources.require_project(owner, value.project_id)
        return value

    def view(self, owner: UUID, family: UUID) -> DashboardView:
        head, count = self.repository.head(owner, family)
        self.sources.require_project(owner, head.project_id)
        content = head.content
        states = []
        for card in content.cards:
            plan = self.sources.plan(owner, card.plan_revision_id)
            execution = (
                self.sources.execution(owner, card.execution_id) if card.execution_id else None
            )
            status, message = card_status(plan, execution)
            dimensions, grain, _ = query_shape(plan)
            version = execution.version_id if execution else plan.version_id
            states.append(
                CardState(
                    card_id=card.id,
                    status=status,
                    message=message,
                    version_id=version,
                    version_number=self.sources.version_number(owner, version),
                    dimensions=dimensions,
                    time_grain=grain,
                    execution_state=execution.state if execution else None,
                    executed_at=execution.finished_at if execution else None,
                    result_rows=execution.result_rows if execution else None,
                    filters=filter_applicability(content.filters, plan),
                )
            )
        return DashboardView(family_id=family, head=head, revision_count=count, cards=states)

    # --- Escritura -------------------------------------------------------------------------

    def create(
        self, owner: UUID, project: UUID, draft: DashboardDraft, key: UUID, correlation: str
    ) -> SaveDashboardResponse:
        try:
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "dashboard_create_request",
                {"project_id": str(project), "draft": draft.model_dump(mode="json")},
            )
            self.repository.lock_scope(project)
            replayed = self.repository.replay(owner, project, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveDashboardResponse(revision=replayed, changed=True)
            content = self.validated(owner, project, draft)
            family = self.repository.create_family(owner, project)
            revision = self.append(owner, family, 0, None, content, "create", None, correlation)
            self.repository.remember(owner, project, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveDashboardResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def revise(
        self,
        owner: UUID,
        family: UUID,
        expected: int,
        draft: DashboardDraft,
        key: UUID,
        correlation: str,
    ) -> SaveDashboardResponse:
        try:
            project, head = self.repository.lock_family(owner, family)
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "dashboard_revise_request",
                {
                    "family_id": str(family),
                    "expected_revision": expected,
                    "draft": draft.model_dump(mode="json"),
                },
            )
            replayed = self.repository.replay(owner, family, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveDashboardResponse(revision=replayed, changed=True)
            if head != expected:
                raise ApplicationError(
                    "DASHBOARD_CONFLICT", "El dashboard cambió: recárgalo antes de guardar.", 409
                )
            current, _ = self.repository.head(owner, family)
            content = self.validated(owner, project, draft)
            if content == current.content:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return SaveDashboardResponse(revision=current, changed=False)
            revision = self.append(
                owner, family, head, current.id, content, "edit", None, correlation
            )
            self.repository.remember(owner, family, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveDashboardResponse(revision=revision, changed=True)
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
    ) -> RefreshDashboardResponse:
        """Vuelve a ejecutar cada tarjeta sobre la versión elegida y crea una revisión nueva.

        Un plan está fijado a su tabla: si la tarjeta ya apunta a la tabla y a la revisión
        semántica vigente de esa versión se reutiliza su plan; si no, se crea un plan nuevo con
        los mismos pasos. Un plan que no es válido (p. ej. requisito semántico pendiente) deja la
        tarjeta sin ejecución, sin romper las demás. Las claves de planes y ejecuciones derivan de
        `key`: repetir la solicitud reutiliza lo ya creado."""
        try:
            project, head = self.repository.lock_family(owner, family)
            self.sources.require_project(owner, project, writable=True)
            fingerprint = digest(
                "dashboard_refresh_request",
                {"family_id": str(family), "expected_revision": expected, "version": str(version)},
            )
            replayed = self.repository.replay(owner, family, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return RefreshDashboardResponse(
                    revision=replayed, cards=self.replayed_cards(owner, replayed)
                )
            if head != expected:
                raise ApplicationError(
                    "DASHBOARD_CONFLICT", "El dashboard cambió: recárgalo antes de actualizar.", 409
                )
            current, _ = self.repository.head(owner, family)
            target = self.sources.target(owner, version)
            if target.project_id != project:
                raise ApplicationError(
                    "VERSION_NOT_FOUND", "La versión no pertenece al proyecto del dashboard.", 404
                )
            self.uow.rollback()  # libera el bloqueo: crear y ejecutar planes confirma por su cuenta
            cards: list[Card] = []
            outcomes: list[CardRefresh] = []
            reused: dict[UUID, tuple[PlanFacts, bool, UUID | None]] = {}
            for card in current.content.cards:
                if card.plan_revision_id not in reused:
                    reused[card.plan_revision_id] = self.rerun(
                        owner, card, target, key, correlation
                    )
                plan, created, execution = reused[card.plan_revision_id]
                cards.append(
                    card.model_copy(
                        update={"plan_revision_id": plan.revision_id, "execution_id": execution}
                    )
                )
                outcomes.append(
                    CardRefresh(
                        card_id=card.id,
                        plan_revision_id=plan.revision_id,
                        plan_created=created,
                        execution_id=execution,
                        problems=[message for _, message in plan.problems],
                    )
                )
            content = current.content.model_copy(update={"cards": cards})
            project, head = self.repository.lock_family(owner, family)
            if head != expected:
                raise ApplicationError(
                    "DASHBOARD_CONFLICT", "El dashboard cambió: recárgalo antes de actualizar.", 409
                )
            revision = self.append(
                owner, family, head, current.id, content, "refresh", version, correlation
            )
            self.repository.remember(owner, family, key, fingerprint, revision.id)
            self.uow.commit()
            return RefreshDashboardResponse(revision=revision, cards=outcomes)
        except Exception:
            self.uow.rollback()
            raise

    # --- Internos --------------------------------------------------------------------------

    def rerun(
        self, owner: UUID, card: Card, target: TargetTable, key: UUID, correlation: str
    ) -> tuple[PlanFacts, bool, UUID | None]:
        plan = self.sources.plan(owner, card.plan_revision_id)
        created = False
        if plan.artifact_id != target.artifact_id or plan.semantic_ref != target.semantic_ref:
            plan = self.sources.create_plan(
                owner, target, plan.steps, uuid5(key, f"plan:{card.plan_revision_id}"), correlation
            )
            created = True
        if not plan.valid:
            return plan, created, None
        execution = self.sources.execute(
            owner, plan.revision_id, uuid5(key, f"run:{plan.revision_id}"), correlation
        )
        return plan, created, execution

    def replayed_cards(self, owner: UUID, revision: DashboardRevision) -> list[CardRefresh]:
        cards = []
        for card in revision.content.cards:
            plan = self.sources.plan(owner, card.plan_revision_id)
            cards.append(
                CardRefresh(
                    card_id=card.id,
                    plan_revision_id=card.plan_revision_id,
                    plan_created=False,
                    execution_id=card.execution_id,
                    problems=[message for _, message in plan.problems],
                )
            )
        return cards

    def validated(self, owner: UUID, project: UUID, draft: DashboardDraft) -> DashboardContent:
        """Cada tarjeta: plan de analytics.query@2 del mismo proyecto, ejecución de esa revisión
        del plan y forma compatible con la consulta."""
        problems: list[str] = []
        for card in draft.cards:
            plan = self.sources.plan(owner, card.plan_revision_id)
            if plan.project_id != project:
                problems.append(f"«{card.title}»: el análisis es de otro proyecto.")
                continue
            problems.extend(f"«{card.title}»: {p}" for p in card_problems(card, plan))
            if card.execution_id is not None:
                execution: ExecutionFacts = self.sources.execution(owner, card.execution_id)
                if execution.plan_revision_id != card.plan_revision_id:
                    problems.append(
                        f"«{card.title}»: la ejecución no corresponde a esa revisión del análisis."
                    )
        if problems:
            raise ApplicationError("DASHBOARD_INVALID", " ".join(problems), 422)
        return DashboardContent(**draft.model_dump(), project_id=project)

    def append(
        self,
        owner: UUID,
        family: UUID,
        head: int,
        previous: UUID | None,
        content: DashboardContent,
        cause: RevisionCause,
        version: UUID | None,
        correlation: str,
    ) -> DashboardRevision:
        revision = DashboardRevision(
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
