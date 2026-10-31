from sqlalchemy.orm import Session

from dataflow.bootstrap.provenance import environment_snapshot
from dataflow.bootstrap.semantic_access import SemanticRepresentationAccess
from dataflow.modules.datasets.application import Datasets
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.application import ExecutionRunner, Executions
from dataflow.modules.executions.contracts import Artifact, Lease, ProcessingConfig
from dataflow.modules.executions.infrastructure import SQLExecutionRepository
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer, PolarsPreview
from dataflow.modules.ingestion.application import AnalysisService, Analyzer, IngestionService
from dataflow.modules.ingestion.executor import CsvExecutor, TableExecutor
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.application import SemanticService
from dataflow.modules.understanding.semantic_repository import SQLSemanticRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import SQLUnitOfWork
from dataflow.platform.runtime import require_ready


def processing_config() -> ProcessingConfig:
    settings = get_settings()
    return ProcessingConfig(
        max_rows=settings.max_csv_rows,
        max_columns=settings.max_csv_columns,
        timeout_seconds=settings.processing_timeout_seconds,
    )


def make_datasets(db: Session) -> Datasets:
    return Datasets(SQLDatasetRepository(db))


def make_executions(db: Session) -> Executions:
    return Executions(SQLExecutionRepository(db, make_datasets(db)), SQLUnitOfWork(db))


def make_ingestion(db: Session, objects: LocalObjects) -> IngestionService:
    require_ready(db)
    settings = get_settings()
    return IngestionService(
        make_datasets(db),
        make_executions(db),
        objects,
        ProjectPermissions(db),
        PolarsPreview(),
        SQLUnitOfWork(db),
        processing_config(),
        settings.max_owner_storage_bytes,
        settings.max_upload_bytes,
    )


def make_analysis(db: Session, objects: LocalObjects) -> AnalysisService:
    require_ready(db)
    return AnalysisService(
        make_datasets(db),
        make_executions(db),
        objects,
        ProjectPermissions(db),
        SQLUnitOfWork(db),
        processing_config(),
        make_semantics(db, objects),
    )


def make_semantics(db: Session, objects: LocalObjects) -> SemanticService:
    require_ready(db)
    access = SemanticRepresentationAccess(
        make_datasets(db), make_executions(db), objects, ProjectPermissions(db)
    )
    return SemanticService(SQLSemanticRepository(db), access, SQLUnitOfWork(db))


class DatasetPublication:
    def __init__(self, datasets: Datasets) -> None:
        self.datasets = datasets

    def published(self, lease: Lease, artifacts: list[Artifact]) -> None:
        if lease.execution.kind == "csv_import":
            self.datasets.materialized(
                lease.version_id,
                lease.execution_id,
                {artifact.kind: artifact.id for artifact in artifacts},
            )


def make_runner(
    db: Session, objects: LocalObjects, analyzer: Analyzer | None = None
) -> ExecutionRunner:
    require_ready(db)
    datasets, executions = make_datasets(db), make_executions(db)
    config = processing_config()
    executor = analyzer or IsolatedAnalyzer(
        objects.root, config.timeout_seconds, config.max_rows, config.max_columns
    )
    projects = ProjectPermissions(db)
    return ExecutionRunner(
        SQLExecutionRepository(db, datasets),
        SQLUnitOfWork(db),
        {
            "csv_import": CsvExecutor(datasets, executions, objects, executor, projects),
            "table_analysis": TableExecutor(
                datasets, executions, objects, executor, projects, make_semantics(db, objects)
            ),
        },
        DatasetPublication(datasets),
        environment_snapshot(),
    )
