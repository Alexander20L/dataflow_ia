"""Interfaz pública de la exploración guiada (Fase 20) y, desde la Fase 26, del cálculo exacto
que usa el dashboard (indicadores, histogramas, dispersión y filtros)."""

from dataflow.modules.exploration.domain import KINDS, Catalog, rule_queries, title, validate
from dataflow.modules.exploration.engine import compute, row_count, subset

__all__ = [
    "KINDS",
    "Catalog",
    "compute",
    "row_count",
    "rule_queries",
    "subset",
    "title",
    "validate",
]
