from datetime import UTC, datetime
from uuid import UUID, uuid4

from dataflow.modules.understanding.domain import (
    context_warnings,
    editable,
    initial_draft,
    make_content,
    suggestions,
    validate_draft,
)
from dataflow.modules.understanding.semantic_contracts import (
    Representation,
    RepresentationAccess,
    RevisionPage,
    SemanticDraft,
    SemanticReference,
    SemanticRepository,
    SemanticRevision,
    SemanticSaveResult,
    SemanticWarning,
    TableReference,
    UnderstandingContext,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class SemanticService:
    def __init__(
        self, repository: SemanticRepository, access: RepresentationAccess, uow: UnitOfWork
    ) -> None:
        self.repository, self.access, self.uow = repository, access, uow

    @staticmethod
    def verify_revision(source: Representation, revision: SemanticRevision) -> None:
        if digest("semantic", revision.content.model_dump(mode="json")) != revision.content_sha256:
            raise ApplicationError(
                "SEMANTIC_HASH_MISMATCH", "La revisión no coincide con su hash.", 409
            )
        if revision.content.table_ref != source.table_ref:
            raise ApplicationError(
                "SEMANTIC_INPUT_MISMATCH", "El contrato corresponde a otra representación.", 409
            )
        facts = [column.model_dump(mode="json") for column in source.columns]
        if len(revision.content.columns) != len(facts):
            raise ApplicationError(
                "SEMANTIC_SCHEMA_MISMATCH", "El número de columnas del contrato no coincide.", 409
            )
        actual = [
            {key: column.model_dump(mode="json")[key] for key in facts[index]}
            for index, column in enumerate(revision.content.columns)
        ]
        if actual != facts:
            raise ApplicationError(
                "SEMANTIC_SCHEMA_MISMATCH",
                "El esquema de la revisión no coincide con la tabla.",
                409,
            )

    def context(self, actor: UUID, artifact: UUID) -> UnderstandingContext:
        source = self.access.resolve(actor, artifact, with_profile=True)
        head = self.repository.head(actor, artifact)
        if head:
            self.verify_revision(source, head)
        draft = editable(head.content) if head else initial_draft(source)
        warnings = context_warnings(draft)
        key_facts = None
        if draft.key.column_ids and draft.key.review_state != "rejected":
            key_facts = self.access.key_facts(
                actor, artifact, draft.key.column_ids, draft.key.null_policy
            )
            if key_facts.duplicate_key_rows:
                warnings.append(
                    SemanticWarning(
                        code="KEY_DUPLICATES",
                        message=f"La clave tiene {key_facts.duplicate_key_rows} repeticiones. "
                        "Confirmarla no elimina registros.",
                    )
                )
            if key_facts.null_key_rows and draft.key.null_policy == "reject":
                warnings.append(
                    SemanticWarning(
                        code="KEY_NULLS",
                        message=f"Hay {key_facts.null_key_rows} filas con clave incompleta. "
                        "La política no admite nulos.",
                    )
                )
        return UnderstandingContext(
            table_ref=source.table_ref,
            columns=source.columns,
            schema_sha256=digest("schema", [c.model_dump(mode="json") for c in source.columns]),
            profile=source.profile,
            head=head,
            revision_count=head.revision if head else 0,
            editable=draft,
            suggestions=suggestions(source),
            warnings=warnings,
            key_assessment=key_facts,
        )

    def save(
        self,
        actor: UUID,
        artifact: UUID,
        sha256: str,
        expected_revision: int,
        draft: SemanticDraft,
        request_key: UUID,
        correlation: str,
    ) -> SemanticSaveResult:
        try:
            source = self.access.resolve(actor, artifact, with_profile=True)
            if source.table_ref.artifact_sha256 != sha256:
                raise ApplicationError(
                    "SEMANTIC_INPUT_MISMATCH",
                    "La tabla seleccionada cambió o su hash no coincide.",
                    409,
                )
            draft = validate_draft(source, draft)
            fingerprint = digest(
                "semantic_request",
                {
                    "actor_id": str(actor),
                    "expected_revision": expected_revision,
                    "table_sha256": sha256,
                    "draft": draft.model_dump(mode="json"),
                },
            )
            head = self.repository.head(actor, artifact)
            if head:
                replay = self.repository.replay(head.family_id, request_key, fingerprint)
                if replay:
                    self.uow.rollback()
                    return SemanticSaveResult(
                        revision=replay, head_revision=head.revision, changed=False
                    )
            self.access.require_write(actor, source.project_id)
            family, current = self.repository.lock_family(source)
            replay = self.repository.replay(family, request_key, fingerprint)
            head = self.repository.head(actor, artifact)
            if replay:
                self.uow.rollback()
                return SemanticSaveResult(revision=replay, head_revision=current, changed=False)
            if current != expected_revision:
                raise ApplicationError(
                    "SEMANTIC_REVISION_CONFLICT",
                    "Existe una revisión más reciente. Revisa los cambios antes de guardar.",
                    409,
                )
            if head:
                self.verify_revision(source, head)
            now = datetime.now(UTC)
            content = make_content(source, draft, actor, now, head.content if head else None)
            content_hash = digest("semantic", content.model_dump(mode="json"))
            changed = not head or content_hash != head.content_sha256
            if changed:
                revision = SemanticRevision(
                    id=uuid4(),
                    family_id=family,
                    revision=current + 1,
                    previous_revision_id=head.id if head else None,
                    content=content,
                    content_sha256=content_hash,
                    created_by=actor,
                    created_at=now,
                )
                self.repository.append(family, current, revision, correlation)
            else:
                assert head
                revision = head
            self.repository.remember(family, request_key, fingerprint, revision.id)
            self.uow.commit()
            return SemanticSaveResult(
                revision=revision, head_revision=revision.revision, changed=bool(changed)
            )
        except Exception:
            self.uow.rollback()
            raise

    def get(self, actor: UUID, revision_id: UUID) -> SemanticRevision:
        revision = self.repository.get(actor, revision_id)
        source = self.access.resolve(actor, revision.content.table_ref.artifact_id)
        self.verify_revision(source, revision)
        return revision

    def page(self, actor: UUID, artifact: UUID, limit: int, offset: int) -> RevisionPage:
        self.access.resolve(actor, artifact)
        return self.repository.page(actor, artifact, limit, offset)

    def resolve_for_table(
        self, actor: UUID, reference: SemanticReference, table_ref: TableReference
    ) -> None:
        revision = self.get(actor, reference.id)
        if (
            revision.revision != reference.revision
            or revision.content_sha256 != reference.content_sha256
        ):
            raise ApplicationError(
                "SEMANTIC_REFERENCE_MISMATCH",
                "La referencia no coincide con la revisión guardada.",
                409,
            )
        if revision.content.table_ref != table_ref:
            raise ApplicationError(
                "SEMANTIC_INPUT_MISMATCH", "La revisión semántica corresponde a otra tabla.", 409
            )
