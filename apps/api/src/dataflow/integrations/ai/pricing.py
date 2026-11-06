"""Costo estimado por llamada (USD). Precios de lista por millón de tokens, revisados el
2026-11-06; una lectura de caché cuesta el 10 % de la entrada y una escritura el 125 %. Un
modelo desconocido no tiene estimación (los límites siguen aplicando por tokens)."""

from decimal import Decimal

from dataflow.integrations.ai.port import AIUsage

PRICES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-opus-5": (Decimal("5"), Decimal("25")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-fable-5-1": (Decimal("10"), Decimal("50")),
    "fake": (Decimal("0"), Decimal("0")),
}
MILLION = Decimal(1_000_000)
SCALE = Decimal("0.000001")


def estimated_cost(model: str, usage: AIUsage) -> Decimal | None:
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    total = (
        usage.input_tokens * input_price
        + usage.cache_read_tokens * input_price * Decimal("0.1")
        + usage.cache_write_tokens * input_price * Decimal("1.25")
        + usage.output_tokens * output_price
    ) / MILLION
    return total.quantize(SCALE)
