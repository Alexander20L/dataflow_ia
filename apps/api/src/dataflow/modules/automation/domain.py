"""Evaluación pura de una política sobre un plan validado y el efecto de su vista previa
(Fase 11B). Sin SQL ni Polars: lee hechos ya calculados. Compara porcentajes con aritmética
exacta (`medido × 100 > límite × total`), nunca con flotantes.
"""

from decimal import Decimal

from dataflow.modules.automation.contracts import (
    ALL_COLUMNS,
    EffectFacts,
    Evaluation,
    PlannedStep,
    PolicyContent,
    PreviewFacts,
    Reason,
)

MESSAGES = {
    "POLICY_MISSING": "El proyecto no tiene una política de automatización.",
    "POLICY_DISABLED": "La política de automatización está desactivada.",
    "PLAN_INVALID": "El plan de limpieza no es válido.",
    "EFFECT_NOT_READY": "La vista previa no terminó correctamente.",
    "EFFECT_BREAKDOWN_MISSING": "La vista previa no tiene el desglose por columna; "
    "genera una vista previa nueva.",
    "OPERATION_NOT_AUTHORIZED": "La política no autoriza esta operación.",
    "COLUMN_NOT_AUTHORIZED": "La política no autoriza esta operación en esta columna.",
    "TOKENS_NOT_AUTHORIZED": "Los marcadores de nulo no son los autorizados para la columna.",
    "IDENTIFIER_CONVERSION": "Convertir un identificador a número exige una persona.",
    "EXCLUDED_ROWS_ABOVE_LIMIT": "La limpieza excluiría más filas de las permitidas.",
    "NULLS_CREATED_ABOVE_LIMIT": "La limpieza crearía más nulos de los permitidos.",
    "ROUNDED_CELLS_ABOVE_LIMIT": "La conversión redondearía más celdas de las permitidas.",
    "OUTPUT_ROWS_BELOW_MINIMUM": "La versión derivada tendría menos filas de las exigidas.",
}


def reason(code: str, **detail: str | None) -> Reason:
    return Reason.model_validate({"code": code, "message": MESSAGES[code], **detail})


def step_columns(step: PlannedStep) -> list[str]:
    parameters = step.parameters
    if "column_ids" in parameters:
        return [str(value) for value in parameters["column_ids"]]
    if "column_id" in parameters:
        return [str(parameters["column_id"])]
    return []


def above(measured: int, limit_pct: Decimal, total: int) -> bool:
    """`measured / total > limit_pct %`, exacto. Sin total no hay nada que superar."""
    return total > 0 and Decimal(measured) * 100 > limit_pct * total


def pct(measured: int, total: int) -> str:
    if total <= 0:
        return "0"
    return format((Decimal(measured) * 100 / total).quantize(Decimal("0.01")), "f")


def authorization(policy: PolicyContent, facts: PreviewFacts) -> list[Reason]:
    reasons: list[Reason] = []
    scopes: dict[str, set[str]] = {
        str(scope.operation): set(scope.columns) for scope in policy.column_scopes
    }
    tokens = {item.column: set(item.tokens) for item in policy.null_tokens_by_column}
    for step in facts.steps:
        if step.operation not in policy.allowed_operations:
            reasons.append(reason("OPERATION_NOT_AUTHORIZED", step_id=step.id))
            continue
        # Sin alcance declarado no hay columnas autorizadas: la operación sola no basta.
        allowed = scopes.get(step.operation, set())
        for column_id in step_columns(step):
            name = facts.column_names.get(column_id, column_id)
            if ALL_COLUMNS not in allowed and name not in allowed:
                reasons.append(reason("COLUMN_NOT_AUTHORIZED", step_id=step.id, column=name))
        if step.operation == "cleaning.normalize_null_tokens":
            requested = {str(token) for token in step.parameters.get("tokens", [])}
            for column_id in step_columns(step):
                name = facts.column_names.get(column_id, column_id)
                if not requested <= tokens.get(name, set()):
                    reasons.append(reason("TOKENS_NOT_AUTHORIZED", step_id=step.id, column=name))
        if step.operation == "cleaning.cast" and step.parameters.get(
            "confirm_identifier_conversion"
        ):
            name = facts.column_names.get(step_columns(step)[0], step_columns(step)[0])
            reasons.append(reason("IDENTIFIER_CONVERSION", step_id=step.id, column=name))
    return reasons


def barriers(policy: PolicyContent, effect: EffectFacts, names: dict[str, str]) -> list[Reason]:
    reasons: list[Reason] = []
    if above(effect.excluded_rows, policy.max_excluded_rows_pct, effect.input_rows):
        share = pct(effect.excluded_rows, effect.input_rows)
        reasons.append(
            reason(
                "EXCLUDED_ROWS_ABOVE_LIMIT",
                measured=f"{effect.excluded_rows} filas ({share} %)",
                limit=f"{policy.max_excluded_rows_pct} %",
            )
        )
    cells = effect.input_rows * len(names)
    if above(effect.created_nulls, policy.max_nulls_created_pct, cells):
        reasons.append(
            reason(
                "NULLS_CREATED_ABOVE_LIMIT",
                measured=f"{effect.created_nulls} celdas ({pct(effect.created_nulls, cells)} %)",
                limit=f"{policy.max_nulls_created_pct} %",
            )
        )
    # Por columna: una columna muy afectada no se diluye en el total de la tabla.
    for column in effect.columns or []:
        if above(column.created_nulls, policy.max_nulls_created_pct, effect.input_rows):
            reasons.append(
                reason(
                    "NULLS_CREATED_ABOVE_LIMIT",
                    column=names.get(column.column_id, column.column_id),
                    measured=f"{column.created_nulls} celdas "
                    f"({pct(column.created_nulls, effect.input_rows)} %)",
                    limit=f"{policy.max_nulls_created_pct} %",
                )
            )
    if effect.rounded_cells > policy.max_rounded_cells:
        reasons.append(
            reason(
                "ROUNDED_CELLS_ABOVE_LIMIT",
                measured=str(effect.rounded_cells),
                limit=str(policy.max_rounded_cells),
            )
        )
    if effect.output_rows < policy.min_output_rows:
        reasons.append(
            reason(
                "OUTPUT_ROWS_BELOW_MINIMUM",
                measured=str(effect.output_rows),
                limit=str(policy.min_output_rows),
            )
        )
    return reasons


def evaluate(policy: PolicyContent | None, facts: PreviewFacts) -> Evaluation:
    """Aprueba sólo si la política está activa, el plan es válido, cada paso y columna está
    autorizado, no hay conversión de identificadores y el efecto cumple todas las barreras."""
    if policy is None:
        return Evaluation(decision="blocked", reasons=[reason("POLICY_MISSING")])
    if not policy.enabled:
        return Evaluation(decision="blocked", reasons=[reason("POLICY_DISABLED")])
    reasons: list[Reason] = []
    if facts.state != "succeeded" or facts.effect is None or facts.effect_sha256 is None:
        reasons.append(reason("EFFECT_NOT_READY"))
    if not facts.plan_valid:
        reasons.append(reason("PLAN_INVALID"))
    reasons.extend(authorization(policy, facts))
    if facts.effect is not None:
        if facts.effect.columns is None:
            reasons.append(reason("EFFECT_BREAKDOWN_MISSING"))
        reasons.extend(barriers(policy, facts.effect, facts.column_names))
    return Evaluation(decision="blocked" if reasons else "approved", reasons=reasons)
