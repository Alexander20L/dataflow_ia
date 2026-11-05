from uuid import uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.cleaning_access import CleaningPlanAccess
from dataflow.bootstrap.operations import OperationCatalog, OperationRegistry
from dataflow.bootstrap.planning_access import PlanningTableAccess
from dataflow.bootstrap.provenance import environment_snapshot
from dataflow.bootstrap.semantic_access import SemanticRepresentationAccess
from dataflow.modules.audit.public import record_event
from dataflow.modules.cleaning.application import CleaningService
from dataflow.modules.cleaning.engine import IsolatedCleaner
from dataflow.modules.cleaning.public import (
    ApprovalSource,
    derived_version_id,
    require_valid_approval,
)
from dataflow.modules.cleaning.repository import SQLApprovalRepository, SQLApprovalSource
from dataflow.modules.cleaning.steps import (
    ApplyFinalizer,
    FilterRowsStep,
    PreviewFinalizer,
    TrimWhitespaceStep,
)
from dataflow.modules.datasets.application import Datasets
from dataflow.modules.datasets.infrastructure import SQLDatasetRepository
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.application import ExecutionRunner, Executions
from dataflow.modules.executions.contracts import (
    Artifact,
    ArtifactOutput,
    Lease,
    ProcessingConfig,
    RunKind,
)
from dataflow.modules.executions.infrastructure import SQLExecutionRepository
from dataflow.modules.ingestion.analytical import IsolatedAnalyzer, PolarsPreview
from dataflow.modules.ingestion.application import AnalysisService, Analyzer, IngestionService
from dataflow.modules.ingestion.executor import (
    ProfileStep,
    QualityStep,
    ReadCsvStep,
    SourceInputResolver,
    TableInputResolver,
)
from dataflow.modules.ingestion.plans import analysis_fingerprint, build_plan
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.infrastructure import SQLPlanningRepository
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.application import SemanticService
from dataflow.modules.understanding.semantic_repository import SQLSemanticRepository
from dataflow.platform.config import get_settings
from dataflow.platform.database import SQLUnitOfWork
from dataflow.platform.errors import ApplicationError
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
    """Efectos de publicación entre módulos, dentro de la transacción de stage/succeed."""

    def __init__(
        self,
        db: Session,
        datasets: Datasets,
        executions: Executions,
        approvals: ApprovalSource,
        config: ProcessingConfig,
    ) -> None:
        self.db, self.datasets, self.executions = db, datasets, executions
        self.approvals, self.config = approvals, config

    def prepare(self, lease: Lease, outputs: list[ArtifactOutput]) -> None:
        if lease.execution.kind != "cleaning_apply":
            return
        # Revocación comprobada otra vez al confirmar, no sólo al empezar el cálculo.
        require_valid_approval(self.approvals, lease)
        table = next(output for output in outputs if output.kind == "table")
        version = derived_version_id(lease.execution_id)
        if table.version_id != version:
            raise ApplicationError("OUTPUT_MANIFEST_INVALID", "Tabla derivada inválida.", 409)
        self.datasets.register_derived(
            self.datasets.get(lease.owner_id, lease.version_id),
            version,
            lease.execution_id,
            table.content,
        )

    def published(self, lease: Lease, artifacts: list[Artifact]) -> None:
        kind = lease.execution.kind
        if kind == "csv_import":
            self.datasets.materialized(
                lease.version_id,
                lease.execution_id,
                {artifact.kind: artifact.id for artifact in artifacts},
            )
        elif kind == "table_analysis":
            self.datasets.materialize_derived(
                lease.version_id,
                lease.execution_id,
                {artifact.kind: artifact.id for artifact in artifacts},
            )
        elif kind == "cleaning_apply":
            self.derived(lease, next(a for a in artifacts if a.kind == "table"))

    def derived(self, lease: Lease, table: Artifact) -> None:
        """Encola perfil y calidad de la versión derivada y la vincula a ese análisis."""
        version = self.datasets.get(lease.owner_id, table.version_id)
        plan = build_plan(lease.owner_id, version, self.config, table=table)
        run = self.executions.enqueue_followup(
            lease.owner_id,
            version.project_id,
            version.id,
            uuid5(lease.execution_id, "derived-analysis"),
            analysis_fingerprint(version.id, table.id, table.content.sha256, "profile_quality"),
            plan,
            str(lease.execution_id),
            table.id,
            table.content.sha256,
        )
        self.datasets.bind_derived(version.id, run.id, table.id)
        record_event(
            self.db,
            lease.owner_id,
            version.id,
            "dataset.derived_published",
            str(lease.execution_id),
        )


WORKER_KINDS: set[RunKind] = {
    "csv_import",
    "table_analysis",
    "plan",
    "cleaning_preview",
    "cleaning_apply",
}


def make_operations(
    objects: LocalObjects, analyzer: Analyzer, cleaner: IsolatedCleaner
) -> OperationRegistry:
    return OperationRegistry(
        {
            "ingestion.read_csv@1": ReadCsvStep(objects, analyzer),
            "understanding.profile@1": ProfileStep(objects, analyzer),
            "quality.evaluate@1": QualityStep(objects, analyzer),
            "cleaning.trim_whitespace@1": TrimWhitespaceStep(objects, cleaner),
            "cleaning.filter_rows@1": FilterRowsStep(objects, cleaner),
        }
    )


def make_runner(
    db: Session,
    objects: LocalObjects,
    analyzer: Analyzer | None = None,
    kinds: set[RunKind] | None = None,
) -> ExecutionRunner:
    require_ready(db)
    datasets, executions = make_datasets(db), make_executions(db)
    config = processing_config()
    engine = analyzer or IsolatedAnalyzer(
        objects.root, config.timeout_seconds, config.max_rows, config.max_columns
    )
    projects = ProjectPermissions(db)
    cleaner = IsolatedCleaner(objects.root)
    approvals = SQLApprovalSource(db)
    return ExecutionRunner(
        SQLExecutionRepository(db, datasets),
        SQLUnitOfWork(db),
        set(WORKER_KINDS if kinds is None else kinds),
        {
            "source": SourceInputResolver(datasets, projects),
            "table": TableInputResolver(
                datasets, executions, projects, make_semantics(db, objects)
            ),
        },
        make_operations(objects, engine, cleaner),
        DatasetPublication(db, datasets, executions, approvals, config),
        environment_snapshot(),
        {
            "cleaning_preview": PreviewFinalizer(objects, cleaner),
            "cleaning_apply": ApplyFinalizer(objects, cleaner, approvals),
        },
    )


def make_planning(db: Session, objects: LocalObjects) -> PlanningService:
    require_ready(db)
    datasets, executions = make_datasets(db), make_executions(db)
    return PlanningService(
        executions,
        PlanningTableAccess(
            datasets, executions, ProjectPermissions(db), make_semantics(db, objects)
        ),
        SQLPlanningRepository(db),
        OperationCatalog(),
        SQLUnitOfWork(db),
        processing_config(),
    )


def make_cleaning(db: Session, objects: LocalObjects) -> CleaningService:
    require_ready(db)
    datasets = make_datasets(db)
    return CleaningService(
        make_executions(db),
        CleaningPlanAccess(make_planning(db, objects), ProjectPermissions(db), datasets),
        SQLApprovalRepository(db),
        OperationCatalog(),
        datasets,
        objects,
        SQLUnitOfWork(db),
    )
