"""Fase 11A: propuesta inicial de limpieza calculada en el servidor.

Las reglas reproducen las que tenía el frontend (`initialDraft` y `draftSteps` de
`features/cleaning/proposal.tsx`) antes de moverlas: misma selección por columna y mismos pasos.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_cleaning_api import Flow

from dataflow.modules.cleaning.proposal import (
    CleaningDraft,
    ConfirmedTokens,
    DedupeProposal,
    NullTokenProposal,
    ProposalColumn,
    ProposalInputs,
    ProposalIssue,
    draft_steps,
    propose,
    propose_draft,
)
from dataflow.modules.datasets.objects import LocalObjects

ID, NAME, AMOUNT, DAY, FLAG = (UUID(int=n) for n in range(1, 6))
COLUMNS = [
    ProposalColumn(id=ID, name="id", technical_type="string"),
    ProposalColumn(id=NAME, name="nombre", technical_type="string"),
    ProposalColumn(id=AMOUNT, name="importe", technical_type="decimal"),
    ProposalColumn(id=DAY, name="fecha", technical_type="date"),
    ProposalColumn(id=FLAG, name="activo", technical_type="boolean"),
]
ALL = [c.id for c in COLUMNS]


def issues(*pairs: tuple[str, str | None]) -> list[ProposalIssue]:
    return [ProposalIssue(rule=rule, column=column) for rule, column in pairs]


def test_quality_issues_map_to_trim_drop_and_dedupe() -> None:
    draft = propose_draft(
        COLUMNS,
        issues(
            ("Q-003", "nombre"),
            ("Q-003", "importe"),  # tipada: no se recorta
            ("Q-001", "importe"),  # Q-001 vale para cualquier tipo
            ("Q-001", "id"),
            ("Q-002", None),
        ),
        [],
    )
    assert draft.trim == [NAME]
    assert draft.drop_nulls == [ID, AMOUNT]  # orden de las columnas, no del diagnóstico
    assert draft.dedupe == DedupeProposal(enabled=True, column_ids=ALL, null_keys="group_nulls")
    assert draft.null_tokens == []


def test_no_issues_proposes_nothing_and_no_steps() -> None:
    draft = propose_draft(COLUMNS, [], [])
    assert (draft.trim, draft.drop_nulls, draft.dedupe.enabled) == ([], [], False)
    assert draft_steps(draft, COLUMNS) == []


def test_unknown_column_names_are_ignored() -> None:
    draft = propose_draft(COLUMNS, issues(("Q-001", "no_existe"), ("Q-003", None)), [])
    assert (draft.trim, draft.drop_nulls) == ([], [])


def test_confirmed_tokens_only_on_text_columns_in_column_order() -> None:
    draft = propose_draft(
        COLUMNS,
        [],
        [
            ConfirmedTokens(column_id=NAME, tokens=["NA", "-", "NA"]),
            ConfirmedTokens(column_id=AMOUNT, tokens=["NA"]),  # tipada: no admite marcadores
            ConfirmedTokens(column_id=ID, tokens=["-"]),
            ConfirmedTokens(column_id=uuid4(), tokens=["x"]),  # columna ajena
            ConfirmedTokens(column_id=DAY, tokens=[]),
        ],
    )
    assert draft.null_tokens == [
        NullTokenProposal(column_id=ID, tokens=["-"]),
        NullTokenProposal(column_id=NAME, tokens=["NA", "-"]),  # sin repetidos, orden original
    ]


def step(
    step_id: str, operation: str, previous: str | None, parameters: dict[str, Any]
) -> dict[str, Any]:
    source = (
        {"kind": "input", "alias": "source"}
        if previous is None
        else {
            "kind": "step",
            "step_id": previous,
        }
    )
    return {
        "id": step_id,
        "operation": operation,
        "version": 1,
        "input": source,
        "parameters": parameters,
    }


def test_steps_follow_the_fixed_order_and_group_identical_tokens() -> None:
    draft = CleaningDraft(
        null_tokens=[
            NullTokenProposal(column_id=ID, tokens=["-"]),
            NullTokenProposal(column_id=NAME, tokens=["NA"]),
            NullTokenProposal(column_id=FLAG, tokens=["-"]),  # mismo grupo que ID
        ],
        trim=[NAME],
        drop_nulls=[AMOUNT, DAY],
        dedupe=DedupeProposal(enabled=True, column_ids=[ID, NAME], null_keys="reject"),
    )
    steps = [s.model_dump(mode="json") for s in draft_steps(draft, COLUMNS)]
    assert steps == [
        step(
            "null_tokens_1",
            "cleaning.normalize_null_tokens",
            None,
            {"column_ids": [str(ID), str(FLAG)], "tokens": ["-"]},
        ),
        step(
            "null_tokens_2",
            "cleaning.normalize_null_tokens",
            "null_tokens_1",
            {"column_ids": [str(NAME)], "tokens": ["NA"]},
        ),
        step("trim", "cleaning.trim_whitespace", "null_tokens_2", {"column_ids": [str(NAME)]}),
        step(
            "drop_nulls",
            "cleaning.filter_rows",
            "trim",
            {"column_ids": [str(AMOUNT), str(DAY)], "predicate": "is_null", "match": "any"},
        ),
        step(
            "dedupe",
            "cleaning.deduplicate",
            "drop_nulls",
            {"column_ids": [str(ID), str(NAME)], "keep": "first", "null_keys": "reject"},
        ),
    ]


def test_dedupe_without_columns_is_not_a_step() -> None:
    draft = CleaningDraft(
        null_tokens=[],
        trim=[],
        drop_nulls=[],
        dedupe=DedupeProposal(enabled=True, column_ids=[], null_keys="group_nulls"),
    )
    assert draft_steps(draft, COLUMNS) == []


def test_proposal_is_deterministic() -> None:
    inputs = ProposalInputs(
        representation_id=uuid4(),
        table_sha256="a" * 64,
        semantic_revision=None,
        columns=COLUMNS,
        issues=issues(("Q-003", "nombre"), ("Q-002", None)),
        confirmed_tokens=[],
    )
    assert propose(inputs) == propose(inputs)
    assert propose(inputs).proposal_version == "cleaning-proposal@1"


# --- API (PostgreSQL) ---


@pytest.fixture
def flow(client: TestClient, db: Session, objects: LocalObjects) -> Flow:
    return Flow(client, db, objects)


def test_api_proposal_for_the_sample_csv_saves_a_valid_plan(flow: Flow) -> None:
    client: TestClient = flow.client
    response = client.get(f"/api/v1/representations/{flow.table['id']}/cleaning-proposal")
    assert response.status_code == 200, response.text
    proposal = response.json()
    importe = flow.columns["importe"]
    assert proposal["representation_id"] == flow.table["id"]
    assert proposal["table_sha256"] == flow.table["sha256"]
    assert proposal["semantic_revision"] is None
    draft = proposal["draft"]
    # ventas_calidad.csv: importe vacío (Q-001), importe sólo espacios (Q-003), fila repetida.
    assert draft["trim"] == [importe] and draft["drop_nulls"] == [importe]
    assert draft["dedupe"] == {
        "enabled": True,
        "column_ids": [c["id"] for c in flow.table["columns"]],
        "null_keys": "group_nulls",
    }
    assert [s["id"] for s in proposal["steps"]] == ["trim", "drop_nulls", "dedupe"]

    plan = flow.plan(proposal["steps"])
    assert plan["validation"]["valid"], plan["validation"]
    preview = flow.preview(plan)
    assert preview["state"] == "succeeded"


def test_api_proposal_requires_access(flow: Flow) -> None:
    client: TestClient = flow.client
    missing = client.get(f"/api/v1/representations/{uuid4()}/cleaning-proposal")
    assert missing.status_code == 404
    client.cookies.clear()
    anonymous = client.get(f"/api/v1/representations/{flow.table['id']}/cleaning-proposal")
    assert anonymous.status_code == 401
