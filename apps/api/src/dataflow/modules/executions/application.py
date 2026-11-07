import time
from typing import Any
from uuid import UUID

from dataflow.modules.executions.contracts import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Execution,
    ExecutionRepository,
    InputKind,
    InputResolver,
    Lease,
    PlanBinding,
    PlanFinalizer,
    PlanRevision,
    PlanStepSpec,
    PublicationHook,
    RunKind,
    StepExecutor,
    StepInput,
    StepRegistry,
    UserPlan,
)
from dataflow.modules.executions.domain import plan_input_kind, plan_steps
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class Executions:
    def __init__(self, repository: ExecutionRepository, uow: UnitOfWork) -> None:
        self.repository, self.uow = repository, uow

    def find_request(
        self, owner: UUID, project: UUID, kind: RunKind, key: UUID, fingerprint: str
    ) -> Execution | None:
        return self.repository.find_request(owner, project, kind, key, fingerprint)

    def enqueue(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        kind: RunKind,
        key: UUID,
        fingerprint: str,
        plan: PlanRevision,
        correlation: str,
        input_artifact: UUID | None = None,
        input_sha256: str | None = None,
    ) -> Execution:
        if digest("plan", plan.content) != plan.content_sha256:
            raise ApplicationError("PLAN_HASH_MISMATCH", "El plan no coincide con su hash.", 409)
        _ = plan.config
        self.ensure_capacity(owner, project, kind)
        return self.repository.enqueue(
            owner,
            project,
            version,
            kind,
            key,
            fingerprint,
            plan,
            correlation,
            input_artifact,
            input_sha256,
        )

    def enqueue_existing_plan(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        key: UUID,
        fingerprint: str,
        plan: UserPlan,
        correlation: str,
        kind: RunKind = "plan",
    ) -> Execution:
        """Encola una revisión de usuario ya guardada; no inserta ni copia el plan."""
        if digest("plan", plan.revision.content) != plan.revision.content_sha256:
            raise ApplicationError("PLAN_HASH_MISMATCH", "El plan no coincide con su hash.", 409)
        _ = plan.revision.config
        self.ensure_capacity(owner, project, kind)
        return self.repository.enqueue_existing_plan(
            owner,
            project,
            version,
            key,
            fingerprint,
            plan.revision.id,
            correlation,
            plan.binding.input_artifact_id,
            plan.binding.input_artifact_sha256,
            kind,
        )

    def enqueue_followup(
        self,
        owner: UUID,
        project: UUID,
        version: UUID,
        key: UUID,
        fingerprint: str,
        plan: PlanRevision,
        correlation: str,
        input_artifact: UUID,
        input_sha256: str,
        kind: RunKind = "table_analysis",
    ) -> Execution:
        """Análisis de sistema encolado dentro de la publicación de otra ejecución (misma
        transacción). No aplica el límite de trabajos activos: la ejecución que publica aún
        cuenta como activa y la publicación no debe fallar por ello."""
        if digest("plan", plan.content) != plan.content_sha256:
            raise ApplicationError("PLAN_HASH_MISMATCH", "El plan no coincide con su hash.", 409)
        return self.repository.enqueue(
            owner,
            project,
            version,
            kind,
            key,
            fingerprint,
            plan,
            correlation,
            input_artifact,
            input_sha256,
        )

    def save_plan_revision(self, plan: PlanRevision, binding: PlanBinding) -> None:
        """Escritura dentro de la transacción del llamador (sin commit)."""
        if digest("plan", plan.content) != plan.content_sha256:
            raise ApplicationError("PLAN_HASH_MISMATCH", "El plan no coincide con su hash.", 409)
        self.repository.save_plan_revision(plan, binding)

    def plan_revision(self, owner: UUID, revision: UUID) -> UserPlan:
        return self.repository.plan_revision(owner, revision)

    def lock_plan_family(self, owner: UUID, family: UUID) -> UserPlan:
        return self.repository.lock_plan_family(owner, family)

    def plans_for_project(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[UserPlan], int]:
        return self.repository.plans_for_project(owner, project, limit, offset)

    def ensure_capacity(self, owner: UUID, project: UUID, kind: RunKind) -> None:
        if self.repository.active_count(owner) >= 3:
            raise ApplicationError("QUEUE_LIMIT", "Ya tienes tres trabajos en curso.", 409)
        if kind == "csv_import" and self.repository.active_count(owner, project, "csv_import") >= 1:
            raise ApplicationError(
                "PROJECT_BUSY", "Este proyecto ya tiene una carga en curso.", 409
            )

    def get(self, owner: UUID, execution: UUID) -> Execution:
        return self.repository.get(owner, execution)

    def for_version(self, owner: UUID, version: UUID) -> list[Execution]:
        return self.repository.for_version(owner, version)

    def representations(self, owner: UUID, version: UUID) -> list[Artifact]:
        return self.repository.representations(owner, version)

    def counts(self, owner: UUID, kind: RunKind = "csv_import") -> dict[str, int]:
        return self.repository.counts(owner, kind)

    def artifact(self, owner: UUID, artifact: UUID) -> Artifact:
        return self.repository.artifact(owner, artifact)

    def artifacts(self, owner: UUID, execution: UUID) -> list[Artifact]:
        return self.repository.artifacts(owner, execution)

    def attempts(self, owner: UUID, execution: UUID) -> list[dict[str, Any]]:
        return self.repository.attempts(owner, execution)

    def error_details(self, owner: UUID, execution: UUID) -> tuple[str, dict[str, Any]] | None:
        """Detalle estructurado del último intento fallido, si el paso lo aportó."""
        return self.repository.error_details(owner, execution)

    def cancel(self, owner: UUID, execution: UUID) -> Execution:
        try:
            result = self.repository.cancel(owner, execution)
            self.uow.commit()
            return result
        except Exception:
            self.uow.rollback()
            raise


class ExecutionRunner:
    def __init__(
        self,
        repository: ExecutionRepository,
        uow: UnitOfWork,
        kinds: set[RunKind],
        inputs: dict[InputKind, InputResolver],
        operations: StepRegistry,
        publisher: PublicationHook,
        environment: dict[str, Any],
        finalizers: dict[RunKind, PlanFinalizer] | None = None,
    ) -> None:
        # `kinds` es explícito: un worker sólo reclama tipos de ejecución que sabe atender.
        self.repository, self.uow, self.kinds = repository, uow, kinds
        self.inputs, self.operations = inputs, operations
        self.publisher, self.environment = publisher, environment
        self.finalizers = finalizers or {}

    def run_once(self) -> bool:
        try:
            lease = self.repository.claim(self.kinds, self.environment)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        if not lease:
            return False
        try:
            assert lease.execution.plan
            content = lease.execution.plan.content
            steps = self.resolve(plan_steps(content))
            source = self.inputs[plan_input_kind(content)].prepare(lease)
            finalizer = self.finalizers.get(lease.execution.kind)
            if not finalizer and any(executor.transforms_data for _, executor in steps):
                # Una transformación sólo se ejecuta con vista previa y aprobación.
                raise ApplicationError(
                    "APPROVAL_REQUIRED", "La limpieza requiere vista previa y aprobación.", 409
                )
            context = finalizer.prepare(lease) if finalizer else None
            for step, executor in steps:
                # Un paso puede leer metadatos inmutables (p. ej. reglas) antes del cómputo.
                prepare = getattr(executor, "prepare", None)
                if prepare is not None:
                    prepare(lease, step)
            self.uow.rollback()  # Cierra la lectura de metadatos antes de los subprocesos.
            deadline = self.deadline(lease)
            outputs, final = self.compute(lease, steps, source, deadline)
            if finalizer:
                if outputs or final is None:
                    raise ApplicationError(
                        "OUTPUT_MANIFEST_INVALID", "La limpieza debe terminar en una tabla.", 409
                    )
                outputs = finalizer.finalize(
                    lease, context, source, final, self.remaining(deadline)
                )
                self.validate(finalizer.expected, outputs)
            else:
                self.validate_outputs(steps, outputs)
            # Misma transacción que stage/succeed: si el fencing falla, todo se revierte.
            self.publisher.prepare(lease, outputs)
            staged = self.repository.stage(lease, outputs)
            if staged is None:
                self.uow.rollback()
                return True
            self.publisher.published(lease, staged)
            if not self.repository.succeed(lease):
                self.uow.rollback()
                return True
            self.uow.commit()
        except Exception as exc:
            self.uow.rollback()
            details = None
            if isinstance(exc, ApplicationError):
                code, message, details = exc.code, exc.message, exc.details
                retryable = code in {"PROCESSING_TIMEOUT", "PROCESSING_ERROR"}
            elif isinstance(exc, OSError):
                code, message, retryable = (
                    "STORAGE_UNAVAILABLE",
                    "Almacenamiento no disponible.",
                    True,
                )
            else:
                code, message, retryable = (
                    "PROCESSING_ERROR",
                    "No se pudo completar el procesamiento.",
                    True,
                )
            try:
                self.repository.fail(lease, code, message, retryable, details)
                self.uow.commit()
            except Exception:
                self.uow.rollback()
                raise
        return True

    def resolve(self, steps: list[PlanStepSpec]) -> list[tuple[PlanStepSpec, StepExecutor]]:
        resolved = []
        for step in steps:
            executor = self.operations.executor(step.operation, step.version)
            if executor is None:
                raise ApplicationError(
                    "UNSUPPORTED_OPERATION",
                    f"Operación no disponible: {step.operation}@{step.version}.",
                    409,
                )
            resolved.append((step, executor))
        return resolved

    @staticmethod
    def deadline(lease: Lease) -> float:
        # Plazo total compartido: la suma de pasos (y del finalizador) no supera
        # timeout_seconds, de modo que la lease (120 s) cubre cálculo + margen de publicación.
        assert lease.execution.plan
        return time.monotonic() + lease.execution.plan.config.timeout_seconds

    @staticmethod
    def remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ApplicationError(
                "PROCESSING_TIMEOUT", "El procesamiento excedió el tiempo permitido.", 422
            )
        return remaining

    @classmethod
    def compute(
        cls,
        lease: Lease,
        steps: list[tuple[PlanStepSpec, StepExecutor]],
        source: StepInput,
        deadline: float | None = None,
    ) -> tuple[list[ArtifactOutput], StepInput | None]:
        """Ejecuta los pasos en orden; devuelve las salidas publicables y la tabla del último
        paso (None si el último no produce tabla)."""
        deadline = cls.deadline(lease) if deadline is None else deadline
        tables: dict[str, StepInput] = {}
        outputs: list[ArtifactOutput] = []
        final: StepInput | None = None
        for step, executor in steps:
            remaining = cls.remaining(deadline)
            if step.input_step is None:
                step_source = source
            elif step.input_step in tables:
                step_source = tables[step.input_step]
            else:
                raise ApplicationError(
                    "INVALID_STEP_REFERENCE", f"«{step.id}» no recibe una tabla.", 409
                )
            result = executor.compute(lease, step, step_source, remaining)
            outputs.extend(result.outputs)
            final = result.table
            if result.table is not None:
                tables[step.id] = result.table
        return outputs, final

    @staticmethod
    def validate_outputs(
        steps: list[tuple[PlanStepSpec, StepExecutor]], outputs: list[ArtifactOutput]
    ) -> None:
        ExecutionRunner.validate(
            {(step.id, executor.output_kind) for step, executor in steps}, outputs
        )

    @staticmethod
    def validate(expected: set[tuple[str, ArtifactKind]], outputs: list[ArtifactOutput]) -> None:
        actual = [(output.step_id, output.slot) for output in outputs]
        if (
            len(actual) != len(set(actual))
            or set(actual) != expected
            or any(o.kind != o.slot for o in outputs)
        ):
            raise ApplicationError(
                "OUTPUT_MANIFEST_INVALID", "Las salidas no corresponden al plan.", 409
            )
