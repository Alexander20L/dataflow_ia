from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from dataflow.modules.planning.contracts import (
    COLUMN_REF,
    ConfirmedColumnRole,
    IdentifierConversionGuard,
    MetricRequirement,
    OperationDescriptor,
    PlanDraft,
    PlanningFacts,
    PlanStep,
    Problem,
    SemanticRevisionRequirement,
)
from dataflow.modules.planning.domain import plan_status, validate_plan
from dataflow.modules.understanding.public import SemanticReference
from dataflow.platform.data_types import NUMERIC, TEXT, DataType


class NoParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    algorithm: Literal["column-profile-v1"] = "column-profile-v1"


class ColumnsParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[UUID] = Field(min_length=1, json_schema_extra={COLUMN_REF: True})


class MeasureParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: UUID = Field(json_schema_extra={COLUMN_REF: True})


class CastParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: UUID = Field(json_schema_extra={COLUMN_REF: True})
    type: Literal["integer", "decimal", "date", "boolean"]
    confirm: bool = False


def cast_schema(parameters: CastParameters, schema: Any) -> dict[UUID, DataType]:
    return {**schema, parameters.column: parameters.type}


DESCRIPTORS = [
    OperationDescriptor("fake.read", 1, "Leer", "source", "table", NoParameters),
    OperationDescriptor("fake.profile", 1, "Perfil", "table", "profile", ProfileParameters),
    OperationDescriptor(
        "fake.trim",
        1,
        "Recortar",
        "table",
        "table",
        ColumnsParameters,
        (SemanticRevisionRequirement(),),
        transforms_data=True,
    ),
    OperationDescriptor(
        "fake.metric",
        1,
        "Métrica",
        "table",
        "quality",
        MeasureParameters,
        (ConfirmedColumnRole(parameter="column", role="measure"),),
    ),
    OperationDescriptor(
        "fake.upper",
        1,
        "Mayúsculas",
        "table",
        "table",
        ColumnsParameters,
        transforms_data=True,
        column_types=lambda parameters: {"columns": TEXT},
    ),
    OperationDescriptor(
        "fake.cast",
        1,
        "Convertir",
        "table",
        "table",
        CastParameters,
        transforms_data=True,
        column_types=lambda parameters: {"column": TEXT},
        output_schema=cast_schema,
        identifier_guard=IdentifierConversionGuard("column", "type", "confirm", NUMERIC),
    ),
]


class FakeCatalog:
    catalog_version = "test-v1"

    def descriptors(self) -> list[OperationDescriptor]:
        return DESCRIPTORS

    def descriptor(self, name: str, version: int) -> OperationDescriptor | None:
        return next((d for d in DESCRIPTORS if (d.name, d.version) == (name, version)), None)


COLUMN, OTHER = uuid4(), uuid4()
SEMANTIC_REF = SemanticReference(id=uuid4(), revision=1, content_sha256="a" * 64)


def step(
    id: str,
    operation: str = "fake.profile",
    source: str | None = None,
    parameters: dict[str, Any] | None = None,
    version: int = 1,
) -> PlanStep:
    return PlanStep.model_validate(
        {
            "id": id,
            "operation": operation,
            "version": version,
            "input": {"kind": "step", "step_id": source} if source else {"kind": "input"},
            "parameters": parameters or {},
        }
    )


def facts(**changes: Any) -> PlanningFacts:
    values: dict[str, Any] = {"input_kind": "table", "column_ids": frozenset({COLUMN, OTHER})}
    return PlanningFacts(**{**values, **changes})


def problems(
    steps: list[PlanStep], context: PlanningFacts | None = None, pinned: bool = False
) -> list[Problem]:
    draft = PlanDraft(semantic_ref=SEMANTIC_REF if pinned else None, steps=steps)
    return validate_plan(draft, FakeCatalog(), context or facts())


def codes(result: list[Problem]) -> list[str]:
    return [problem.code for problem in result]


def trim(
    id: str = "trim", source: str | None = None, columns: list[UUID] | None = None
) -> PlanStep:
    return step(id, "fake.trim", source, {"columns": [str(c) for c in columns or [COLUMN]]})


def test_valid_plan_has_no_problems_and_is_valid() -> None:
    result = problems(
        [trim(), step("profile", source="trim")], facts(semantic_pinned=True), pinned=True
    )
    assert result == [] and plan_status(result) == "valid"


def test_empty_plan() -> None:
    result = problems([])
    assert codes(result) == ["EMPTY_PLAN"] and plan_status(result) == "incomplete"
    assert result[0].resolve_in == "plan_steps"
    assert "EMPTY_PLAN" not in codes(problems([step("profile")]))


def test_too_many_steps() -> None:
    assert "TOO_MANY_STEPS" in codes(problems([step(f"p{i}") for i in range(17)]))
    assert problems([step(f"p{i}") for i in range(16)]) == []


def test_duplicate_step_id() -> None:
    result = problems([step("profile"), step("profile")])
    assert codes(result) == ["DUPLICATE_STEP_ID"] and result[0].step_id == "profile"
    assert problems([step("profile"), step("profile_2")]) == []


@pytest.mark.parametrize(
    "steps",
    [
        [step("profile", source="later"), trim("later")],  # referencia adelantada
        [trim("loop", source="loop")],  # ciclo sobre sí mismo
        [step("profile", source="missing")],  # inexistente
        [step("first"), step("second", source="first")],  # consume un perfil, no una tabla
    ],
    ids=["forward", "cycle", "missing", "non_table"],
)
def test_invalid_step_reference(steps: list[PlanStep]) -> None:
    result = problems(steps, facts(semantic_pinned=True), pinned=True)
    assert "INVALID_STEP_REFERENCE" in codes(result)


def test_valid_backward_table_reference() -> None:
    result = problems([trim(), trim("again", source="trim")], facts(semantic_pinned=True), True)
    assert "INVALID_STEP_REFERENCE" not in codes(result)


def test_unsupported_operation() -> None:
    assert codes(problems([step("x", "fake.unknown")])) == ["UNSUPPORTED_OPERATION"]
    assert codes(problems([step("x", "fake.profile", version=2)])) == ["UNSUPPORTED_OPERATION"]
    assert "UNSUPPORTED_OPERATION" not in codes(problems([step("x", "fake.profile")]))


def test_unknown_operation_does_not_cascade_into_reference_errors() -> None:
    result = problems([step("x", "fake.unknown"), step("profile", source="x")])
    assert codes(result) == ["UNSUPPORTED_OPERATION"]


def test_input_kind_mismatch() -> None:
    result = problems([step("read", "fake.read")])
    assert codes(result) == ["INPUT_KIND_MISMATCH"] and result[0].resolve_in == "plan_input"
    assert problems([step("read", "fake.read")], facts(input_kind="source")) == []
    assert "INPUT_KIND_MISMATCH" in codes(problems([step("profile")], facts(input_kind="source")))


def test_invalid_parameters() -> None:
    wrong_value = problems([step("profile", parameters={"algorithm": "other"})])
    unknown_key = problems([step("profile", parameters={"extra": 1})])
    incomplete = problems(
        [step("trim", "fake.trim", parameters={})], facts(semantic_pinned=True), True
    )
    for result in (wrong_value, unknown_key, incomplete):
        assert codes(result) == ["INVALID_PARAMETERS"]
    assert incomplete[0].parameter == "columns"
    assert problems([step("profile", parameters={"algorithm": "column-profile-v1"})]) == []


def test_unknown_column() -> None:
    missing = uuid4()
    result = problems([trim(columns=[COLUMN, missing])], facts(semantic_pinned=True), True)
    assert codes(result) == ["UNKNOWN_COLUMN"]
    assert result[0].parameter == "columns" and str(missing) in result[0].message
    assert problems([trim(columns=[COLUMN, OTHER])], facts(semantic_pinned=True), True) == []


def test_semantic_revision_requirement_resolved_by_pinning_a_revision() -> None:
    missing = problems([trim()])
    assert codes(missing) == ["SEMANTIC_REQUIREMENT_MISSING"]
    assert missing[0].resolve_in == "understanding"
    assert problems([trim()], facts(semantic_pinned=True), pinned=True) == []


def test_confirmed_column_role_requirement() -> None:
    metric = step("metric", "fake.metric", parameters={"column": str(COLUMN)})
    assert codes(problems([metric])) == ["SEMANTIC_REQUIREMENT_MISSING"]
    unconfirmed = facts(semantic_pinned=True, confirmed_roles={COLUMN: "dimension"})
    assert codes(problems([metric], unconfirmed, True)) == ["SEMANTIC_REQUIREMENT_MISSING"]
    confirmed = facts(semantic_pinned=True, confirmed_roles={COLUMN: "measure"})
    assert problems([metric], confirmed, True) == []


def test_operations_without_requirements_do_not_need_semantics() -> None:
    assert "SEMANTIC_REQUIREMENT_MISSING" not in codes(problems([step("profile")]))


TYPED = {COLUMN: "string", OTHER: "integer"}


def upper(id: str = "upper", source: str | None = None, column: UUID = COLUMN) -> PlanStep:
    return step(id, "fake.upper", source, {"columns": [str(column)]})


def cast(
    id: str = "cast",
    source: str | None = None,
    type: str = "integer",
    confirm: bool = False,
    column: UUID = COLUMN,
) -> PlanStep:
    return step(id, "fake.cast", source, {"column": str(column), "type": type, "confirm": confirm})


def test_column_type_mismatch_against_the_pinned_table() -> None:
    assert problems([upper(column=COLUMN)], facts(column_types=TYPED)) == []
    result = problems([upper(column=OTHER)], facts(column_types=TYPED))
    assert codes(result) == ["COLUMN_TYPE_MISMATCH"]
    assert (result[0].resolve_in, result[0].step_id, result[0].parameter) == (
        "plan_steps",
        "upper",
        "columns",
    )
    assert "«integer»" in result[0].message


def test_schema_propagates_between_steps() -> None:
    # Texto antes de convertir: válido. Después la columna ya es un entero.
    assert problems([upper(), cast(source="upper")], facts(column_types=TYPED)) == []
    result = problems([cast(), upper(source="cast")], facts(column_types=TYPED))
    assert codes(result) == ["COLUMN_TYPE_MISMATCH"] and result[0].step_id == "upper"
    # Convertir dos veces: la segunda recibe un entero.
    twice = problems([cast(), cast("again", source="cast")], facts(column_types=TYPED))
    assert codes(twice) == ["COLUMN_TYPE_MISMATCH"] and twice[0].step_id == "again"
    # Los pasos que no consumen la salida convertida ven el esquema de la entrada.
    assert problems([cast(), upper("other")], facts(column_types=TYPED)) == []


def test_unknown_types_or_invalid_parameters_do_not_cascade() -> None:
    assert problems([upper(column=OTHER)], facts()) == []
    invalid = step("cast", "fake.cast", None, {"column": str(COLUMN), "type": "float"})
    result = problems([invalid, upper(source="cast")], facts(column_types=TYPED))
    assert codes(result) == ["INVALID_PARAMETERS"]


IDENTIFIER = {COLUMN: "identifier"}


@pytest.mark.parametrize(
    ("type", "confirm", "pinned", "roles", "expected"),
    [
        ("integer", False, True, IDENTIFIER, ["IDENTIFIER_CONVERSION_UNCONFIRMED"]),
        ("decimal", False, True, IDENTIFIER, ["IDENTIFIER_CONVERSION_UNCONFIRMED"]),
        ("integer", True, True, IDENTIFIER, []),  # confirmación explícita
        ("integer", False, False, IDENTIFIER, []),  # sin revisión fijada no hay salvaguarda
        ("date", False, True, IDENTIFIER, []),  # no numérico
        ("integer", False, True, {COLUMN: "measure"}, []),
        ("integer", False, True, {}, []),  # columna sin confirmar
    ],
)
def test_identifier_conversion_guard(
    type: str, confirm: bool, pinned: bool, roles: dict[UUID, str], expected: list[str]
) -> None:
    context = facts(column_types=TYPED, semantic_pinned=pinned, confirmed_roles=roles)
    result = problems([cast(type=type, confirm=confirm)], context, pinned=pinned)
    assert codes(result) == expected
    if expected:
        assert (result[0].resolve_in, result[0].parameter) == ("plan_steps", "confirm")


class MetricRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: UUID
    content_sha256: str


class QueryParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: list[MetricRef] = Field(min_length=1)
    time_grain: Literal["month"] | None = None


QUERY = OperationDescriptor(
    "fake.query",
    1,
    "Consulta",
    "table",
    "analysis_result",
    QueryParameters,
    metric_reference="metrics",
)
AMOUNT, DAY, OTHER_AMOUNT, CODE = uuid4(), uuid4(), uuid4(), uuid4()
TYPED_COLUMNS = {AMOUNT: "decimal", DAY: "date", OTHER_AMOUNT: "decimal", CODE: "string"}


def requirement(
    measure: UUID = AMOUNT,
    measured: bool = True,
    time: UUID | None = DAY,
    sha: str = "a" * 64,
) -> MetricRequirement:
    return MetricRequirement(
        sha, measure, NUMERIC if measured else frozenset(TYPED_COLUMNS.values()), measured, time, ()
    )


def query_problems(
    metrics: dict[UUID, MetricRequirement],
    refs: list[tuple[UUID, str]],
    time_grain: str | None = None,
    pinned: bool = True,
    roles: dict[UUID, str] | None = None,
    units: dict[UUID, str | None] | None = None,
    column_types: dict[UUID, str] | None = None,
) -> list[Problem]:
    parameters: dict[str, Any] = {
        "metrics": [{"revision_id": str(r), "content_sha256": s} for r, s in refs]
    }
    if time_grain:
        parameters["time_grain"] = time_grain
    draft = PlanDraft(
        semantic_ref=SEMANTIC_REF if pinned else None,
        steps=[step("query", "fake.query", None, parameters)],
    )
    facts = PlanningFacts(
        input_kind="table",
        column_ids=frozenset(TYPED_COLUMNS),
        semantic_pinned=pinned,
        confirmed_roles=roles
        if roles is not None
        else {AMOUNT: "measure", DAY: "business_date", OTHER_AMOUNT: "measure"},  # type: ignore[arg-type]
        column_types=column_types or TYPED_COLUMNS,  # type: ignore[arg-type]
        metrics=metrics,
        column_units=units
        if units is not None
        else {AMOUNT: "currency:EUR", OTHER_AMOUNT: "currency:EUR"},
    )

    class Catalog(FakeCatalog):
        def descriptor(self, name: str, version: int) -> OperationDescriptor | None:
            return QUERY if name == "fake.query" else super().descriptor(name, version)

    return validate_plan(draft, Catalog(), facts)


def test_metric_query_valid_with_confirmed_semantics() -> None:
    m1, m2 = uuid4(), uuid4()
    metrics = {m1: requirement(), m2: requirement(OTHER_AMOUNT)}
    assert query_problems(metrics, [(m1, "a" * 64), (m2, "a" * 64)], time_grain="month") == []


def test_semantic_requirement_missing_until_measure_is_confirmed() -> None:
    m = uuid4()
    result = query_problems({m: requirement()}, [(m, "a" * 64)], roles={})
    assert [(p.code, p.resolve_in) for p in result] == [
        ("SEMANTIC_REQUIREMENT_MISSING", "understanding")
    ]
    unpinned = query_problems({m: requirement()}, [(m, "a" * 64)], pinned=False, time_grain="month")
    assert [p.code for p in unpinned] == ["SEMANTIC_REQUIREMENT_MISSING"] * 2  # medida y fecha
    # Un conteo no exige rol de medida ni unidad.
    count = uuid4()
    assert (
        query_problems(
            {count: requirement(CODE, measured=False, time=None)}, [(count, "a" * 64)], roles={}
        )
        == []
    )


def test_metric_reference_type_and_unit_problems() -> None:
    m1, m2 = uuid4(), uuid4()
    forged = query_problems({m1: requirement()}, [(m1, "0" * 64)])
    assert [p.code for p in forged] == ["METRIC_REFERENCE_MISMATCH"]
    assert [p.code for p in query_problems({}, [(uuid4(), "a" * 64)])] == [
        "METRIC_REFERENCE_MISMATCH"
    ]
    missing_column = query_problems({m1: requirement(uuid4())}, [(m1, "a" * 64)])
    assert [p.code for p in missing_column] == ["METRIC_REFERENCE_MISMATCH"]
    text = query_problems(
        {m1: requirement()}, [(m1, "a" * 64)], column_types={**TYPED_COLUMNS, AMOUNT: "string"}
    )
    assert [p.code for p in text] == ["COLUMN_TYPE_MISMATCH"]
    currencies = query_problems(
        {m1: requirement(), m2: requirement(OTHER_AMOUNT)},
        [(m1, "a" * 64), (m2, "a" * 64)],
        units={AMOUNT: "currency:EUR", OTHER_AMOUNT: "currency:USD"},
    )
    assert [p.code for p in currencies] == ["UNIT_MISMATCH"]
    assert "currency:EUR, currency:USD" in currencies[0].message
    no_time = query_problems(
        {m1: requirement(), m2: requirement(OTHER_AMOUNT, time=None)},
        [(m1, "a" * 64), (m2, "a" * 64)],
        time_grain="month",
    )
    assert [p.code for p in no_time] == ["TIME_COLUMN_MISMATCH"]


class ShareParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: list[MetricRef] = Field(min_length=1)
    share_of_total: list[UUID] = Field(default_factory=list)


SHARE_QUERY = OperationDescriptor(
    "fake.share",
    1,
    "Participación",
    "table",
    "analysis_result",
    ShareParameters,
    metric_reference="metrics",
    additive_metrics="share_of_total",
)


def test_share_of_total_requires_additive_metrics() -> None:
    """La participación sólo se calcula sobre métricas que se pueden sumar entre grupos; planning
    lo sabe por el requisito de la métrica, sin importar analytics."""
    additive, average = uuid4(), uuid4()
    metrics = {
        additive: MetricRequirement("a" * 64, AMOUNT, NUMERIC, True, None, (), additive=True),
        average: MetricRequirement("a" * 64, AMOUNT, NUMERIC, True, None, ()),
    }

    def problems(shared: list[UUID]) -> list[Problem]:
        draft = PlanDraft(
            semantic_ref=SEMANTIC_REF,
            steps=[
                step(
                    "share",
                    "fake.share",
                    None,
                    {
                        "metrics": [
                            {"revision_id": str(m), "content_sha256": "a" * 64}
                            for m in (additive, average)
                        ],
                        "share_of_total": [str(m) for m in shared],
                    },
                )
            ],
        )
        facts = PlanningFacts(
            input_kind="table",
            column_ids=frozenset(TYPED_COLUMNS),
            semantic_pinned=True,
            confirmed_roles={AMOUNT: "measure"},
            column_types=TYPED_COLUMNS,  # type: ignore[arg-type]
            metrics=metrics,
            column_units={AMOUNT: "currency:EUR"},
        )

        class Catalog(FakeCatalog):
            def descriptor(self, name: str, version: int) -> OperationDescriptor | None:
                return SHARE_QUERY if name == "fake.share" else super().descriptor(name, version)

        return validate_plan(draft, Catalog(), facts)

    assert problems([additive]) == []
    found = problems([additive, average])
    assert [(p.code, p.parameter, p.resolve_in) for p in found] == [
        ("SHARE_NOT_ADDITIVE", "share_of_total", "plan_steps")
    ]
    assert str(average) in found[0].message
