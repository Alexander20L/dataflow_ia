from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from dataflow.modules.executions.public import (
    Execution,
    Executions,
    PlanBinding,
    PlanRevision,
    ProcessingConfig,
    UserPlan,
)
from dataflow.modules.planning.contracts import (
    ApplicableOperation,
    ConfirmedColumnRole,
    OperationCatalog,
    OperationDescriptor,
    PinnedTable,
    PlanDraft,
    PlanningAccess,
    PlanningFacts,
    PlanningRepository,
    PlanPage,
    PlanStep,
    PlanValidation,
    PlanView,
    SemanticRevisionRequirement,
    SemanticRole,
    TableInput,
)
from dataflow.modules.planning.domain import plan_status, validate_plan
from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class PlanningService:
    def __init__(
        self,
        executions: Executions,
        access: PlanningAccess,
        repository: PlanningRepository,
        catalog: OperationCatalog,
        uow: UnitOfWork,
        config: ProcessingConfig,
    ) -> None:
        self.executions, self.access, self.repository = executions, access, repository
        self.catalog, self.uow, self.config = catalog, uow, config

    def operations(self) -> list[OperationDescriptor]:
        return self.catalog.descriptors()

    def applicable(
        self, owner: UUID, artifact: UUID, semantic_revision: UUID | None = None
    ) -> list[ApplicableOperation]:
        table = self.access.table(owner, artifact)
        semantic_ref = (
            self.access.semantic_reference(owner, semantic_revision) if semantic_revision else None
        )
        roles = (
            self.access.confirmed_roles(owner, semantic_ref, table.input) if semantic_ref else {}
        )
        result = []
        for descriptor in self.catalog.descriptors():
            missing: list[SemanticRevisionRequirement | ConfirmedColumnRole] = []
            for requirement in descriptor.requirements:
                if isinstance(requirement, SemanticRevisionRequirement):
                    if semantic_ref is None:
                        missing.append(requirement)
                elif requirement.role not in roles.values():
                    missing.append(requirement)
            applicable = descriptor.input_kind == "table"
            result.append(
                ApplicableOperation(
                    operation=descriptor.name,
                    version=descriptor.version,
                    key=descriptor.key,
                    title=descriptor.title,
                    applicable=applicable,
                    reason=None
                    if applicable
                    else "Requiere el archivo original; los planes parten de una tabla publicada.",
                    missing_requirements=missing,
                )
            )
        return result

    def create(
        self,
        owner: UUID,
        project: UUID,
        artifact: UUID,
        artifact_sha256: str,
        draft: PlanDraft,
        key: UUID,
        correlation: str,
    ) -> PlanView:
        try:
            self.access.lock_owner(owner)
            fingerprint = request_fingerprint(
                "plan_create_request",
                {
                    "project_id": str(project),
                    "artifact_id": str(artifact),
                    "artifact_sha256": artifact_sha256,
                    "draft": draft.model_dump(mode="json"),
                },
            )
            existing = self.repository.request(project, key)
            if existing:
                if existing[0] != fingerprint:
                    raise ApplicationError(
                        "IDEMPOTENCY_CONFLICT", "La clave ya corresponde a otra solicitud.", 409
                    )
                self.uow.rollback()
                return self.get(owner, existing[1])
            self.access.require_project(owner, project, writable=True)
            table = self.access.table(owner, artifact)
            if table.project_id != project or table.input.artifact_sha256 != artifact_sha256:
                raise ApplicationError(
                    "INPUT_MISMATCH", "La tabla o su hash no corresponde al proyecto.", 409
                )
            plan = self.store(owner, uuid4(), 1, table, draft)
            self.repository.remember(project, key, owner, fingerprint, plan.revision.id)
            self.uow.commit()
            return self.get(owner, plan.revision.id)
        except Exception:
            self.uow.rollback()
            raise

    def revise(
        self, owner: UUID, family: UUID, expected_revision: int, draft: PlanDraft
    ) -> PlanView:
        try:
            head = self.executions.lock_plan_family(owner, family)
            self.access.require_project(owner, head.binding.project_id, writable=True)
            if head.head_revision != expected_revision:
                raise ApplicationError(
                    "PLAN_REVISION_CONFLICT",
                    "Existe una revisión más reciente del plan. Recárgala antes de guardar.",
                    409,
                )
            table = self.pinned(owner, head)
            content = self.content(table, draft)
            if digest("plan", content) == head.revision.content_sha256:
                self.uow.rollback()  # Sin cambios: no se crea una revisión vacía.
                return self.get(owner, head.revision.id)
            plan = self.store(owner, family, head.head_revision + 1, table, draft)
            self.uow.commit()
            return self.get(owner, plan.revision.id)
        except Exception:
            self.uow.rollback()
            raise

    def get(self, owner: UUID, revision: UUID) -> PlanView:
        plan = self.executions.plan_revision(owner, revision)
        self.access.require_project(owner, plan.binding.project_id)
        validation = self.repository.validation(plan.revision.id, self.catalog.catalog_version)
        if validation is None:
            # Sólo ocurre si cambia la versión del catálogo: se valida una vez y se conserva.
            try:
                validation = self.validate(owner, plan)
                self.repository.save_validation(plan.revision.id, validation)
                self.uow.commit()
            except Exception:
                self.uow.rollback()
                raise
        return view(plan, validation)

    def page(self, owner: UUID, project: UUID, limit: int, offset: int) -> PlanPage:
        self.access.require_project(owner, project)
        plans, total = self.executions.plans_for_project(owner, project, limit, offset)
        return PlanPage(
            items=[self.get(owner, plan.revision.id) for plan in plans],
            total=total,
            limit=limit,
            offset=offset,
        )

    def execute(self, owner: UUID, revision: UUID, key: UUID, correlation: str) -> Execution:
        try:
            self.access.lock_owner(owner)
            plan = self.executions.plan_revision(owner, revision)
            fingerprint = digest(
                "plan_execution_request",
                {
                    "plan_revision_id": str(plan.revision.id),
                    "content_sha256": plan.revision.content_sha256,
                },
            )
            existing = self.executions.find_request(
                owner, plan.binding.project_id, "plan", key, fingerprint
            )
            if existing:
                self.uow.rollback()
                return existing
            self.access.require_project(owner, plan.binding.project_id, writable=True)
            validation = self.repository.validation(
                plan.revision.id, self.catalog.catalog_version
            ) or self.validate(owner, plan)
            if not validation.valid:
                raise ApplicationError(
                    "PLAN_INCOMPLETE",
                    f"El plan tiene {len(validation.problems)} problema(s) pendiente(s) "
                    "y no se puede ejecutar.",
                    422,
                )
            table = self.pinned(owner, plan)
            run = self.executions.enqueue_existing_plan(
                owner,
                plan.binding.project_id,
                table.input.version_id,
                key,
                fingerprint,
                plan,
                correlation,
            )
            self.uow.commit()
            return run
        except Exception:
            self.uow.rollback()
            raise

    def pinned(self, owner: UUID, plan: UserPlan) -> PinnedTable:
        """Re-verifica la tabla fijada: nunca se sustituye por la versión predeterminada."""
        table = self.access.table(owner, plan.binding.input_artifact_id)
        if (
            table.input.artifact_sha256 != plan.binding.input_artifact_sha256
            or table.input.model_dump(mode="json") != plan.revision.content["input"]
        ):
            raise ApplicationError("INPUT_MISMATCH", "La tabla fijada no coincide.", 409)
        return table

    def store(
        self, owner: UUID, family: UUID, number: int, table: PinnedTable, draft: PlanDraft
    ) -> UserPlan:
        content = self.content(table, draft)
        roles = self.roles(owner, draft.semantic_ref, table.input)
        revision = PlanRevision(
            uuid4(), family, number, content, digest("plan", content), owner, datetime.now(UTC)
        )
        binding = PlanBinding(
            table.project_id,
            table.input.artifact_id,
            table.input.artifact_sha256,
            draft.semantic_ref.id if draft.semantic_ref else None,
        )
        self.executions.save_plan_revision(revision, binding)
        plan = UserPlan(revision, binding, number)
        self.repository.save_validation(revision.id, self.check(plan, table, roles))
        return plan

    def content(self, table: PinnedTable, draft: PlanDraft) -> dict[str, Any]:
        content = {
            "objective": None,
            "input": table.input.model_dump(mode="json"),
            "semantic_ref": draft.semantic_ref.model_dump(mode="json")
            if draft.semantic_ref
            else None,
            "steps": [self.normalized(step) for step in draft.steps],
            "config": self.config.model_dump(),
        }
        try:
            digest("plan", content)
        except ValueError as exc:
            raise ApplicationError(
                "PLAN_NOT_CANONICAL",
                "Los parámetros usan claves o valores no admitidos (claves a-z/0-9/_, "
                "sin decimales en coma flotante).",
                422,
            ) from exc
        return content

    def normalized(self, step: PlanStep) -> dict[str, Any]:
        # Parámetros válidos se guardan completos (con valores por defecto) para que el plan
        # sea explícito; los incompletos se conservan tal cual y la validación los informa.
        value = step.model_dump(mode="json")
        descriptor = self.catalog.descriptor(step.operation, step.version)
        if descriptor is not None:
            try:
                value["parameters"] = descriptor.parameters.model_validate(
                    step.parameters
                ).model_dump(mode="json")
            except ValidationError:
                pass
        return value

    def roles(
        self, owner: UUID, reference: SemanticReference | None, table: TableInput
    ) -> dict[UUID, SemanticRole]:
        return self.access.confirmed_roles(owner, reference, table) if reference else {}

    def validate(self, owner: UUID, plan: UserPlan) -> PlanValidation:
        table = self.pinned(owner, plan)
        reference = plan.revision.content.get("semantic_ref")
        semantic_ref = SemanticReference.model_validate(reference) if reference else None
        return self.check(plan, table, self.roles(owner, semantic_ref, table.input))

    def check(
        self, plan: UserPlan, table: PinnedTable, roles: dict[UUID, SemanticRole]
    ) -> PlanValidation:
        content = plan.revision.content
        draft = PlanDraft(semantic_ref=content["semantic_ref"], steps=content["steps"])
        facts = PlanningFacts(
            input_kind="table",
            column_ids=table.column_ids,
            semantic_pinned=draft.semantic_ref is not None,
            confirmed_roles=roles,
        )
        problems = validate_plan(draft, self.catalog, facts)
        return PlanValidation(
            catalog_version=self.catalog.catalog_version,
            status=plan_status(problems),
            valid=not problems,
            problems=problems,
            validated_at=datetime.now(UTC),
        )


def request_fingerprint(domain: str, payload: dict[str, Any]) -> str:
    try:
        return digest(domain, payload)
    except ValueError as exc:
        raise ApplicationError(
            "PLAN_NOT_CANONICAL", "Los parámetros usan claves o valores no admitidos.", 422
        ) from exc


def view(plan: UserPlan, validation: PlanValidation) -> PlanView:
    content = plan.revision.content
    return PlanView(
        id=plan.revision.id,
        family_id=plan.revision.family_id,
        revision=plan.revision.revision,
        head_revision=plan.head_revision,
        project_id=plan.binding.project_id,
        input=TableInput.model_validate(content["input"]),
        semantic_ref=content["semantic_ref"],
        steps=content["steps"],
        content=content,
        content_sha256=plan.revision.content_sha256,
        created_by=plan.revision.created_by,
        created_at=plan.revision.created_at,
        validation=validation,
    )
