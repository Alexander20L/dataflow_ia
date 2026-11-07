"""Contexto decimal único del cálculo exacto (Fase 11.0).

El contexto por defecto de Python tiene 28 dígitos de precisión: con `Decimal(38, s)` redondea
sumas y restas sin avisar. Todo cálculo con decimales del motor (sumas, medias, variaciones,
participaciones, cuantización) usa este contexto. Con 4 × 38 dígitos, una suma de N valores de
hasta 38 dígitos (que necesita 38 + log10(N) + 1) nunca se redondea; los cocientes se cuantizan
después con HALF_EVEN y un resultado de más de 38 dígitos es un error explícito
(`RESULT_PRECISION_EXCEEDED`), no un redondeo.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Context, localcontext

from dataflow.platform.data_types import MAX_DECIMAL_PRECISION

EXACT_PRECISION = 4 * MAX_DECIMAL_PRECISION


@contextmanager
def exact_context() -> Iterator[Context]:
    with localcontext() as context:
        context.prec = EXACT_PRECISION
        yield context
