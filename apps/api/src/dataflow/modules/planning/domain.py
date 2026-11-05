"""Validación pura de planes: devuelve problemas, nunca excepciones por contenido incompleto."""

from uuid import UUID

from pydantic import BaseModel, ValidationError

from dataflow.modules.planning.contracts import (
    COLUMN_REF,
    MAX_STEPS,
    ConfirmedColumnRole,
    InputKind,
    InputRef,
    OperationCatalog,
    OperationDescriptor,
    OutputKind,
    PlanDraft,
    PlanningFacts,
    PlanStatus,
    PlanStep,
    Problem,
    SemanticRevisionRequirement,
)


def plan_status(problems: list[Problem]) -> PlanStatus:
    return "incomplete" if problems else "valid"


def column_parameters(model: type[BaseModel]) -> list[str]:
    return [
        name
        for name, info in model.model_fields.items()
        if isinstance(info.json_schema_extra, dict) and info.json_schema_extra.get(COLUMN_REF)
    ]


def referenced_columns(parameters: BaseModel, name: str) -> list[UUID]:
    value = getattr(parameters, name)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else [value]


def validate_plan(
    draft: PlanDraft, catalog: OperationCatalog, facts: PlanningFacts
) -> list[Problem]:
    problems: list[Problem] = []
    if not draft.steps:
        problems.append(
            Problem(
                code="EMPTY_PLAN",
                message="Añade al menos una operación del catálogo.",
                resolve_in="plan_steps",
            )
        )
    if len(draft.steps) > MAX_STEPS:
        problems.append(
            Problem(
                code="TOO_MANY_STEPS",
                message=f"Un plan admite como máximo {MAX_STEPS} pasos.",
                resolve_in="plan_steps",
            )
        )
    all_ids = {step.id for step in draft.steps}
    # None: salida de una operación desconocida; no se encadenan errores sobre ella.
    outputs: dict[str, OutputKind | None] = {}
    for step in draft.steps:
        if step.id in outputs:
            problems.append(
                Problem(
                    code="DUPLICATE_STEP_ID",
                    message=f"El identificador de paso «{step.id}» está repetido.",
                    resolve_in="plan_steps",
                    step_id=step.id,
                )
            )
        descriptor = catalog.descriptor(step.operation, step.version)
        if descriptor is None:
            problems.append(
                Problem(
                    code="UNSUPPORTED_OPERATION",
                    message=f"{step.operation}@{step.version} no está en el catálogo "
                    f"{catalog.catalog_version}.",
                    resolve_in="plan_steps",
                    step_id=step.id,
                )
            )
        source_kind = step_input_kind(step, facts.input_kind, outputs, all_ids, problems)
        if descriptor is not None:
            if source_kind is not None and source_kind != descriptor.input_kind:
                problems.append(
                    Problem(
                        code="INPUT_KIND_MISMATCH",
                        message=f"{descriptor.key} requiere una entrada «{descriptor.input_kind}» "
                        f"y recibe «{source_kind}».",
                        resolve_in="plan_input"
                        if isinstance(step.input, InputRef)
                        else "plan_steps",
                        step_id=step.id,
                    )
                )
            problems.extend(step_parameter_problems(step, descriptor, facts))
        outputs.setdefault(step.id, descriptor.output_kind if descriptor else None)
    return problems


def step_input_kind(
    step: PlanStep,
    plan_input: InputKind,
    outputs: dict[str, OutputKind | None],
    all_ids: set[str],
    problems: list[Problem],
) -> InputKind | None:
    if isinstance(step.input, InputRef):
        return plan_input
    target = step.input.step_id
    if target == step.id:
        reason = "no puede consumir su propia salida (ciclo)"
    elif target not in outputs:
        reason = (
            "referencia un paso posterior"
            if target in all_ids
            else "referencia un paso inexistente"
        )
    elif outputs[target] is None:
        return None
    elif outputs[target] != "table":
        reason = f"consume una salida «{outputs[target]}», que no es una tabla"
    else:
        return "table"
    problems.append(
        Problem(
            code="INVALID_STEP_REFERENCE",
            message=f"El paso «{step.id}» {reason}: «{target}».",
            resolve_in="plan_steps",
            step_id=step.id,
        )
    )
    return None


def step_parameter_problems(
    step: PlanStep, descriptor: OperationDescriptor, facts: PlanningFacts
) -> list[Problem]:
    problems: list[Problem] = []
    try:
        parameters = descriptor.parameters.model_validate(step.parameters)
    except ValidationError as exc:
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or None
            problems.append(
                Problem(
                    code="INVALID_PARAMETERS",
                    message=f"Parámetro {location or ''} no válido: {error['msg']}".replace(
                        "  ", " "
                    ),
                    resolve_in="plan_steps",
                    step_id=step.id,
                    parameter=location,
                )
            )
        parameters = None
    if parameters is not None:
        for name in column_parameters(descriptor.parameters):
            for column in referenced_columns(parameters, name):
                if column not in facts.column_ids:
                    problems.append(
                        Problem(
                            code="UNKNOWN_COLUMN",
                            message=f"La columna {column} no existe en la tabla fijada.",
                            resolve_in="plan_steps",
                            step_id=step.id,
                            parameter=name,
                        )
                    )
    for requirement in descriptor.requirements:
        if isinstance(requirement, SemanticRevisionRequirement):
            if not facts.semantic_pinned:
                problems.append(
                    Problem(
                        code="SEMANTIC_REQUIREMENT_MISSING",
                        message=f"{descriptor.key} requiere fijar una revisión semántica.",
                        resolve_in="understanding",
                        step_id=step.id,
                    )
                )
        elif isinstance(requirement, ConfirmedColumnRole) and parameters is not None:
            for column in referenced_columns(parameters, requirement.parameter):
                if (
                    not facts.semantic_pinned
                    or facts.confirmed_roles.get(column) != requirement.role
                ):
                    problems.append(
                        Problem(
                            code="SEMANTIC_REQUIREMENT_MISSING",
                            message=f"{descriptor.key} requiere que la columna {column} esté "
                            f"confirmada como «{requirement.role}» en la revisión fijada.",
                            resolve_in="understanding",
                            step_id=step.id,
                            parameter=requirement.parameter,
                        )
                    )
    return problems
