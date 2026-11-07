"""Propuesta inicial de limpieza (Fase 11A): reglas puras, sin Polars ni SQL.

Antes se calculaba en el frontend (`initialDraft` y `draftSteps` de `features/cleaning`); ahora es
la única fuente para la interfaz, la automatización (Fase 11B–11C) y el copiloto:

- Q-003 (celdas sólo de espacios) → recortar esa columna, sólo si es texto.
- Q-001 (celdas vacías) → excluir los registros con nulo en esa columna, de cualquier tipo.
- Q-002 (filas duplicadas) → deduplicar por todas las columnas agrupando nulos (mismo criterio).
- Marcadores de nulo → los confirmados en la revisión semántica vigente, sólo en columnas de texto.
- Nunca se propone una conversión de tipo: sólo se indica el tipo sugerido por el perfil.

Orden fijo de los pasos: marcadores → recortar → convertir → excluir nulos → deduplicar.
"""

import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.planning.contracts import InputRef, PlanStep, StepRef
from dataflow.platform.data_types import DataType

PROPOSAL_VERSION: Literal["cleaning-proposal@1"] = "cleaning-proposal@1"
NullKeys = Literal["reject", "group_nulls"]


class ProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NullTokenProposal(ProposalModel):
    column_id: UUID
    tokens: list[str] = Field(min_length=1, max_length=20)


class DedupeProposal(ProposalModel):
    enabled: bool
    column_ids: list[UUID]
    null_keys: NullKeys


class CleaningDraft(ProposalModel):
    """Selección editable por columna; `draft_steps` la convierte en pasos del catálogo."""

    null_tokens: list[NullTokenProposal]
    trim: list[UUID]
    drop_nulls: list[UUID]
    dedupe: DedupeProposal


class ProposalSemanticRef(ProposalModel):
    id: UUID
    revision: int
    content_sha256: str


class CleaningProposal(ProposalModel):
    proposal_version: Literal["cleaning-proposal@1"] = PROPOSAL_VERSION
    representation_id: UUID
    table_sha256: str
    semantic_revision: ProposalSemanticRef | None
    draft: CleaningDraft
    steps: list[PlanStep]


@dataclass(frozen=True)
class ProposalColumn:
    id: UUID
    name: str
    technical_type: DataType


@dataclass(frozen=True)
class ProposalIssue:
    rule: str
    column: str | None  # nombre de columna, como en el diagnóstico csv-quality-v1


@dataclass(frozen=True)
class ConfirmedTokens:
    """Marcadores de nulo de una columna confirmada con política `explicit_tokens`."""

    column_id: UUID
    tokens: list[str]


@dataclass(frozen=True)
class ProposalInputs:
    representation_id: UUID
    table_sha256: str
    semantic_revision: ProposalSemanticRef | None
    columns: list[ProposalColumn]
    issues: list[ProposalIssue]
    confirmed_tokens: list[ConfirmedTokens]


def propose_draft(
    columns: list[ProposalColumn],
    issues: list[ProposalIssue],
    confirmed_tokens: list[ConfirmedTokens],
) -> CleaningDraft:
    def flagged(rule: str, any_type: bool) -> list[UUID]:
        names = {issue.column for issue in issues if issue.rule == rule}
        return [
            column.id
            for column in columns
            if column.name in names and (any_type or column.technical_type == "string")
        ]

    text = {column.id for column in columns if column.technical_type == "string"}
    order = {column.id: index for index, column in enumerate(columns)}
    tokens = sorted(
        (
            NullTokenProposal(column_id=item.column_id, tokens=list(dict.fromkeys(item.tokens)))
            for item in confirmed_tokens
            if item.column_id in text and item.tokens
        ),
        key=lambda proposal: order[proposal.column_id],
    )
    return CleaningDraft(
        null_tokens=tokens,
        trim=flagged("Q-003", any_type=False),
        drop_nulls=flagged("Q-001", any_type=True),
        dedupe=DedupeProposal(
            enabled=any(issue.rule == "Q-002" for issue in issues),
            column_ids=[column.id for column in columns],
            null_keys="group_nulls",
        ),
    )


def draft_steps(draft: CleaningDraft, columns: list[ProposalColumn]) -> list[PlanStep]:
    """Pasos del catálogo en el orden fijo. Columnas con los mismos marcadores comparten paso."""
    steps: list[PlanStep] = []

    def add(step_id: str, operation: str, parameters: dict[str, object]) -> None:
        source = StepRef(step_id=steps[-1].id) if steps else InputRef()
        steps.append(
            PlanStep(
                id=step_id,
                operation=operation,
                version=1,
                input=source,
                parameters=json.loads(json.dumps(parameters, default=str)),
            )
        )

    by_column = {item.column_id: item.tokens for item in draft.null_tokens}
    groups: dict[str, list[UUID]] = {}
    for column in columns:
        if by_column.get(column.id):
            groups.setdefault(json.dumps(by_column[column.id]), []).append(column.id)
    for index, (key, ids) in enumerate(groups.items(), start=1):
        add(
            f"null_tokens_{index}",
            "cleaning.normalize_null_tokens",
            {"column_ids": ids, "tokens": json.loads(key)},
        )
    if draft.trim:
        add("trim", "cleaning.trim_whitespace", {"column_ids": draft.trim})
    if draft.drop_nulls:
        add(
            "drop_nulls",
            "cleaning.filter_rows",
            {"column_ids": draft.drop_nulls, "predicate": "is_null", "match": "any"},
        )
    if draft.dedupe.enabled and draft.dedupe.column_ids:
        add(
            "dedupe",
            "cleaning.deduplicate",
            {
                "column_ids": draft.dedupe.column_ids,
                "keep": "first",
                "null_keys": draft.dedupe.null_keys,
            },
        )
    return steps


def propose(inputs: ProposalInputs) -> CleaningProposal:
    draft = propose_draft(inputs.columns, inputs.issues, inputs.confirmed_tokens)
    return CleaningProposal(
        representation_id=inputs.representation_id,
        table_sha256=inputs.table_sha256,
        semantic_revision=inputs.semantic_revision,
        draft=draft,
        steps=draft_steps(draft, inputs.columns),
    )
