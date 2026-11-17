"""Interfaz pública del módulo de investigación (Fase 16)."""

from dataflow.modules.investigation.application import (
    Explainer,
    FollowUps,
    Investigator,
    Proposer,
    explained_figures,
)
from dataflow.modules.investigation.domain import KINDS, Catalog, rule_queries, validate

__all__ = [
    "KINDS",
    "Catalog",
    "Explainer",
    "FollowUps",
    "Investigator",
    "Proposer",
    "explained_figures",
    "rule_queries",
    "validate",
]
