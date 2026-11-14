from dataflow.modules.planning.automatic import plan_analyses
from dataflow.modules.planning.contracts import (
    CATALOG_VERSION,
    COLUMN_REF,
    AnalysisPlan,
    ConfirmedColumnRole,
    IdentifierConversionGuard,
    OperationCatalog,
    OperationDescriptor,
    PlannedAnalysis,
    SemanticRevisionRequirement,
)

# Puerto que bootstrap implementa registrando descriptor y ejecutor de cada operación.
OperationRegistry = OperationCatalog

__all__ = [
    "AnalysisPlan",
    "PlannedAnalysis",
    "plan_analyses",
    "CATALOG_VERSION",
    "COLUMN_REF",
    "ConfirmedColumnRole",
    "IdentifierConversionGuard",
    "OperationDescriptor",
    "OperationRegistry",
    "SemanticRevisionRequirement",
]
