"""Catálogo de operaciones: único lugar que une descriptores de planning con ejecutores."""

from collections.abc import Mapping

from dataflow.modules.analytics.contracts import (
    QueryParameters,
    QueryParametersV2,
    QueryParametersV3,
)
from dataflow.modules.cleaning.public import (
    CastParameters,
    DeduplicateParameters,
    FilterRowsParameters,
    NormalizeNullTokensParameters,
    TrimWhitespaceParameters,
    cast_column_types,
    cast_output_schema,
    deduplicate_column_types,
    filter_column_types,
    tokens_column_types,
    trim_column_types,
)
from dataflow.modules.executions.public import StepExecutor, StepRegistry
from dataflow.modules.ingestion.contracts import ReadCsvParameters, ReadXlsxParameters
from dataflow.modules.planning.public import (
    CATALOG_VERSION,
    IdentifierConversionGuard,
    OperationDescriptor,
)
from dataflow.modules.quality.contracts import AnalyticalQualityParameters, QualityParameters
from dataflow.modules.quality.public import QualityRulesParameters
from dataflow.modules.understanding.contracts import (
    AnalyticalProfileParameters,
    AutomaticProfileParameters,
    InterpretedProfileParameters,
    ProfileParameters,
)
from dataflow.platform.data_types import ALL_TYPES, NUMERIC

# Sólo operaciones con ejecutor real; ninguna exige revisión semántica (Fase 3). Las de
# limpieza transforman datos: se ejecutan con vista previa y aprobación, nunca como "plan".
DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    OperationDescriptor("ingestion.read_csv", 1, "Leer CSV", "source", "table", ReadCsvParameters),
    OperationDescriptor(
        "ingestion.read_xlsx", 1, "Leer Excel (.xlsx)", "source", "table", ReadXlsxParameters
    ),
    OperationDescriptor(
        "understanding.profile", 1, "Perfil de columnas", "table", "profile", ProfileParameters
    ),
    OperationDescriptor(
        "understanding.profile",
        2,
        "Perfil y dashboard automático",
        "table",
        "profile",
        AutomaticProfileParameters,
    ),
    OperationDescriptor(
        "understanding.profile",
        3,
        "Dashboard e interpretación automática",
        "table",
        "profile",
        InterpretedProfileParameters,
    ),
    OperationDescriptor(
        "understanding.profile",
        4,
        "Interpretación analítica y dashboard por medidas",
        "table",
        "profile",
        AnalyticalProfileParameters,
    ),
    OperationDescriptor(
        "quality.evaluate", 1, "Evaluar calidad", "table", "quality", QualityParameters
    ),
    OperationDescriptor(
        "quality.evaluate",
        3,
        "Evaluar calidad y análisis afectados",
        "table",
        "quality",
        AnalyticalQualityParameters,
    ),
    OperationDescriptor(
        "quality.evaluate",
        2,
        "Evaluar reglas de calidad",
        "table",
        "quality_rules",
        QualityRulesParameters,
        ruleset_reference=("ruleset_revision_id", "ruleset_sha256"),
    ),
    OperationDescriptor(
        "analytics.query",
        1,
        "Consultar métricas",
        "table",
        "analysis_result",
        QueryParameters,
        column_types=lambda parameters: {"filter_column_ids": ALL_TYPES},
        metric_reference="metrics",
    ),
    OperationDescriptor(
        "analytics.query",
        2,
        "Consultar, comparar y ordenar métricas",
        "table",
        "analysis_result",
        QueryParametersV2,
        column_types=lambda parameters: {"filter_column_ids": ALL_TYPES},
        metric_reference="metrics",
        additive_metrics="share_of_total",
    ),
    OperationDescriptor(
        "analytics.query",
        3,
        "Consultar métricas con productos y último corte",
        "table",
        "analysis_result",
        QueryParametersV3,
        column_types=lambda parameters: {"filter_column_ids": ALL_TYPES},
        metric_reference="metrics",
        additive_metrics="share_of_total",
    ),
    OperationDescriptor(
        "cleaning.trim_whitespace",
        1,
        "Recortar espacios",
        "table",
        "table",
        TrimWhitespaceParameters,
        transforms_data=True,
        column_types=trim_column_types,
    ),
    OperationDescriptor(
        "cleaning.filter_rows",
        1,
        "Excluir registros",
        "table",
        "table",
        FilterRowsParameters,
        transforms_data=True,
        column_types=filter_column_types,
    ),
    OperationDescriptor(
        "cleaning.normalize_null_tokens",
        1,
        "Convertir marcadores en nulos",
        "table",
        "table",
        NormalizeNullTokensParameters,
        transforms_data=True,
        column_types=tokens_column_types,
    ),
    OperationDescriptor(
        "cleaning.cast",
        1,
        "Convertir tipo",
        "table",
        "table",
        CastParameters,
        transforms_data=True,
        column_types=cast_column_types,
        output_schema=cast_output_schema,
        identifier_guard=IdentifierConversionGuard(
            "column_id", "type", "confirm_identifier_conversion", NUMERIC
        ),
    ),
    OperationDescriptor(
        "cleaning.deduplicate",
        1,
        "Eliminar duplicados",
        "table",
        "table",
        DeduplicateParameters,
        transforms_data=True,
        column_types=deduplicate_column_types,
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


class WorkerRegistry:
    """Catálogo planificable más operaciones internas del worker (no planificables)."""

    def __init__(self, catalog: StepRegistry, internal: dict[str, StepExecutor]) -> None:
        self.catalog, self.internal = catalog, internal

    def executor(self, operation: str, version: int) -> StepExecutor | None:
        return self.catalog.executor(operation, version) or self.internal.get(
            f"{operation}@{version}"
        )
