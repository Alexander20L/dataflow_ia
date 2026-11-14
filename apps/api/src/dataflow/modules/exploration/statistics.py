"""Estadística de la investigación en Python puro (Fase 29, ADR-047, `relevance-v3`).

Sin dependencias nuevas: las distribuciones se calculan con las funciones gamma y beta
incompletas regularizadas (fracciones continuas de Lentz, como en Numerical Recipes), con
precisión de sobra para decidir si un valor p es menor que 0,05.

- Tasas por grupo: prueba chi-cuadrado de independencia (k × 2) e intervalo de Wilson al 95 %.
- Medias por grupo: prueba de Kruskal-Wallis (con corrección por empates) e intervalo t al 95 %.
- Varias pruebas en una investigación: corrección de Benjamini-Hochberg (valores q).

Todo es determinista: mismas entradas, mismas cifras.
"""

import math
from collections.abc import Sequence

Z95 = 1.959963984540054  # cuantil 0,975 de la normal estándar
ALPHA = 0.05
_EPS = 1e-15
_TINY = 1e-300
_ITERATIONS = 500


def _gamma_series(a: float, x: float) -> float:
    """P(a, x) por su serie (para x < a + 1)."""
    total = term = 1.0 / a
    current = a
    for _ in range(_ITERATIONS):
        current += 1
        term *= x / current
        total += term
        if abs(term) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_fraction(a: float, x: float) -> float:
    """Q(a, x) por fracción continua (para x ≥ a + 1)."""
    b = x + 1 - a
    c = 1 / _TINY
    d = 1 / b
    h = d
    for i in range(1, _ITERATIONS):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = _TINY if abs(d) < _TINY else d
        c = b + an / c
        c = _TINY if abs(c) < _TINY else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gamma_q(a: float, x: float) -> float:
    """Función gamma incompleta superior regularizada Q(a, x)."""
    if x <= 0:
        return 1.0
    if x < a + 1:
        return max(0.0, min(1.0, 1 - _gamma_series(a, x)))
    return max(0.0, min(1.0, _gamma_fraction(a, x)))


def chi2_sf(statistic: float, df: int) -> float:
    """P(χ²(df) ≥ statistic)."""
    if df <= 0:
        return 1.0
    return gamma_q(df / 2, statistic / 2)


def _beta_fraction(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1 - qab * x / qap
    d = _TINY if abs(d) < _TINY else d
    d = 1 / d
    h = d
    for m in range(1, _ITERATIONS):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = _TINY if abs(d) < _TINY else d
        c = 1 + aa / c
        c = _TINY if abs(c) < _TINY else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = _TINY if abs(d) < _TINY else d
        c = 1 + aa / c
        c = _TINY if abs(c) < _TINY else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < _EPS:
            break
    return h


def beta_i(a: float, b: float, x: float) -> float:
    """Función beta incompleta regularizada I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _beta_fraction(a, b, x) / a
    return 1 - front * _beta_fraction(b, a, 1 - x) / b


def t_cdf(t: float, df: int) -> float:
    tail = 0.5 * beta_i(df / 2, 0.5, df / (df + t * t))
    return 1 - tail if t >= 0 else tail


def t_quantile(p: float, df: int) -> float:
    """Cuantil de la t de Student por bisección (p entre 0,5 y 1)."""
    low, high = 0.0, 1000.0
    for _ in range(200):
        middle = (low + high) / 2
        if t_cdf(middle, df) < p:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def wilson(cases: int, total: int, z: float = Z95) -> tuple[float, float]:
    """Intervalo de Wilson de una proporción (en tanto por uno)."""
    if total <= 0:
        return 0.0, 0.0
    p = cases / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def mean_interval(values: Sequence[float]) -> tuple[float, float, float] | None:
    """Media e intervalo t al 95 % (hacen falta al menos dos valores)."""
    n = len(values)
    if n < 2:
        return None
    mean = math.fsum(values) / n
    variance = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    half = t_quantile(0.975, n - 1) * math.sqrt(variance / n)
    return mean, mean - half, mean + half


def chi_square(table: Sequence[tuple[int, int]]) -> tuple[float, int, float, float] | None:
    """Independencia de una tabla k × 2 (casos, no casos por grupo): estadístico, grados de
    libertad, valor p y V de Cramér. None si no hay variación o menos de dos grupos."""
    rows = [(a, b) for a, b in table if a + b > 0]
    if len(rows) < 2:
        return None
    total = sum(a + b for a, b in rows)
    cases = sum(a for a, _ in rows)
    if cases in {0, total}:
        return None
    statistic = 0.0
    for a, b in rows:
        size = a + b
        for observed, column in ((a, cases), (b, total - cases)):
            expected = size * column / total
            statistic += (observed - expected) ** 2 / expected
    df = len(rows) - 1
    return statistic, df, chi2_sf(statistic, df), math.sqrt(statistic / total)


def kruskal_wallis(groups: Sequence[Sequence[float]]) -> tuple[float, int, float, float] | None:
    """Kruskal-Wallis con corrección por empates: H, grados de libertad, valor p y épsilon
    cuadrado (tamaño del efecto). None con menos de dos grupos o sin variación."""
    kept = [list(g) for g in groups if g]
    if len(kept) < 2:
        return None
    pooled = sorted((value, index) for index, group in enumerate(kept) for value in group)
    n = len(pooled)
    ranks = [0.0] * n
    ties = 0.0
    start = 0
    while start < n:
        end = start
        while end + 1 < n and pooled[end + 1][0] == pooled[start][0]:
            end += 1
        rank = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[position] = rank
        size = end - start + 1
        ties += size**3 - size
        start = end + 1
    correction = 1 - ties / (n**3 - n)
    if correction <= 0:
        return None
    sums = [0.0] * len(kept)
    for (_, index), rank in zip(pooled, ranks, strict=True):
        sums[index] += rank
    h = 12 / (n * (n + 1)) * sum(s * s / len(g) for s, g in zip(sums, kept, strict=True))
    h = (h - 3 * (n + 1)) / correction
    df = len(kept) - 1
    return h, df, chi2_sf(h, df), max(0.0, h / (n - 1))


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Valores q (tasa de falsos descubrimientos) en el mismo orden que los p."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    previous = 1.0
    for position in range(m - 1, -1, -1):
        index = order[position]
        value = min(previous, p_values[index] * m / (position + 1))
        adjusted[index] = previous = min(1.0, value)
    return adjusted


def p_text(value: float) -> str:
    """El valor p como se lee: «p < 0,001» o «p = 0,032»."""
    if value < 0.001:
        return "p < 0,001"
    return "p = " + format(value, ".3f").replace(".", ",")
