from typing import Any
from uuid import UUID

from dataflow.modules.executions.contracts import (
    Artifact,
    ArtifactOutput,
    Execution,
    ExecutionRepository,
    Executor,
    PlanRevision,
    PublicationHook,
    RunKind,
)
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
        registry: dict[RunKind, Executor],
        publisher: PublicationHook,
        environment: dict[str, Any],
    ) -> None:
        self.repository, self.uow, self.registry = repository, uow, registry
        self.publisher, self.environment = publisher, environment

    def run_once(self) -> bool:
        try:
            lease = self.repository.claim(set(self.registry), self.environment)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        if not lease:
            return False
        try:
            handler = self.registry[lease.execution.kind]
            prepared = handler.prepare(lease)
            self.uow.rollback()  # Cierra la lectura de metadatos antes del subproceso.
            outputs = handler.compute(lease, prepared)
            self.validate_outputs(lease.execution, outputs)
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
            if isinstance(exc, ApplicationError):
                code, message = exc.code, exc.message
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
                self.repository.fail(lease, code, message, retryable)
                self.uow.commit()
            except Exception:
                self.uow.rollback()
                raise
        return True

    @staticmethod
    def validate_outputs(run: Execution, outputs: list[ArtifactOutput]) -> None:
        assert run.plan
        expected: set[tuple[str, str]] = set()
        for step in run.plan.content["steps"]:
            slot = {
                "ingestion.read_csv": "table",
                "understanding.profile": "profile",
                "quality.evaluate": "quality",
            }.get(step["operation"])
            if not slot:
                raise ApplicationError("UNSUPPORTED_OPERATION", "Operación no disponible.", 409)
            expected.add((step["id"], slot))
        actual = [(output.step_id, output.slot) for output in outputs]
        if (
            len(actual) != len(set(actual))
            or set(actual) != expected
            or any(o.kind != o.slot for o in outputs)
        ):
            raise ApplicationError(
                "OUTPUT_MANIFEST_INVALID", "Las salidas no corresponden al plan.", 409
            )
