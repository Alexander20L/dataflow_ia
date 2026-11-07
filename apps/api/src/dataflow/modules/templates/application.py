from typing import Any
from uuid import UUID

from dataflow.modules.templates.contracts import (
    CandidateList,
    MappingContent,
    MappingMatch,
    MappingRepository,
    MappingRevision,
    TableColumn,
    TemplateTables,
)
from dataflow.modules.templates.domain import ORDER, candidates, compatibility, semantic_draft
from dataflow.modules.templates.domain import validate as validate_mapping
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


class TemplateService:
    """Moldes candidatos y mapeos confirmados (Fase 11D)."""

    def __init__(
        self, repository: MappingRepository, tables: TemplateTables, uow: UnitOfWork
    ) -> None:
        self.repository, self.tables, self.uow = repository, tables, uow

    def candidates(self, owner: UUID, artifact: UUID) -> CandidateList:
        project, columns = self.tables.columns(owner, artifact)
        mappings = {m.template: m for m in self.repository.heads(owner, project)}
        result = []
        for candidate in candidates(columns):
            mapping = mappings.get(candidate.template)
            if mapping:
                check = compatibility(mapping.content, columns)
                candidate = candidate.model_copy(
                    update={
                        "mapping_revision_id": mapping.id,
                        "compatible": check.compatible,
                        "problems": check.problems,
                    }
                )
            result.append(candidate)
        return CandidateList(representation_id=artifact, candidates=result)

    def mappings(self, owner: UUID, project: UUID) -> list[MappingRevision]:
        self.tables.require_project(owner, project, writable=False)
        return self.repository.heads(owner, project)

    def revision(self, owner: UUID, revision: UUID) -> MappingRevision:
        return self.repository.get(owner, revision)

    def save(
        self,
        owner: UUID,
        project: UUID,
        expected: int,
        content: MappingContent,
        key: UUID,
        correlation: str,
    ) -> MappingRevision:
        problems = validate_mapping(content)
        if problems:
            raise ApplicationError("TEMPLATE_MAPPING_INVALID", " ".join(problems), 422)
        content_sha256 = digest("template_mapping", content.model_dump(mode="json"))
        fingerprint = digest(
            "template_mapping_request", {"expected": expected, "content": content_sha256}
        )
        try:
            self.tables.require_project(owner, project, writable=True)
            self.repository.lock(project, content.template)
            replayed = self.repository.replay(owner, project, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return replayed
            head = self.repository.head(owner, project, content.template)
            if (head.revision if head else 0) != expected:
                raise ApplicationError(
                    "TEMPLATE_MAPPING_CONFLICT",
                    "El mapeo cambió mientras tanto. Recárgalo y vuelve a intentarlo.",
                    409,
                )
            if head and head.content_sha256 == content_sha256:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return head
            saved = self.repository.append(
                owner, project, content, content_sha256, key, fingerprint, correlation
            )
            self.uow.commit()
            return saved
        except Exception:
            self.uow.rollback()
            raise

    def match(self, owner: UUID, project: UUID, columns: list[TableColumn]) -> MappingMatch:
        """Mapeo confirmado del proyecto que la tabla cumple (en el orden de los moldes). Si hay
        mapeos y ninguno es compatible, `incompatible` con sus problemas; si no hay, `none`."""
        heads: dict[str, MappingRevision] = {
            m.template: m for m in self.repository.heads(owner, project)
        }
        problems: list[str] = []
        for template in ORDER:
            mapping = heads.get(template)
            if mapping is None:
                continue
            check = compatibility(mapping.content, columns)
            if check.compatible:
                return MappingMatch("compatible", mapping, [], check.casts)
            problems.extend(f"{template}: {problem}" for problem in check.problems)
        if problems:
            return MappingMatch("incompatible", None, problems, [])
        return MappingMatch("none", None, [], [])

    def semantic_draft(
        self, mapping: MappingRevision, columns: list[TableColumn], base: dict[str, Any]
    ) -> dict[str, Any]:
        return semantic_draft(mapping.content, columns, base)
