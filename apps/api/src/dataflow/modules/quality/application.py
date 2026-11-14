"""Casos de uso de csv-quality-v2: guardar revisiones de reglas, consultar su aplicabilidad y
leer los informes publicados por quality.evaluate@2."""

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from dataflow.modules.quality.domain import required_types, validate_rules
from dataflow.modules.quality.rules_contracts import (
    BaseTable,
    QualityRulesReport,
    RulesetContent,
    RulesetContext,
    RulesetDraft,
    RulesetFacts,
    RulesetReference,
    RulesetRepository,
    RulesetRevision,
    RulesetRevisionPage,
    RulesetSummary,
    SaveRulesetResponse,
)
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class QualityTables(Protocol):
    """Puerto implementado en bootstrap: tablas publicadas, permisos y artefactos."""

    def table(self, owner: UUID, artifact: UUID) -> tuple[UUID, BaseTable, list[dict[str, Any]]]:
        """(proyecto, referencia exacta, columnas) de una tabla del propietario."""
        ...

    def require_project(self, owner: UUID, project: UUID, writable: bool = False) -> None: ...
    def rules_report(self, owner: UUID, execution: UUID) -> bytes | None: ...


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def content_sha256(content: RulesetContent) -> str:
    return digest("quality_ruleset", content.model_dump(mode="json"))


def reference(revision: RulesetRevision) -> RulesetReference:
    return RulesetReference(
        id=revision.id, revision=revision.revision, content_sha256=revision.content_sha256
    )


class RulesetService:
    def __init__(self, repository: RulesetRepository, tables: QualityTables, uow: UnitOfWork):
        self.repository, self.tables, self.uow = repository, tables, uow

    def summary(
        self, family: UUID, columns: list[dict[str, Any]], artifact: UUID
    ) -> RulesetSummary | None:
        head = self.repository.head(family)
        if head is None:
            return None
        revision, count = head
        problems = validate_rules(revision.content.rules, columns)
        return RulesetSummary(
            family_id=family,
            head=revision,
            revision_count=count,
            anchored_here=revision.content.base_table.artifact_id == artifact,
            applicable=not problems,
            problems=problems,
        )

    def context(self, owner: UUID, artifact: UUID) -> RulesetContext:
        """Conjunto anclado a esta tabla y los demás del proyecto, con su aplicabilidad (una
        derivada conserva los IDs de columna de su origen y puede usar sus reglas)."""
        project, _, columns = self.tables.table(owner, artifact)
        own_family = self.repository.family_for_table(owner, artifact)
        own = self.summary(own_family, columns, artifact) if own_family else None
        others = [
            summary
            for family in self.repository.families(owner, project)
            if family != own_family and (summary := self.summary(family, columns, artifact))
        ]
        return RulesetContext(artifact_id=artifact, own=own, others=others)

    def save(
        self,
        owner: UUID,
        artifact: UUID,
        table_sha256: str,
        expected: int,
        draft: RulesetDraft,
        key: UUID,
        correlation: str,
    ) -> SaveRulesetResponse:
        try:
            project, base, columns = self.tables.table(owner, artifact)
            self.tables.require_project(owner, project, writable=True)
            if base.artifact_sha256 != table_sha256:
                raise ApplicationError(
                    "INPUT_MISMATCH", "La tabla no coincide con la consultada.", 409
                )
            problems = validate_rules(draft.rules, columns)
            if problems:
                raise ApplicationError(
                    "QUALITY_RULESET_INVALID",
                    " ".join(problem.message for problem in problems),
                    422,
                )
            content = RulesetContent(name=draft.name, rules=draft.rules, base_table=base)
            fingerprint = digest(
                "quality_ruleset_request",
                {"expected_revision": expected, "content": content.model_dump(mode="json")},
            )
            family, head = self.repository.lock_family(owner, project, base)
            replayed = self.repository.replay(family, key, fingerprint)
            if replayed:
                self.uow.rollback()
                return SaveRulesetResponse(revision=replayed, changed=True)
            if head != expected:
                raise ApplicationError(
                    "QUALITY_RULESET_CONFLICT", "El conjunto de reglas cambió: recarga.", 409
                )
            current = self.repository.head(family)
            if current and current[0].content == content:
                self.uow.rollback()  # Sin cambios no se crea revisión.
                return SaveRulesetResponse(revision=current[0], changed=False)
            revision = RulesetRevision(
                id=uuid4(),
                family_id=family,
                project_id=project,
                revision=head + 1,
                previous_revision_id=current[0].id if current else None,
                content=content,
                content_sha256=content_sha256(content),
                created_by=owner,
                created_at=datetime.now(UTC),
            )
            self.repository.append(family, expected, revision, correlation)
            self.repository.remember(family, key, fingerprint, revision.id)
            self.uow.commit()
            return SaveRulesetResponse(revision=revision, changed=True)
        except Exception:
            self.uow.rollback()
            raise

    def revision(self, owner: UUID, revision: UUID) -> RulesetRevision:
        value = self.repository.revision(owner, revision)
        self.tables.require_project(owner, value.project_id)
        return value

    def history(self, owner: UUID, family: UUID) -> RulesetRevisionPage:
        items = self.repository.history(owner, family)
        return RulesetRevisionPage(items=items, total=len(items))

    def facts(self, owner: UUID, revision: UUID) -> RulesetFacts | None:
        """Para validar planes: hash y tipos exigidos; None si no existe o es ajena."""
        try:
            value = self.repository.revision(owner, revision)
        except ApplicationError:
            return None
        return RulesetFacts(
            content_sha256=value.content_sha256,
            column_types={
                column: sorted(types)
                for column, types in required_types(value.content.rules).items()
            },
        )

    def report(self, owner: UUID, execution: UUID) -> QualityRulesReport:
        content = self.tables.rules_report(owner, execution)
        if content is None:
            raise ApplicationError(
                "RESULT_NOT_READY", "El resultado de las reglas no está disponible.", 409
            )
        return QualityRulesReport.model_validate(json.loads(content))
