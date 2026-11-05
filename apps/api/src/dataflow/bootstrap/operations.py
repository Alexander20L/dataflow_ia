"""Catálogo de operaciones: único lugar que une descriptores de planning con ejecutores."""

from collections.abc import Mapping

from dataflow.modules.executions.public import StepExecutor
from dataflow.modules.ingestion.contracts import ReadCsvParameters
from dataflow.modules.planning.public import CATALOG_VERSION, OperationDescriptor
from dataflow.modules.quality.contracts import QualityParameters
from dataflow.modules.understanding.contracts import ProfileParameters

# Fase 4: sólo operaciones con ejecutor real; ninguna exige revisión semántica (Fase 3).
DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    OperationDescriptor("ingestion.read_csv", 1, "Leer CSV", "source", "table", ReadCsvParameters),
    OperationDescriptor(
        "understanding.profile", 1, "Perfil de columnas", "table", "profile", ProfileParameters
    ),
    OperationDescriptor(
        "quality.evaluate", 1, "Evaluar calidad", "table", "quality", QualityParameters
    ),
)


class OperationCatalog:
    """Descriptores sin ejecutores: suficiente para validar y publicar el catálogo."""

    catalog_version = CATALOG_VERSION

    def __init__(self, descriptors: tuple[OperationDescriptor, ...] = DESCRIPTORS) -> None:
        self.by_key = {(d.name, d.version): d for d in descriptors}

    def descriptors(self) -> list[OperationDescriptor]:
        return list(self.by_key.values())

    def descriptor(self, name: str, version: int) -> OperationDescriptor | None:
        return self.by_key.get((name, version))


class OperationRegistry(OperationCatalog):
    """Catálogo + ejecutores; executions sólo ve el puerto StepRegistry."""

    def __init__(
        self,
        executors: Mapping[str, StepExecutor],
        descriptors: tuple[OperationDescriptor, ...] = DESCRIPTORS,
    ) -> None:
        super().__init__(descriptors)
        keys = {d.key for d in descriptors}
        if set(executors) != keys:
            raise ValueError(f"Registro incompleto: {sorted(keys ^ set(executors))}")
        for descriptor in descriptors:
            if executors[descriptor.key].output_kind != descriptor.output_kind:
                raise ValueError(f"Salida incoherente para {descriptor.key}")
        self.executors = dict(executors)

    def executor(self, operation: str, version: int) -> StepExecutor | None:
        return self.executors.get(f"{operation}@{version}")
