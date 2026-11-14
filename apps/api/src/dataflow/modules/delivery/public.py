"""Interfaz pública del módulo de entrega (Fase 17; informe v2 desde la Fase 27)."""

from dataflow.modules.delivery.domain import build_report, progress
from dataflow.modules.delivery.pdf import render_pdf
from dataflow.modules.delivery.report import (
    build_report_v2,
    principal_figures,
    review_items,
    selection_digest_items,
)

__all__ = [
    "build_report",
    "build_report_v2",
    "principal_figures",
    "progress",
    "render_pdf",
    "review_items",
    "selection_digest_items",
]
