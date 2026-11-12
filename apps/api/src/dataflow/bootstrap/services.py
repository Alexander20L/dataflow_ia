from uuid import uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.ai import configured
from dataflow.bootstrap.analytics_access import AnalyticsMetricSource, AnalyticsTableAccess
from dataflow.bootstrap.cleaning_access import CleaningPlanAccess, CleaningProposalAccess
from dataflow.bootstrap.comprehension_job import (
    ComprehensionInput,
    ComprehensionStep,
    enqueue_comprehension,
    record_comprehension_calls,
)
from dataflow.bootstrap.dashboard_job import (
    DashboardInput,
    DashboardStep,
    enqueue_dashboard,
    record_dashboard_calls,
    request_report_update,
)
from dataflow.bootstrap.delivery_job import ReportInput, ReportStep, enqueue_report
from dataflow.bootstrap.exploration_job import (
    ExplorationInput,
    ExplorationStep,
    enqueue_exploration,
    record_exploration_calls,
)
from dataflow.bootstrap.inspection_job import (
    InspectionInput,
    InspectionStep,
    enqueue_inspection,
)
from dataflow.bootstrap.investigation_job import (
    InvestigationInput,
    InvestigationStep,
    enqueue_investigation,
    record_investigation_calls,
)
from dataflow.bootstrap.operations import OperationCatalog, OperationRegistry, WorkerRegistry
from dataflow.bootstrap.overview_audit import (
    OverviewAuditStep,
    OverviewInput,
    enqueue_audit,
    record_audit_call,
)
from dataflow.bootstrap.planning_access import PlanningTableAccess
from dataflow.bootstrap.provenance import environment_snapshot
from dataflow.bootstrap.quality_access import QualityTableAccess
from dataflow.bootstrap.semantic_access import SemanticRepresentationAccess
from dataflow.integrations.ai import AIProvider
from dataflow.modules.analytics.application import MetricService
from dataflow.modules.analytics.infrastructure import SQLMetricRepository
from dataflow.modules.analytics.steps import (
    AnalyticsQueryStep,
    AutomaticAnalysisStep,
    FollowUpComputer,
    MetricSource,
)
from dataflow.modules.audit.public import record_event
from dataflow.modules.cleaning.application import CleaningProposals, CleaningService
from dataflow.modules.cleaning.engine import IsolatedCleaner
from dataflow.modules.cleaning.public import (
    ApprovalSource,
    derived_version_id,
    require_valid_approval,
)
from dataflow.modules.cleaning.repository import SQLApprovalRepository, SQLApprovalSource
from dataflow.modules.cleaning.steps import (
    ApplyFinalizer,
    CastStep,
    DeduplicateStep,
    FilterRowsStep,
    NormalizeNullTokensStep,
    PreviewFinalizer,
    TrimWhitespaceStep,
)
from dataflow.modules.comprehension.infrastructure import SQLFeedbackRepository
from dataflow.modules.copilot.application import CopilotConfig, CopilotService
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.curation.public import SQLFindingFeedback
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
from dataflow.modules.ingestion.contracts import SourceReview
from dataflow.modules.ingestion.executor import (
    ProfileStep,
    QualityRulesStep,
    QualityStep,
    ReadCsvStep,
    ReadCsvV2Step,
    ReadPdfStep,
    ReadXlsxStep,
    RulesetSource,
    SourceInputResolver,
    TableInputResolver,
)
from dataflow.modules.ingestion.plans import analysis_fingerprint, build_plan
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.planning.infrastructure import SQLPlanningRepository
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.quality.application import RulesetService
from dataflow.modules.quality.infrastructure import SQLRulesetRepository
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
        IsolatedAnalyzer(
            objects.root,
            settings.processing_timeout_seconds,
            settings.max_csv_rows,
            settings.max_csv_columns,
        ),
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


def make_metrics(db: Session, objects: LocalObjects) -> MetricService:
    require_ready(db)
    access = AnalyticsTableAccess(
        make_datasets(db), make_executions(db), ProjectPermissions(db), objects
    )
    return MetricService(SQLMetricRepository(db), access, SQLUnitOfWork(db))


def make_rulesets(db: Session, objects: LocalObjects) -> RulesetService:
    require_ready(db)
    access = QualityTableAccess(
        make_datasets(db), make_executions(db), ProjectPermissions(db), objects
    )
    return RulesetService(SQLRulesetRepository(db), access, SQLUnitOfWork(db))


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
        objects: LocalObjects,
    ) -> None:
        self.db, self.datasets, self.executions = db, datasets, executions
        self.approvals, self.config = approvals, config
        self.objects = objects

    def prepare(self, lease: Lease, outputs: list[ArtifactOutput]) -> None:
        if lease.execution.kind == "dashboard":
            record_dashboard_calls(
                self.db, lease, next(o for o in outputs if o.kind == "dashboard"), self.objects
            )
            return
        if lease.execution.kind == "exploration":
            record_exploration_calls(
                self.db, lease, next(o for o in outputs if o.kind == "exploration"), self.objects
            )
            return
        if lease.execution.kind == "comprehension":
            record_comprehension_calls(
                self.db, lease, next(o for o in outputs if o.kind == "comprehension"), self.objects
            )
            return
        if lease.execution.kind == "investigation":
            record_investigation_calls(
                self.db, lease, next(o for o in outputs if o.kind == "investigation"), self.objects
            )
            return
        if lease.execution.kind == "overview_audit":
            record_audit_call(
                self.db, lease, next(o for o in outputs if o.kind == "overview_audit"), self.objects
            )
            return
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
            analysis = next((a for a in artifacts if a.kind == "automatic_analysis"), None)
            table = next((a for a in artifacts if a.kind == "table"), None)
            if analysis is not None and table is not None:
                # Fase 22: la inspección de la pestaña Dataset, la primera de los trabajos de
                # fondo (sólo en el recorrido automático actual, como la comprensión).
                enqueue_inspection(self.executions, self.datasets, lease, artifacts, self.config)
                # Fase 19: primero la comprensión del negocio (se reclama antes por llegar
                # antes); después la investigación (Fase 16), que explica los hallazgos.
                profile = next((a for a in artifacts if a.kind == "profile"), None)
                if profile is not None:
                    enqueue_comprehension(
                        self.executions,
                        self.datasets,
                        SQLFeedbackRepository(self.db),
                        lease,
                        profile,
                        table,
                        self.config,
                    )
                enqueue_investigation(self.executions, lease, analysis, table, self.config)
                return
            profile = next((a for a in artifacts if a.kind == "profile"), None)
            if (
                profile is not None
                and lease.execution.plan
                and any(
                    s.get("operation") == "understanding.profile" and s.get("version") in {2, 3, 4}
                    for s in lease.execution.plan.content["steps"]
                )
            ):
                enqueue_audit(self.executions, lease, profile, self.config)
        elif kind == "comprehension":
            # Fase 20: la exploración guiada parte de la comprensión publicada.
            enqueue_exploration(
                self.executions,
                lease,
                next(a for a in artifacts if a.kind == "comprehension"),
                self.config,
            )
        elif kind == "exploration":
            # Fase 21: el dashboard adaptado parte de la exploración publicada.
            enqueue_dashboard(
                self.executions,
                lease,
                next(a for a in artifacts if a.kind == "exploration"),
                self.config,
            )
        elif kind == "dashboard":
            # Fase 21: si el informe ya se generó sin este dashboard, se genera otra versión.
            dashboard = next(a for a in artifacts if a.kind == "dashboard")
            request_report_update(
                self.executions,
                lease.owner_id,
                lease.version_id,
                f"dashboard:{dashboard.content.sha256}",
            )
        elif kind == "investigation":
            # Fase 17: el informe automático se genera al publicarse la investigación.
            enqueue_report(
                self.executions,
                self.datasets,
                lease,
                next(a for a in artifacts if a.kind == "investigation"),
                self.config,
                self.review(lease),
            )
        elif kind == "table_analysis":
            self.datasets.materialize_derived(
                lease.version_id,
                lease.execution_id,
                {artifact.kind: artifact.id for artifact in artifacts},
            )
        elif kind == "cleaning_apply":
            self.derived(lease, next(a for a in artifacts if a.kind == "table"))

    def review(self, lease: Lease) -> SourceReview | None:
        """Fase 18: lectura y cambios de estructura de la versión, para el informe. Si no se
        puede obtener, el informe sale sin esas secciones."""
        try:
            return make_ingestion(self.db, self.objects).review(lease.owner_id, lease.version_id)
        except ApplicationError:
            return None

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
    "inspection",
    "comprehension",
    "exploration",
    "dashboard",
    "overview_audit",
    "investigation",
    "automatic_report",
    "csv_import",
    "table_analysis",
    "plan",
    "cleaning_preview",
    "cleaning_apply",
}


def make_operations(
    objects: LocalObjects,
    analyzer: Analyzer,
    cleaner: IsolatedCleaner,
    rulesets: RulesetSource | None = None,
    metrics: MetricSource | None = None,
) -> OperationRegistry:
    return OperationRegistry(
        {
            "ingestion.read_csv@1": ReadCsvStep(objects, analyzer),
            "ingestion.read_csv@2": ReadCsvV2Step(objects, analyzer),
            "ingestion.read_xlsx@1": ReadXlsxStep(objects, analyzer),
            "ingestion.read_xlsx@2": ReadXlsxStep(objects, analyzer),
            "ingestion.read_pdf@1": ReadPdfStep(objects, analyzer),
            "understanding.profile@1": ProfileStep(objects, analyzer),
            "understanding.profile@2": ProfileStep(objects, analyzer),
            "understanding.profile@3": ProfileStep(objects, analyzer),
            "understanding.profile@4": ProfileStep(objects, analyzer),
            "quality.evaluate@1": QualityStep(objects, analyzer),
            "quality.evaluate@3": QualityStep(objects, analyzer),
            "quality.evaluate@2": QualityRulesStep(objects, analyzer, rulesets),
            "analytics.automatic@1": AutomaticAnalysisStep(objects, objects.root),
            "analytics.query@1": AnalyticsQueryStep(objects, objects.root, metrics),
            "analytics.query@2": AnalyticsQueryStep(objects, objects.root, metrics),
            "analytics.query@3": AnalyticsQueryStep(objects, objects.root, metrics),
            "cleaning.trim_whitespace@1": TrimWhitespaceStep(objects, cleaner),
            "cleaning.filter_rows@1": FilterRowsStep(objects, cleaner),
            "cleaning.normalize_null_tokens@1": NormalizeNullTokensStep(objects, cleaner),
            "cleaning.cast@1": CastStep(objects, cleaner),
            "cleaning.deduplicate@1": DeduplicateStep(objects, cleaner),
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
    settings = get_settings()
    provider, ai_config = configured(
        settings.model_copy(
            update={
                "ai_timeout_seconds": min(
                    settings.ai_timeout_seconds, max(1, config.timeout_seconds - 5)
                )
            }
        ),
        max_retries=0,
    )
    return ExecutionRunner(
        SQLExecutionRepository(db, datasets),
        SQLUnitOfWork(db),
        set(WORKER_KINDS if kinds is None else kinds),
        {
            "source": SourceInputResolver(datasets, projects),
            "table": TableInputResolver(
                datasets, executions, projects, make_semantics(db, objects)
            ),
            "overview": OverviewInput(datasets, executions, projects),
            "automatic": InvestigationInput(datasets, executions, projects),
            "comprehension": ComprehensionInput(datasets, executions, projects),
            "exploration": ExplorationInput(datasets, executions, projects),
            "dashboard": DashboardInput(datasets, executions, projects),
            "inspection": InspectionInput(datasets, executions, projects),
            "investigation": ReportInput(datasets, executions, projects),
        },
        WorkerRegistry(
            make_operations(
                objects,
                engine,
                cleaner,
                make_rulesets(db, objects),
                AnalyticsMetricSource(make_metrics(db, objects), make_semantics(db, objects)),
            ),
            {
                "copilot.audit_overview@1": OverviewAuditStep(
                    objects, make_copilot(db, provider, ai_config)
                ),
                "investigation.investigate@1": InvestigationStep(
                    objects,
                    FollowUpComputer(objects, objects.root),
                    make_copilot(db, provider, ai_config),
                ),
                "delivery.report@1": ReportStep(objects, executions, SQLFindingFeedback(db)),
                "delivery.dashboard@1": DashboardStep(
                    objects, make_copilot(db, provider, ai_config)
                ),
                "exploration.explore@1": ExplorationStep(
                    objects, make_copilot(db, provider, ai_config)
                ),
                "inspection.inspect@1": InspectionStep(
                    objects, engine if isinstance(engine, IsolatedAnalyzer) else None
                ),
                "comprehension.understand@1": ComprehensionStep(
                    objects, make_copilot(db, provider, ai_config)
                ),
            },
        ),
        DatasetPublication(db, datasets, executions, approvals, config, objects),
        environment_snapshot(),
        {
            "cleaning_preview": PreviewFinalizer(objects, cleaner),
            "cleaning_apply": ApplyFinalizer(objects, cleaner, approvals),
        },
    )


def make_copilot(db: Session, provider: AIProvider | None, config: CopilotConfig) -> CopilotService:
    require_ready(db)
    return CopilotService(SQLCopilotRepository(db), provider, config)


def make_planning(db: Session, objects: LocalObjects) -> PlanningService:
    require_ready(db)
    datasets, executions = make_datasets(db), make_executions(db)
    return PlanningService(
        executions,
        PlanningTableAccess(
            datasets,
            executions,
            ProjectPermissions(db),
            make_semantics(db, objects),
            make_rulesets(db, objects),
            make_metrics(db, objects),
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


def make_cleaning_proposals(db: Session, objects: LocalObjects) -> CleaningProposals:
    return CleaningProposals(
        CleaningProposalAccess(make_semantics(db, objects), make_ingestion(db, objects))
    )
