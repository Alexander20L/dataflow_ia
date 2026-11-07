"""Validación pura de planes: devuelve problemas, nunca excepciones por contenido incompleto."""

from uuid import UUID

from pydantic import BaseModel, ValidationError

from dataflow.modules.planning.contracts import (
    COLUMN_REF,
    MAX_STEPS,
    ConfirmedColumnRole,
    InputKind,
    InputRef,
    MetricRequirement,
    OperationCatalog,
    OperationDescriptor,
    OutputKind,
    PlanDraft,
    PlanningFacts,
    PlanStatus,
    PlanStep,
    Problem,
    ProblemCode,
    ResolveIn,
    Schema,
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
    # Esquema tipado de cada salida tabular; None si no se conoce (no se comprueban tipos).
    schemas: dict[str, Schema | None] = {}
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
            schema: Schema | None = (
                facts.column_types or None
                if isinstance(step.input, InputRef)
                else schemas.get(step.input.step_id)
                if source_kind == "table"
                else None
            )
            step_problems, parameters = step_parameter_problems(step, descriptor, facts, schema)
            problems.extend(step_problems)
            if step.id not in schemas:
                schemas[step.id] = output_schema(descriptor, parameters, schema)
        outputs.setdefault(step.id, descriptor.output_kind if descriptor else None)
    return problems


def output_schema(
    descriptor: OperationDescriptor, parameters: BaseModel | None, schema: Schema | None
) -> Schema | None:
    if descriptor.output_kind != "table" or schema is None:
        return None
    if descriptor.output_schema is None:
        return schema
    # Parámetros inválidos: el esquema de salida es desconocido y no se encadenan errores.
    return descriptor.output_schema(parameters, schema) if parameters is not None else None


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
    step: PlanStep,
    descriptor: OperationDescriptor,
    facts: PlanningFacts,
    schema: Schema | None = None,
) -> tuple[list[Problem], BaseModel | None]:
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
    if parameters is not None:
        problems.extend(type_problems(step, descriptor, parameters, facts, schema))
        problems.extend(ruleset_problems(step, descriptor, parameters, facts, schema))
        problems.extend(metric_problems(step, descriptor, parameters, facts, schema))
    return problems, parameters


def metric_problems(
    step: PlanStep,
    descriptor: OperationDescriptor,
    parameters: BaseModel,
    facts: PlanningFacts,
    schema: Schema | None,
) -> list[Problem]:
    """Métricas referenciadas: revisión exacta, columnas existentes y tipos; requisito
    semántico positivo (medida confirmada como «measure»; columna temporal como
    «business_date»); unidad o moneda compartida y una única columna temporal."""
    if descriptor.metric_reference is None:
        return []
    name = descriptor.metric_reference
    problems: list[Problem] = []

    def problem(code: ProblemCode, message: str, resolve: ResolveIn = "plan_steps") -> None:
        problems.append(
            Problem(code=code, message=message, resolve_in=resolve, step_id=step.id, parameter=name)
        )

    uses_time = (
        getattr(parameters, "time_grain", None) is not None
        or getattr(parameters, "time_range", None) is not None
    )
    resolved: list[MetricRequirement] = []
    for reference in getattr(parameters, name):
        requirement = facts.metrics.get(reference.revision_id)
        if requirement is None or requirement.content_sha256 != reference.content_sha256:
            problem(
                "METRIC_REFERENCE_MISMATCH",
                f"La métrica {reference.revision_id} no existe, no es accesible o su hash no "
                "coincide.",
            )
            continue
        if descriptor.version < requirement.min_query_version:
            problem(
                "METRIC_UNSUPPORTED",
                f"La métrica {reference.revision_id} usa sum_product o el último corte: "
                f"necesita {descriptor.name}@{requirement.min_query_version}.",
            )
            continue
        second = requirement.second_measure_column_id
        measures = [requirement.measure_column_id, *([second] if second else [])]
        columns = [
            *measures,
            *requirement.filter_column_ids,
            *([requirement.time_column_id] if requirement.time_column_id else []),
        ]
        missing = [column for column in columns if column not in facts.column_ids]
        if missing:
            problem(
                "METRIC_REFERENCE_MISMATCH",
                f"La métrica usa la columna {missing[0]}, que no existe en la tabla fijada.",
            )
            continue
        resolved.append(requirement)
        for measure in measures:
            actual = schema.get(measure) if schema is not None else None
            if actual is not None and actual not in requirement.measure_types:
                problem(
                    "COLUMN_TYPE_MISMATCH",
                    "La métrica necesita una columna "
                    f"{', '.join(sorted(requirement.measure_types))}; {measure} es «{actual}». "
                    "Conviértela en Limpieza.",
                )
            if requirement.requires_measure_role and (
                not facts.semantic_pinned or facts.confirmed_roles.get(measure) != "measure"
            ):
                problem(
                    "SEMANTIC_REQUIREMENT_MISSING",
                    f"La columna {measure} debe estar confirmada como medida («measure») en la "
                    "revisión semántica fijada.",
                    "understanding",
                )
        if (uses_time or requirement.requires_time_role) and requirement.time_column_id is not None:
            time_type = schema.get(requirement.time_column_id) if schema is not None else None
            if time_type is not None and time_type != "date":
                problem(
                    "COLUMN_TYPE_MISMATCH",
                    f"La columna temporal {requirement.time_column_id} debe ser una fecha.",
                )
            if (
                not facts.semantic_pinned
                or facts.confirmed_roles.get(requirement.time_column_id) != "business_date"
            ):
                problem(
                    "SEMANTIC_REQUIREMENT_MISSING",
                    f"La columna {requirement.time_column_id} debe estar confirmada como fecha "
                    "de negocio («business_date») en la revisión semántica fijada.",
                    "understanding",
                )
    if uses_time and resolved:
        times = {r.time_column_id for r in resolved}
        if None in times or len(times) > 1:
            problem(
                "TIME_COLUMN_MISMATCH",
                "Para agrupar por tiempo o filtrar un periodo, todas las métricas deben declarar "
                "la misma columna temporal.",
            )
    if descriptor.additive_metrics is not None:
        for revision in getattr(parameters, descriptor.additive_metrics) or []:
            requirement = facts.metrics.get(revision)
            if requirement is not None and not requirement.additive:
                problems.append(
                    Problem(
                        code="SHARE_NOT_ADDITIVE",
                        message=f"La participación sobre el total sólo se calcula para sumas y "
                        f"conteos; la métrica {revision} no se puede sumar entre grupos.",
                        resolve_in="plan_steps",
                        step_id=step.id,
                        parameter=descriptor.additive_metrics,
                    )
                )
    if facts.semantic_pinned:
        units: set[str | None] = set()
        for r in resolved:
            if not r.requires_measure_role:
                continue
            unit = facts.column_units.get(r.measure_column_id)
            if r.second_measure_column_id is not None:
                valid, unit = product_unit(unit, facts.column_units.get(r.second_measure_column_id))
                if not valid:
                    problem(
                        "UNIT_MISMATCH",
                        "sum_product no multiplica dos monedas: una de las medidas debe ser una "
                        "cantidad.",
                    )
                    continue
            units.add(unit)
        if len(units) > 1:
            shown = ", ".join(sorted(unit or "sin unidad" for unit in units))
            problem(
                "UNIT_MISMATCH",
                f"Las métricas combinadas deben compartir unidad o moneda; hay: {shown}.",
            )
    return problems


def product_unit(first: str | None, second: str | None) -> tuple[bool, str | None]:
    """Unidad de Σ(medida × segunda medida), con las claves de `column_units`: una cantidad por
    un costo unitario da la moneda («currency:COP»); dos unidades, su producto («unit:kg×m»);
    dos monedas no se multiplican (no válido). Misma regla que
    `analytics.contracts.product_unit`."""
    currencies = [u for u in (first, second) if u is not None and u.startswith("currency:")]
    if len(currencies) == 2:
        return False, None
    if currencies:
        return True, currencies[0]
    units = [u.removeprefix("unit:") for u in (first, second) if u is not None]
    return True, f"unit:{'×'.join(units)}" if units else None


def ruleset_problems(
    step: PlanStep,
    descriptor: OperationDescriptor,
    parameters: BaseModel,
    facts: PlanningFacts,
    schema: Schema | None,
) -> list[Problem]:
    """La revisión exacta de reglas debe existir, coincidir con su hash y ser aplicable a la
    tabla que llega al paso (columnas existentes y tipos admitidos)."""
    if descriptor.ruleset_reference is None:
        return []
    id_parameter, sha_parameter = descriptor.ruleset_reference
    revision = getattr(parameters, id_parameter)
    requirement = facts.quality_rulesets.get(revision)

    def problem(code: ProblemCode, message: str) -> Problem:
        return Problem(
            code=code,
            message=message,
            resolve_in="plan_steps",
            step_id=step.id,
            parameter=id_parameter,
        )

    if requirement is None or requirement.content_sha256 != getattr(parameters, sha_parameter):
        return [
            problem(
                "QUALITY_RULESET_MISMATCH",
                f"La revisión de reglas {revision} no existe, no es accesible o su hash no "
                "coincide.",
            )
        ]
    known = schema if schema is not None else None
    problems: list[Problem] = []
    for column, allowed in requirement.column_types.items():
        if column not in facts.column_ids:
            problems.append(
                problem(
                    "QUALITY_RULESET_MISMATCH",
                    f"Una regla usa la columna {column}, que no existe en la tabla fijada.",
                )
            )
        elif known is not None and (actual := known.get(column)) and actual not in allowed:
            problems.append(
                problem(
                    "COLUMN_TYPE_MISMATCH",
                    f"Las reglas no admiten la columna {column} de tipo «{actual}»; admiten: "
                    f"{', '.join(sorted(allowed))}.",
                )
            )
    return problems


def type_problems(
    step: PlanStep,
    descriptor: OperationDescriptor,
    parameters: BaseModel,
    facts: PlanningFacts,
    schema: Schema | None,
) -> list[Problem]:
    """Tipos de columna admitidos (según el esquema que llega al paso) y salvaguarda de
    identificadores. Una columna desconocida ya se informa como UNKNOWN_COLUMN."""
    problems: list[Problem] = []
    if descriptor.column_types is not None and schema is not None:
        for name, allowed in descriptor.column_types(parameters).items():
            for column in referenced_columns(parameters, name):
                if column not in facts.column_ids and name not in column_parameters(
                    descriptor.parameters
                ):
                    problems.append(
                        Problem(
                            code="UNKNOWN_COLUMN",
                            message=f"La columna {column} no existe en la tabla fijada.",
                            resolve_in="plan_steps",
                            step_id=step.id,
                            parameter=name,
                        )
                    )
                    continue
                actual = schema.get(column)
                if actual is not None and actual not in allowed:
                    problems.append(
                        Problem(
                            code="COLUMN_TYPE_MISMATCH",
                            message=f"{descriptor.key} no admite la columna {column} de tipo "
                            f"«{actual}» en este paso; admite: {', '.join(sorted(allowed))}.",
                            resolve_in="plan_steps",
                            step_id=step.id,
                            parameter=name,
                        )
                    )
    guard = descriptor.identifier_guard
    if (
        guard is not None
        and facts.semantic_pinned
        and getattr(parameters, guard.type_parameter) in guard.numeric_types
        and not getattr(parameters, guard.confirmation_parameter)
    ):
        for column in referenced_columns(parameters, guard.column_parameter):
            if facts.confirmed_roles.get(column) == "identifier":
                problems.append(
                    Problem(
                        code="IDENTIFIER_CONVERSION_UNCONFIRMED",
                        message=f"La columna {column} está confirmada como identificador en la "
                        "revisión semántica fijada. Convertirla a número exige confirmarlo "
                        f"explícitamente ({guard.confirmation_parameter}).",
                        resolve_in="plan_steps",
                        step_id=step.id,
                        parameter=guard.confirmation_parameter,
                    )
                )
    return problems
