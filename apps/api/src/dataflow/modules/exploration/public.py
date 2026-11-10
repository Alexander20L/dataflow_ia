"""Interfaz pública de la exploración guiada (Fase 20)."""

from dataflow.modules.exploration.domain import KINDS, Catalog, rule_queries, validate
from dataflow.modules.exploration.engine import compute

__all__ = ["KINDS", "Catalog", "compute", "rule_queries", "validate"]
