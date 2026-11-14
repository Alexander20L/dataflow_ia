"""¿Una fecha registra eventos o describe a la entidad? (Fase 28, ADR-046, `date-role-v1`).

Una columna de fecha no siempre es una línea de tiempo. En un registro de ventas cada fila es un
evento (una venta en su día) y la evolución mensual tiene sentido. En un padrón de empleados cada
fila es una persona y su fecha de ingreso la describe: casi cada mes tiene uno o ningún registro,
y una «evolución mensual del salario» compararía personas sueltas.

Regla pura, compartida por la inspección y la comprensión para que nunca digan cosas distintas:
la fecha es un **atributo** cuando el grano es una entidad (una clave única por fila que no
incluye las columnas del periodo) y la mediana de registros por mes observado es menor que
`MIN_EVENTS_PER_MONTH`. Si no, registra **eventos** (una serie con una fila por mes, cuya clave es
el propio periodo, también).
"""

from collections.abc import Sequence
from typing import Literal

RULE = "date-role-v1"
MIN_EVENTS_PER_MONTH = 2

DateRole = Literal["events", "attribute"]


def median(values: Sequence[int]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def date_role(unique_key: bool, per_month: Sequence[int]) -> DateRole:
    """`unique_key`: hay una clave única por fila (el grano es una entidad). `per_month`:
    registros de cada mes con al menos uno."""
    if unique_key and per_month and median(per_month) < MIN_EVENTS_PER_MONTH:
        return "attribute"
    return "events"


def explain(role: DateRole, column: str, per_month: Sequence[int]) -> str:
    typical = median(per_month)
    shown = format(typical, "g").replace(".", ",")
    if role == "attribute":
        return (
            f"«{column}» describe a cada registro (mediana de {shown} registros por mes y una "
            "clave única por fila): no es una línea de tiempo de eventos, así que no se analiza "
            "su evolución mensual."
        )
    return f"«{column}» registra eventos (mediana de {shown} registros por mes)."
