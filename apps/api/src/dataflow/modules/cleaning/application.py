import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.cleaning.contracts import (
    ApplyStatus,
    ApprovalRepository,
    ApprovalView,
    ColumnEffectCounts,
    EffectManifest,
    EffectSample,
    LineageOperation,
    LineageView,
    PreviewFailure,
    PreviewView,
)
from dataflow.modules.cleaning.proposal import CleaningProposal, ProposalInputs, propose
from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import Execution, Executions
from dataflow.modules.planning.contracts import InputRef, OperationCatalog, PlanView
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class CleaningPlans(Protocol):
    """Acceso a planes guardados y permisos del proyecto (bootstrap lo implementa con planning)."""

    def plan(self, owner: UUID, revision: UUID) -> PlanView: ...
    def require_write(self, owner: UUID, project: UUID) -> None: ...
    def lock_owner(self, owner: UUID) -> None: ...


def apply_fingerprint(approval: UUID) -> str:
    return digest("cleaning_apply_request", {"approval_id": str(approval)})


class CleaningService:
    def __init__(
        self,
        executions: Executions,
        plans: CleaningPlans,
        approvals: ApprovalRepository,
        catalog: OperationCatalog,
        datasets: Datasets,
        objects: ObjectStore,
        uow: UnitOfWork,
    ) -> None:
        self.executions, self.plans, self.approvals = executions, plans, approvals
        self.catalog, self.datasets, self.objects, self.uow = catalog, datasets, objects, uow

    def require_chain(self, plan: PlanView) -> None:
        """Una limpieza es una cadena lineal sólo de operaciones que transforman datos; el
        perfil y la calidad de la versión derivada se encolan al publicarla."""
        previous: str | None = None
        for step in plan.steps:
            descriptor = self.catalog.descriptor(step.operation, step.version)
            linked = (
                isinstance(step.input, InputRef)
                if previous is None
                else not isinstance(step.input, InputRef) and step.input.step_id == previous
            )
            if descriptor is None or not descriptor.transforms_data or not linked:
                break
            previous = step.id
        else:
            if previous is not None:
                return
        raise ApplicationError(
            "CLEANING_PLAN_REQUIRED",
            "La vista previa requiere una cadena de operaciones de limpieza, cada una sobre la "
            "salida de la anterior.",
            422,
        )

    def preview(self, owner: UUID, revision: UUID, key: UUID, correlation: str) -> Execution:
        try:
            # Leer el plan antes del lock: su revalidación (si cambió el catálogo) confirma.
            plan = self.plans.plan(owner, revision)
            self.plans.lock_owner(owner)
            fingerprint = digest(
                "cleaning_preview_request",
                {"plan_revision_id": str(plan.id), "content_sha256": plan.content_sha256},
            )
            existing = self.executions.find_request(
                owner, plan.project_id, "cleaning_preview", key, fingerprint
            )
            if existing:
                self.uow.rollback()
                return existing
            self.plans.require_write(owner, plan.project_id)
            if not plan.validation.valid:
                raise ApplicationError(
                    "PLAN_INCOMPLETE",
                    "Resuelve los problemas pendientes del plan antes de la vista previa.",
                    422,
                )
            self.require_chain(plan)
            run = self.executions.enqueue_existing_plan(
                owner,
                plan.project_id,
                plan.input.version_id,
                key,
                fingerprint,
                self.executions.plan_revision(owner, plan.id),
                correlation,
                "cleaning_preview",
            )
            self.uow.commit()
            return run
        except Exception:
            self.uow.rollback()
            raise

    def preview_run(self, owner: UUID, execution: UUID) -> Execution:
        run = self.executions.get(owner, execution)
        if run.kind != "cleaning_preview" or run.plan is None:
            raise ApplicationError("PREVIEW_NOT_FOUND", "Vista previa no encontrada.", 404)
        return run

    def effect(self, owner: UUID, run: Execution) -> tuple[dict[str, Any], list[Any]]:
        artifacts = {a.kind: a for a in self.executions.artifacts(owner, run.id)}
        if "effect" not in artifacts or "effect_samples" not in artifacts:
            raise ApplicationError(
                "PREVIEW_NOT_READY", "La vista previa todavía no ha terminado.", 409
            )
        return (
            json.loads(self.objects.read(artifacts["effect"].content)),
            json.loads(self.objects.read(artifacts["effect_samples"].content)),
        )

    def apply_status(self, owner: UUID, run: Execution, approval: UUID) -> ApplyStatus | None:
        applied = self.executions.find_request(
            owner, run.project_id, "cleaning_apply", approval, apply_fingerprint(approval)
        )
        if not applied:
            return None
        return ApplyStatus(
            execution_id=applied.id,
            state=applied.state,
            error_code=applied.error_code,
            error_message=applied.error_message,
        )

    def get_preview(self, owner: UUID, execution: UUID) -> PreviewView:
        run = self.preview_run(owner, execution)
        assert run.plan
        effect: dict[str, Any] | None = None
        samples: list[Any] = []
        if run.state == "succeeded":
            effect, samples = self.effect(owner, run)
        approval = self.approvals.active(run.id)
        return PreviewView(
            execution_id=run.id,
            plan_revision_id=run.plan.id,
            project_id=run.project_id,
            version_id=run.version_id,
            state=run.state,
            error_code=run.error_code,
            error_message=run.error_message,
            effect_sha256=effect["effect_sha256"] if effect else None,
            manifest=EffectManifest.model_validate(effect["manifest"]) if effect else None,
            samples=[EffectSample.model_validate(sample) for sample in samples],
            approval=approval,
            apply=self.apply_status(owner, run, approval.id) if approval else None,
            failure=self.failure(owner, run),
            column_effects=[ColumnEffectCounts.model_validate(item) for item in effect["breakdown"]]
            if effect and "breakdown" in effect
            else None,
        )

    def failure(self, owner: UUID, run: Execution) -> PreviewFailure | None:
        """Valores que no convierten o claves nulas rechazadas: nada se publica y la
        vista previa los muestra para corregir los datos o el plan."""
        if run.state != "failed":
            return None
        detail = self.executions.error_details(owner, run.id)
        if detail is None:
            return None
        code, details = detail
        return PreviewFailure.model_validate({"code": code, **details})

    def approve(
        self,
        owner: UUID,
        execution: UUID,
        effect_sha256: str,
        correlation: str,
        before_commit: Callable[[ApprovalView], None] | None = None,
    ) -> ApprovalView:
        """Aprueba el efecto exacto. `before_commit` (Fase 11B) permite registrar en la misma
        transacción que la aprobación la concedió una política."""
        try:
            run = self.preview_run(owner, execution)
            assert run.plan
            self.plans.require_write(owner, run.project_id)
            if run.state != "succeeded":
                raise ApplicationError(
                    "PREVIEW_NOT_READY", "La vista previa todavía no ha terminado.", 409
                )
            effect, _ = self.effect(owner, run)
            if effect["effect_sha256"] != effect_sha256:
                raise ApplicationError(
                    "APPROVAL_SCOPE_MISMATCH",
                    "El efecto aprobado no coincide con el de esta vista previa.",
                    409,
                )
            current = self.approvals.active(run.id)
            if current:  # Aprobar dos veces el mismo efecto devuelve la aprobación vigente.
                self.uow.rollback()
                return current
            manifest = EffectManifest.model_validate(effect["manifest"])
            semantic = manifest.semantic_ref["id"] if manifest.semantic_ref else None
            approval = ApprovalView(
                id=uuid4(),
                plan_revision_id=run.plan.id,
                preview_execution_id=run.id,
                effect_sha256=effect_sha256,
                input_artifact_sha256=str(manifest.input["artifact_sha256"]),
                semantic_revision_id=UUID(semantic) if semantic else None,
                config_sha256=manifest.config_sha256,
                environment_sha256=manifest.environment_sha256,
                approved_by=owner,
                approved_at=datetime.now(UTC),
                revoked_at=None,
                status="active",
            )
            self.approvals.add(approval, correlation)
            if before_commit:
                before_commit(approval)
            self.uow.commit()
            return approval
        except Exception:
            self.uow.rollback()
            raise

    def revoke(self, owner: UUID, approval_id: UUID, correlation: str) -> ApprovalView:
        try:
            approval = self.approvals.get(owner, approval_id)
            if approval.revoked_at:
                self.uow.rollback()
                return approval
            run = self.preview_run(owner, approval.preview_execution_id)
            self.plans.require_write(owner, run.project_id)
            applied = self.apply_status(owner, run, approval.id)
            if applied and applied.state == "running":
                raise ApplicationError(
                    "APPLY_IN_PROGRESS",
                    "La aplicación ya empezó; espera a que termine o cancélala.",
                    409,
                )
            if applied and applied.state == "succeeded":
                raise ApplicationError(
                    "APPROVAL_ALREADY_APPLIED", "La aprobación ya se aplicó.", 409
                )
            self.approvals.revoke(approval.id, datetime.now(UTC), correlation)
            if applied and applied.state == "queued":
                # Cancela la aplicación en cola en la misma transacción que la revocación.
                self.executions.cancel(owner, applied.execution_id)
            else:
                self.uow.commit()
            return self.approvals.get(owner, approval.id)
        except Exception:
            self.uow.rollback()
            raise

    def apply(self, owner: UUID, approval_id: UUID, correlation: str) -> Execution:
        try:
            self.plans.lock_owner(owner)
            approval = self.approvals.get(owner, approval_id)
            run = self.preview_run(owner, approval.preview_execution_id)
            fingerprint = apply_fingerprint(approval.id)
            existing = self.executions.find_request(
                owner, run.project_id, "cleaning_apply", approval.id, fingerprint
            )
            if existing:
                self.uow.rollback()
                return existing
            if approval.revoked_at:
                raise ApplicationError("APPROVAL_REVOKED", "La aprobación fue revocada.", 409)
            self.plans.require_write(owner, run.project_id)
            applied = self.executions.enqueue_existing_plan(
                owner,
                run.project_id,
                run.version_id,
                approval.id,
                fingerprint,
                self.executions.plan_revision(owner, approval.plan_revision_id),
                correlation,
                "cleaning_apply",
            )
            self.uow.commit()
            return applied
        except Exception:
            self.uow.rollback()
            raise

    def lineage(self, owner: UUID, version_id: UUID) -> LineageView:
        version = self.datasets.get(owner, version_id)
        lineage = self.datasets.lineage(owner, version_id)
        if lineage is None:
            return LineageView(
                version_id=version.id,
                kind=version.kind,
                parent_version_id=None,
                producer_execution_id=None,
                plan_revision_id=None,
                effect_sha256=None,
                operations=[],
            )
        producer = self.executions.get(owner, lineage.producer_execution_id)
        assert producer.plan
        effect, _ = self.effect(owner, producer)
        return LineageView(
            version_id=version.id,
            kind=version.kind,
            parent_version_id=lineage.parent_version_id,
            producer_execution_id=producer.id,
            plan_revision_id=producer.plan.id,
            effect_sha256=effect["effect_sha256"],
            operations=[
                LineageOperation(
                    step_id=step["id"],
                    operation=step["operation"],
                    version=step["version"],
                    parameters=step.get("parameters", {}),
                )
                for step in producer.plan.content["steps"]
            ],
        )


class ProposalSource(Protocol):
    """Hechos de la tabla para proponer una limpieza (bootstrap los reúne de understanding e
    ingestion: columnas, revisión semántica vigente y diagnóstico de calidad)."""

    def proposal_inputs(self, owner: UUID, artifact: UUID) -> ProposalInputs: ...


class CleaningProposals:
    """Propuesta inicial de limpieza de una tabla publicada (Fase 11A): misma propuesta para la
    interfaz y la automatización. Sólo lee; no guarda planes ni ejecuta nada."""

    def __init__(self, source: ProposalSource) -> None:
        self.source = source

    def get(self, owner: UUID, artifact: UUID) -> CleaningProposal:
        return propose(self.source.proposal_inputs(owner, artifact))
