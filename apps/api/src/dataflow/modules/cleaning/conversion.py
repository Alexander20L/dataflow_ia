"""Gramáticas de conversión de cleaning.cast@1: viven en platform (contrato §3) porque también
las usa la regla de calidad «formato convertible» (csv-quality-v2)."""

from dataflow.platform.conversion import (
    FORMATS,
    REASONS,
    CastFormat,
    CastType,
    Converted,
    Failed,
    Reason,
    convert,
)

__all__ = [
    "FORMATS",
    "REASONS",
    "CastFormat",
    "CastType",
    "Converted",
    "Failed",
    "Reason",
    "convert",
]
