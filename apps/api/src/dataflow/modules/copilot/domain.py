"""Reglas puras del copiloto: contexto autorizado, verificación de cifras y resolución de
propuestas a pasos del catálogo. Sin frameworks, sin proveedor y sin base de datos."""

import json
import re
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import Any
from uuid import UUID

from dataflow.modules.copilot.contracts import (
    AuditAlert,
    AuditContent,
    AuditoriaTextual,
    ClarificationTopic,
    CleaningStepProposal,
    ColumnFact,
    DashboardCardFact,
    DashboardFacts,
    MetricFact,
    MetricProposal,
    NamedRef,
    ProposalProblem,
    ProposedFilter,
    QueryProposal,
    ResultCell,
    ResultFacts,
    Segment,
    TableContext,
)

UNTRUSTED = "dato_no_confiable"
UNVERIFIED = "[cifra no verificada]"
NUMERIC_TYPES = {"integer", "decimal"}
MAX_HISTORY = 10
MAX_RESULT_CELLS = 200

# --- Contexto autorizado ----------------------------------------------------------------------


def untrusted(value: Any) -> dict[str, Any] | None:
    """Envuelve texto que viene de los datos o de un usuario: el prompt indica que nunca es
    una instrucción. None se conserva como null."""
    return None if value is None else {UNTRUSTED: value}


def column_context(column: ColumnFact) -> dict[str, Any]:
    return {
        "id": str(column.id),
        "nombre": untrusted(column.name),
        "tipo": column.technical_type,
        "nulos": column.null_count,
        "distintos": column.distinct_count,
        "rol": column.role,
        "rol_confirmado": column.confirmed,
        "moneda": column.currency,
        "unidad": untrusted(column.unit),
        "descripcion": untrusted(column.description),
    }


def metric_context(metric: MetricFact) -> dict[str, Any]:
    return {
        "id": str(metric.revision_id),
        "etiqueta": untrusted(metric.label),
        "agregacion": metric.aggregation,
        "columna_medida": str(metric.measure_column_id),
        "columna_fecha": str(metric.time_column_id) if metric.time_column_id else None,
        "filtros": [
            {
                "columna": str(f["column_id"]),
                "operador": f["operator"],
                "valores": untrusted(list(f.get("values", []))),
            }
            for f in metric.filters
        ],
        "aplicable": metric.applicable,
    }


def authorized_context(table: TableContext, metrics: list[MetricFact]) -> dict[str, Any]:
    """Contexto mínimo aprobado (ADR-022 §Privacidad): esquema, semántica, métricas y conteos
    agregados. Nunca filas, valores de ejemplo ni resumen numérico del perfil."""
    return {
        "tabla": {
            "filas": table.row_count,
            "columnas": [column_context(c) for c in table.columns],
        },
        "semantica": {
            "revision": table.semantic_revision,
            "descripcion_dataset": untrusted(table.dataset_description),
            "grano_fila": untrusted(table.row_grain),
        }
        if table.semantic_revision is not None
        else None,
        "metricas": [metric_context(m) for m in metrics],
    }


def result_context(result: ResultFacts) -> dict[str, Any]:
    """Explicar un resultado: definiciones, conteos y cada cifra con su evidence_id. Las
    etiquetas de grupo son datos del dataset (no confiables)."""
    return {
        "ejecucion": str(result.execution_id),
        "operacion": result.operation,
        "filas_resultado": result.rows,
        "metricas": [{**m, "etiqueta": untrusted(m.get("etiqueta"))} for m in result.metrics],
        "cifras": [
            {
                "evidencia": c.evidence_id,
                "celda": c.cell,
                "metrica": c.metric_key,
                "comparacion": c.comparison,
                "grupo": untrusted(c.group) if c.group else None,
                "periodo": c.period,
                "valor": c.value,
            }
            for c in result.cells
        ],
        "cifras_omitidas": max(0, result.total_cells - len(result.cells)),
    }


# --- Auditoría textual de un dashboard (11F) --------------------------------------------------

MAX_AUDIT_CELLS_PER_CARD = 40  # cifras por tarjeta que se envían al proveedor


def audit_context(
    dashboard: DashboardFacts, audited: list[tuple[DashboardCardFact, ResultFacts]], skipped: int
) -> dict[str, Any]:
    """Contexto de la auditoría: sólo resultados publicados (agregados con su evidencia) y
    etiquetas autorizadas; nunca filas de detalle. Títulos y etiquetas son textos de personas o
    del dataset (no confiables)."""
    return {
        "dashboard": {
            "titulo": untrusted(dashboard.title),
            "descripcion": untrusted(dashboard.description),
        },
        "tarjetas": [
            {
                "titulo": untrusted(card.title),
                "metrica_dibujada": card.metric,
                "resultado": result_context(result),
            }
            for card, result in audited
        ],
        "tarjetas_sin_resultado": skipped,
    }


def audited_result(
    dashboard: DashboardFacts, audited: list[tuple[DashboardCardFact, ResultFacts]]
) -> dict[str, Any]:
    """Lo auditado, para su hash: cifras y evidencias de cada tarjeta y los textos que las
    acompañan. Una cifra distinta (otra ejecución, otro valor) es otro resultado."""
    return {
        "title": dashboard.title,
        "description": dashboard.description,
        "cards": [
            {
                "card_id": str(card.id),
                "title": card.title,
                "metric": card.metric,
                "execution_id": str(result.execution_id),
                "operation": result.operation,
                "cells": [[c.evidence_id, c.cell, c.value] for c in result.cells],
                "total_cells": result.total_cells,
            }
            for card, result in audited
        ],
    }


def verify_audit(
    output: AuditoriaTextual, cells: dict[str, ResultCell], executions: dict[str, UUID]
) -> tuple[AuditContent | None, list[str]]:
    """Aplica la regla única de cifras a cada texto de la auditoría: {{evidence:id}} se sustituye
    por el valor exacto (con la ejecución de su tarjeta), un número libre se retira y se cuenta, y
    una referencia inexistente o ajena anula TODA la auditoría (devuelve None y las referencias)."""
    invalid: list[str] = []
    removed = 0

    def verified(text: str) -> list[Segment]:
        nonlocal removed
        segments, numbers, wrong = verify_explanation(text, cells, UUID(int=0))
        invalid.extend(wrong)
        removed += numbers
        return [
            segment.model_copy(update={"execution_id": executions[segment.evidence_id]})
            if segment.kind == "evidence" and segment.evidence_id
            else segment
            for segment in segments
        ]

    content = AuditContent(
        resumen_ejecutivo=verified(output.resumen_ejecutivo),
        alertas_criticas=[
            AuditAlert(
                titulo=verified(alert.titulo),
                detalle=verified(alert.detalle),
                severidad=alert.severidad,
            )
            for alert in output.alertas_criticas
        ],
        recomendaciones=[verified(text) for text in output.recomendaciones],
        unverified_numbers=0,
    )
    if invalid:
        return None, invalid
    return content.model_copy(update={"unverified_numbers": removed}), []


def serialize(context: dict[str, Any]) -> str:
    """JSON estable; `<`, `>` y `&` se escapan para que un dato no pueda cerrar el bloque."""
    text = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# --- Cifras -----------------------------------------------------------------------------------

REFERENCE = re.compile(r"\{\{\s*(evidence|label)\s*:\s*([^}\s]*)\s*\}\}")
ANY_BRACES = re.compile(r"\{\{.*?\}\}", re.S)
# Cualquier número escrito: 1.234,56 · 1,234.56 · 12 % · -3 · 2026 (también dentro de «Q1»).
NUMBER = re.compile(r"[-+−]?\d(?:[\d  .,]*\d)?(?:\s?%)?")
CANONICAL_NUMBER = re.compile(r"(-?)(\d+)(?:\.(\d+))?")
MAX_DIGITS = 200


def free_text(text: str) -> tuple[list[Segment], int]:
    """Texto escrito por el modelo: cada número se sustituye por una marca visible."""
    segments: list[Segment] = []
    count = 0
    position = 0
    for match in NUMBER.finditer(text):
        if match.start() > position:
            segments.append(Segment(kind="text", text=text[position : match.start()]))
        segments.append(Segment(kind="unverified", text=UNVERIFIED))
        count += 1
        position = match.end()
    if position < len(text):
        segments.append(Segment(kind="text", text=text[position:]))
    return merge(segments), count


def plain_text(text: str) -> tuple[list[Segment], int]:
    """Mensaje de una propuesta: no admite referencias; cualquiera se trata como cifra."""
    count = len(ANY_BRACES.findall(text))
    segments, numbers = free_text(ANY_BRACES.sub(UNVERIFIED, text))
    return segments, numbers + count


def verify_explanation(
    text: str, cells: dict[str, ResultCell], execution: UUID
) -> tuple[list[Segment], int, list[str]]:
    """Sustituye cada {{evidence:id}} por la cifra exacta y formateada y cada {{label:id}} por
    la etiqueta de grupo y periodo de esa cifra (contienen dígitos, como «2026-01», y no pueden
    escribirse libremente). Devuelve los segmentos, cuántos números libres se retiraron y las
    referencias inválidas (inexistentes, ajenas o mal formadas): con alguna, la respuesta
    completa se descarta."""
    invalid = []
    for block in ANY_BRACES.findall(text):
        match = REFERENCE.fullmatch(block)
        if match is None or match.group(2) not in cells:
            invalid.append(block)
    if invalid:
        return [], 0, invalid
    segments: list[Segment] = []
    removed = 0
    position = 0
    for match in REFERENCE.finditer(text):
        chunk, count = free_text(text[position : match.start()])
        segments.extend(chunk)
        removed += count
        cell = cells[match.group(2)]
        if match.group(1) == "label":
            segments.append(Segment(kind="text", text=format_label(cell)))
        else:
            segments.append(
                Segment(
                    kind="evidence",
                    text=format_cell(cell),
                    evidence_id=cell.evidence_id,
                    execution_id=execution,
                )
            )
        position = match.end()
    chunk, count = free_text(text[position:])
    segments.extend(chunk)
    return merge(segments), removed + count, []


def merge(segments: list[Segment]) -> list[Segment]:
    result: list[Segment] = []
    for segment in segments:
        if result and segment.kind == "text" and result[-1].kind == "text":
            result[-1] = Segment(kind="text", text=result[-1].text + segment.text)
        elif segment.text:
            result.append(segment)
    return result


def format_number(value: str) -> str:
    """Formato colombiano: punto de miles y coma decimal, sin perder dígitos. Trabaja sobre la
    cadena canónica: `format(Decimal, "f")` usa la precisión del contexto (28 dígitos) y
    redondearía un Decimal(38, s)."""
    match = CANONICAL_NUMBER.fullmatch(value)
    if match is None:
        try:
            with localcontext(Context(prec=MAX_DIGITS)):
                plain = format(Decimal(value), "f")
        except InvalidOperation:
            return value
        match = CANONICAL_NUMBER.fullmatch(plain)
        if match is None:
            return value
    sign, integer, fraction = match.group(1), match.group(2), match.group(3) or ""
    if not integer.strip("0") and not fraction.strip("0"):
        sign = ""  # sin «-0»
    groups: list[str] = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return sign + ".".join(groups) + ("," + fraction if fraction else "")


def format_label(cell: ResultCell) -> str:
    parts = [value if value is not None else "(sin valor)" for value in cell.group.values()]
    if cell.period:
        parts.append(cell.period)
    return ", ".join(parts) if parts else "todo el resultado"


def format_cell(cell: ResultCell) -> str:
    if cell.value is None:
        return "sin dato"
    if cell.cell == "rank":
        return f"puesto {cell.value}"
    text = format_number(cell.value)
    if cell.cell in {"change_pct", "share_of_total"}:
        return f"{text} %"
    if cell.aggregation in {"count", "count_distinct"}:
        return text
    suffix = cell.currency or cell.unit
    return f"{text} {suffix}" if suffix else text


# --- Resolución de propuestas -------------------------------------------------------------------


def problem(code: str, message: str, resolve_in: str = "proposal") -> ProposalProblem:
    return ProposalProblem.model_validate(
        {"code": code, "message": message, "resolve_in": resolve_in}
    )


def as_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(str(value))
    except ValueError:
        return None


class Resolver:
    """Traduce IDs del modelo a referencias reales. Lo que no existe en el contexto es un
    problema de la propuesta, nunca se adivina por nombre."""

    def __init__(self, table: TableContext, metrics: list[MetricFact]) -> None:
        self.table = table
        self.columns = {c.id: c for c in table.columns}
        self.metrics = {m.revision_id: m for m in metrics}
        self.problems: list[ProposalProblem] = []

    def column(self, raw: str | None, what: str) -> ColumnFact | None:
        identifier = as_uuid(raw)
        column = self.columns.get(identifier) if identifier else None
        if column is None:
            self.problems.append(
                problem("UNKNOWN_COLUMN", f"La {what} propuesta no existe en esta tabla.")
            )
        return column

    def metric(self, raw: str | None) -> MetricFact | None:
        identifier = as_uuid(raw)
        metric = self.metrics.get(identifier) if identifier else None
        if metric is None:
            self.problems.append(
                problem(
                    "UNKNOWN_METRIC",
                    "La consulta cita una métrica que no está definida en este proyecto.",
                    "metrics",
                )
            )
        elif not metric.applicable:
            self.problems.append(
                problem(
                    "METRIC_NOT_APPLICABLE",
                    f"La métrica «{metric.label}» no se puede usar en esta versión.",
                    "metrics",
                )
            )
        return metric

    def filters(self, proposed: list[ProposedFilter]) -> list[dict[str, Any]]:
        result = []
        for item in proposed:
            column = self.column(item.column_id, "columna del filtro")
            if column:
                result.append(
                    {"column_id": str(column.id), "operator": item.operator, "values": item.values}
                )
        return result


def resolve_query(
    proposal: QueryProposal, table: TableContext, metrics: list[MetricFact]
) -> tuple[dict[str, Any], list[ProposalProblem]]:
    """analytics.query@2 con métricas existentes; el servidor añade los hashes."""
    r = Resolver(table, metrics)
    chosen = [m for m in (r.metric(raw) for raw in proposal.metric_ids) if m]
    if not proposal.metric_ids:
        r.problems.append(problem("EMPTY_QUERY", "La consulta no cita ninguna métrica.", "metrics"))
    dimensions = [c for c in (r.column(raw, "dimensión") for raw in proposal.dimension_ids) if c]
    filters = r.filters(proposal.filters)
    ranking = None
    if proposal.ranking_metric_id is not None:
        target = r.metric(proposal.ranking_metric_id)
        if target:
            ranking = {
                "metric_revision_id": str(target.revision_id),
                "direction": proposal.ranking_direction or "desc",
                "top_n": proposal.top_n or 10,
            }
    share = [m for m in (r.metric(raw) for raw in proposal.share_metric_ids) if m]
    time_range = (
        {"start": proposal.time_start, "end": proposal.time_end}
        if proposal.time_start or proposal.time_end
        else None
    )
    parameters: dict[str, Any] = {
        "metrics": [
            {"revision_id": str(m.revision_id), "content_sha256": m.content_sha256} for m in chosen
        ],
        "dimensions": [str(c.id) for c in dimensions],
        "filters": filters,
        "time_grain": proposal.time_grain,
        "time_range": time_range,
        "comparisons": list(proposal.comparisons),
        "ranking": ranking,
        "share_of_total": [str(m.revision_id) for m in share],
    }
    summary = {
        "steps": [
            {
                "id": "query",
                "operation": "analytics.query",
                "version": 2,
                "input": {"kind": "input"},
                "parameters": parameters,
            }
        ],
        "metrics": [NamedRef(id=str(m.revision_id), name=m.label) for m in chosen],
        "dimensions": [NamedRef(id=str(c.id), name=c.name) for c in dimensions],
        "time_grain": proposal.time_grain,
        "time_range": time_range,
        "comparisons": list(proposal.comparisons),
        "ranking": ranking,
        "share_of_total": [NamedRef(id=str(m.revision_id), name=m.label) for m in share],
    }
    return summary, r.problems


def resolve_metric(
    proposal: MetricProposal, table: TableContext
) -> tuple[dict[str, Any], ColumnFact | None, ColumnFact | None, list[ProposalProblem]]:
    r = Resolver(table, [])
    measure = r.column(proposal.measure_column_id, "columna medida")
    time = (
        r.column(proposal.time_column_id, "columna de fecha") if proposal.time_column_id else None
    )
    filters = r.filters(proposal.filters)
    label = proposal.label.strip()[:120] or "Métrica propuesta"
    if (
        measure
        and proposal.aggregation in {"sum", "avg", "min", "max"}
        and measure.technical_type not in NUMERIC_TYPES
    ):
        r.problems.append(
            problem(
                "COLUMN_TYPE_MISMATCH",
                f"«{measure.name}» no es numérica: conviértela en Limpieza antes de sumarla.",
                "plan",
            )
        )
    if time and time.technical_type != "date":
        r.problems.append(
            problem(
                "COLUMN_TYPE_MISMATCH",
                f"«{time.name}» no es una fecha: conviértela en Limpieza.",
                "plan",
            )
        )
    draft = {
        "label": label,
        "description": (proposal.description or None) and proposal.description[:300],
        "measure_column_id": str(measure.id) if measure else proposal.measure_column_id,
        "aggregation": proposal.aggregation,
        "filters": filters,
        "time_column_id": str(time.id) if time else None,
        "null_policy": "exclude",
    }
    return draft, measure, time, r.problems


def resolve_cleaning(
    steps: list[CleaningStepProposal],
) -> tuple[list[dict[str, Any]], list[ProposalProblem]]:
    """Cadena lineal de pasos de limpieza. Una operación que no es de limpieza se rechaza aquí;
    las desconocidas o con parámetros inválidos las informa planning."""
    problems: list[ProposalProblem] = []
    result: list[dict[str, Any]] = []
    if not steps:
        problems.append(problem("EMPTY_PLAN", "La propuesta no tiene pasos de limpieza."))
    for index, step in enumerate(steps, start=1):
        name, _, version = step.operation.partition("@")
        if not name.startswith("cleaning."):
            problems.append(
                problem(
                    "NOT_A_CLEANING_OPERATION",
                    f"«{name}» no es una operación de limpieza del catálogo.",
                )
            )
            continue
        try:
            parameters = json.loads(step.parameters_json)
        except json.JSONDecodeError:
            parameters = None
        if not isinstance(parameters, dict):
            problems.append(
                problem("INVALID_PARAMETERS", f"Los parámetros de «{name}» no son un objeto.")
            )
            continue
        result.append(
            {
                "id": f"s{index}",
                "operation": name,
                "version": int(version) if version.isdigit() else step.version,
                "input": {"kind": "step", "step_id": result[-1]["id"]}
                if result
                else {"kind": "input"},
                "parameters": parameters,
            }
        )
    return result, problems


def clarification_target(topic: ClarificationTopic) -> str:
    if topic in {"measure", "currency", "business_date"}:
        return "understanding"
    if topic == "metric":
        return "metrics"
    return "conversation"


def planning_problems(raw: list[tuple[str, str, str]]) -> list[ProposalProblem]:
    """Problemas de planning (código, mensaje, dónde se resuelve)."""
    return [
        problem(code, message, "understanding" if where == "understanding" else "plan")
        for code, message, where in raw
    ]
