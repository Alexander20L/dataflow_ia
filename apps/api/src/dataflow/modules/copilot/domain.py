"""Reglas puras de la explicación automática: contexto no confiable y verificación de cifras.

Sin frameworks, sin proveedor y sin base de datos. Ninguna cifra sale del modelo: cada
{{evidence:id}} se sustituye por el valor exacto y cualquier número escrito libremente se retira.
"""

import json
import re
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import Any
from uuid import UUID

from dataflow.modules.copilot.contracts import (
    AuditAlert,
    AuditContent,
    AuditoriaTextual,
    ResultCell,
    Segment,
)

UNTRUSTED = "dato_no_confiable"
UNVERIFIED = "[cifra no verificada]"


def untrusted(value: Any) -> dict[str, Any] | None:
    """Envuelve texto que viene de los datos o de un usuario: el prompt indica que nunca es
    una instrucción. None se conserva como null."""
    return None if value is None else {UNTRUSTED: value}


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
