"""Presentación de cifras del informe (Fase 24B, ADR-042): como mucho tres decimales.

Sólo cambia cómo se lee una cifra en el PDF: las cifras canónicas, sus evidencias y los
artefactos guardados no cambian. Regla `display-decimals-v1`:

- una cifra con cuatro o más decimales se redondea a tres, mitad hacia arriba (lejos de cero);
- si se redondeó, se quitan los ceros finales que deja el redondeo (1,29999 → 1,3; 2,0004 → 2);
- una cifra con tres decimales o menos se deja tal cual (12,50 sigue siendo 12,50);
- vale para la escritura canónica (1234.56789) y para la española (1.234,56789): los separadores
  de miles siempre agrupan tres cifras, así que un separador seguido de cuatro o más cifras sólo
  puede ser el decimal.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

DECIMALS = 3
# Una cifra: dígitos con separadores entre ellos, sin letras ni dígitos pegados a los lados.
NUMBER = re.compile(r"(?<![\w.,])-?\d[\d.,]*\d(?![\w])")


def cap_number(token: str) -> str:
    """Una cifra con como mucho tres decimales (la regla del módulo)."""
    negative = token.startswith("-")
    body = token[1:] if negative else token
    position = max(body.rfind("."), body.rfind(","))
    if position < 0:
        return token
    fraction = body[position + 1 :]
    if len(fraction) <= DECIMALS or not fraction.isdigit():
        return token
    decimal_mark = body[position]
    head = body[:position]
    grouping = "." if decimal_mark == "," else ","
    digits = head.replace(grouping, "")
    if not digits.isdigit():
        return token
    rounded = Decimal(f"{digits}.{fraction}").quantize(
        Decimal(1).scaleb(-DECIMALS), rounding=ROUND_HALF_UP
    )
    integer, _, decimals = f"{rounded:f}".partition(".")
    decimals = decimals.rstrip("0")
    # La escritura española agrupa los miles; si el redondeo añade una cifra (999,9996 → 1.000),
    # también se agrupa.
    if grouping in head or (decimal_mark == "," and len(digits) <= 3):
        integer = re.sub(r"\B(?=(\d{3})+(?!\d))", grouping, integer)
    sign = "-" if negative and (integer.strip("0" + grouping) or decimals) else ""
    return f"{sign}{integer}{decimal_mark}{decimals}" if decimals else f"{sign}{integer}"


def cap_decimals(text: str) -> str:
    """El texto con cada cifra limitada a tres decimales; lo demás no cambia."""
    return NUMBER.sub(lambda match: cap_number(match.group(0)), text)
