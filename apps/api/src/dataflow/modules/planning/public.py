from dataflow.modules.planning.contracts import (
    CATALOG_VERSION,
    COLUMN_REF,
    ConfirmedColumnRole,
    OperationCatalog,
    OperationDescriptor,
    SemanticRevisionRequirement,
)

# Puerto que bootstrap implementa registrando descriptor y ejecutor de cada operación.
OperationRegistry = OperationCatalog

__all__ = [
    "CATALOG_VERSION",
    "COLUMN_REF",
    "ConfirmedColumnRole",
    "OperationDescriptor",
    "OperationRegistry",
    "SemanticRevisionRequirement",
]
