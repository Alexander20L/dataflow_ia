import secrets
from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from dataflow.bootstrap.ai import configured
from dataflow.bootstrap.services import (
    make_analysis,
    make_analysis_sessions,
    make_automation,
    make_cleaning,
    make_cleaning_proposals,
    make_copilot,
    make_dashboards,
    make_datasets,
    make_executions,
    make_ingestion,
    make_metrics,
    make_pipeline,
    make_planning,
    make_reports,
    make_rulesets,
    make_semantics,
)
from dataflow.integrations.ai import AIProvider
from dataflow.modules.analysis_sessions.application import AnalysisSessionService
from dataflow.modules.analytics.application import MetricService
from dataflow.modules.automation.application import AutomationService
from dataflow.modules.automation.pipeline import PipelineService
from dataflow.modules.cleaning.application import CleaningProposals, CleaningService
from dataflow.modules.copilot.application import CopilotConfig, CopilotService
from dataflow.modules.dashboards.application import DashboardService
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.identity.application import IdentityService
from dataflow.modules.identity.contracts import SessionIdentity
from dataflow.modules.identity.infrastructure import ArgonPasswords, SQLIdentityRepository
from dataflow.modules.ingestion.application import AnalysisService, IngestionService
from dataflow.modules.planning.application import PlanningService
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
from dataflow.modules.quality.application import RulesetService
from dataflow.modules.reports.application import ReportService
from dataflow.modules.understanding.public import SemanticService
from dataflow.platform.config import get_settings
from dataflow.platform.database import get_db
from dataflow.platform.errors import ApplicationError

Db = Annotated[Session, Depends(get_db)]
cookie_scheme = APIKeyCookie(name=get_settings().cookie_name, auto_error=False)
passwords = ArgonPasswords()


def identity_service(db: Db) -> IdentityService:
    return IdentityService(SQLIdentityRepository(db), passwords, get_settings().session_hours)


Identity = Annotated[IdentityService, Depends(identity_service)]


def current_identity(
    request: Request,
    service: Identity,
    token: Annotated[str | None, Security(cookie_scheme)],
    csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SessionIdentity:
    identity = service.current(token)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(identity.csrf_token, csrf or ""):
            raise ApplicationError(
                "CSRF_INVALID", "La sesión debe actualizarse. Recarga la página.", 403
            )
    return identity


CurrentIdentity = Annotated[SessionIdentity, Depends(current_identity)]


def project_service(request: Request, db: Db) -> ProjectService:
    return ProjectService(SQLProjectRepository(db, request.state.correlation_id))


Projects = Annotated[ProjectService, Depends(project_service)]


def object_store() -> LocalObjects:
    return LocalObjects(get_settings().storage_path)


Objects = Annotated[LocalObjects, Depends(object_store)]


def ingestion_service(db: Db, objects: Objects) -> IngestionService:
    return make_ingestion(db, objects)


Ingestion = Annotated[IngestionService, Depends(ingestion_service)]


def analysis_service(db: Db, objects: Objects) -> AnalysisService:
    return make_analysis(db, objects)


Analysis = Annotated[AnalysisService, Depends(analysis_service)]


def execution_service(db: Db) -> Executions:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return make_executions(db)


ExecutionAccess = Annotated[Executions, Depends(execution_service)]


def dataset_service(db: Db) -> Datasets:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return make_datasets(db)


DatasetAccess = Annotated[Datasets, Depends(dataset_service)]


def semantic_service(db: Db, objects: Objects) -> SemanticService:
    return make_semantics(db, objects)


Semantics = Annotated[SemanticService, Depends(semantic_service)]


def ruleset_service(db: Db, objects: Objects) -> RulesetService:
    return make_rulesets(db, objects)


Rulesets = Annotated[RulesetService, Depends(ruleset_service)]


def metric_service(db: Db, objects: Objects) -> MetricService:
    return make_metrics(db, objects)


Metrics = Annotated[MetricService, Depends(metric_service)]


def dashboard_service(db: Db, objects: Objects) -> DashboardService:
    return make_dashboards(db, objects)


Dashboards = Annotated[DashboardService, Depends(dashboard_service)]


def report_service(db: Db, objects: Objects) -> ReportService:
    return make_reports(db, objects)


Reports = Annotated[ReportService, Depends(report_service)]


def ai_setup() -> tuple[AIProvider | None, CopilotConfig]:
    """Proveedor y límites del copiloto; las pruebas lo sustituyen por uno guionizado."""
    return configured()


AISetup = Annotated[tuple[AIProvider | None, CopilotConfig], Depends(ai_setup)]


def copilot_service(db: Db, objects: Objects, setup: AISetup) -> CopilotService:
    return make_copilot(db, objects, *setup)


Copilot = Annotated[CopilotService, Depends(copilot_service)]


def planning_service(db: Db, objects: Objects) -> PlanningService:
    return make_planning(db, objects)


Planning = Annotated[PlanningService, Depends(planning_service)]


def cleaning_service(db: Db, objects: Objects) -> CleaningService:
    return make_cleaning(db, objects)


Cleaning = Annotated[CleaningService, Depends(cleaning_service)]


def cleaning_proposal_service(db: Db, objects: Objects) -> CleaningProposals:
    return make_cleaning_proposals(db, objects)


CleaningProposalsDep = Annotated[CleaningProposals, Depends(cleaning_proposal_service)]


def analysis_session_service(db: Db) -> AnalysisSessionService:
    return make_analysis_sessions(db)


AnalysisSessions = Annotated[AnalysisSessionService, Depends(analysis_session_service)]


def automation_service(db: Db, objects: Objects) -> AutomationService:
    return make_automation(db, objects)


Automation = Annotated[AutomationService, Depends(automation_service)]


def pipeline_service(db: Db, objects: Objects) -> PipelineService:
    return make_pipeline(db, objects)


Pipelines = Annotated[PipelineService, Depends(pipeline_service)]
