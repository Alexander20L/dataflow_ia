import secrets
from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from dataflow.bootstrap.comprehension_job import ComprehensionAccess
from dataflow.bootstrap.dashboard_job import DashboardAccess
from dataflow.bootstrap.delivery_job import DeliveryAccess
from dataflow.bootstrap.exploration_job import ExplorationAccess
from dataflow.bootstrap.inspection_job import InspectionAccess
from dataflow.bootstrap.investigation_job import InvestigationAccess
from dataflow.bootstrap.overview_audit import OverviewAuditAccess
from dataflow.bootstrap.services import (
    make_analysis,
    make_cleaning,
    make_datasets,
    make_executions,
    make_ingestion,
    make_metrics,
)
from dataflow.modules.analytics.application import MetricService
from dataflow.modules.cleaning.application import CleaningService
from dataflow.modules.comprehension.infrastructure import SQLFeedbackRepository
from dataflow.modules.curation.public import SQLFindingFeedback
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.datasets.public import Datasets
from dataflow.modules.executions.public import Executions
from dataflow.modules.identity.application import IdentityService
from dataflow.modules.identity.contracts import SessionIdentity
from dataflow.modules.identity.infrastructure import ArgonPasswords, SQLIdentityRepository
from dataflow.modules.ingestion.application import AnalysisService, IngestionService
from dataflow.modules.inspection.infrastructure import SQLColumnAnnotations
from dataflow.modules.projects.application import ProjectService
from dataflow.modules.projects.infrastructure import SQLProjectRepository
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


def overview_audit_service(db: Db, objects: Objects) -> OverviewAuditAccess:
    return OverviewAuditAccess(make_datasets(db), make_executions(db), objects)


OverviewAudits = Annotated[OverviewAuditAccess, Depends(overview_audit_service)]


def investigation_service(db: Db, objects: Objects) -> InvestigationAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return InvestigationAccess(make_datasets(db), make_executions(db), objects)


Investigations = Annotated[InvestigationAccess, Depends(investigation_service)]


def comprehension_service(db: Db, objects: Objects) -> ComprehensionAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return ComprehensionAccess(
        db, make_datasets(db), make_executions(db), objects, SQLFeedbackRepository(db)
    )


Comprehensions = Annotated[ComprehensionAccess, Depends(comprehension_service)]


def exploration_service(db: Db, objects: Objects) -> ExplorationAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return ExplorationAccess(make_datasets(db), make_executions(db), objects, db)


Explorations = Annotated[ExplorationAccess, Depends(exploration_service)]


def inspection_service(db: Db, objects: Objects) -> InspectionAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return InspectionAccess(
        db, make_datasets(db), make_executions(db), objects, SQLColumnAnnotations(db)
    )


Inspections = Annotated[InspectionAccess, Depends(inspection_service)]


def dashboard_service(db: Db, objects: Objects) -> DashboardAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return DashboardAccess(
        db, make_datasets(db), make_executions(db), objects, SQLFindingFeedback(db)
    )


Dashboards = Annotated[DashboardAccess, Depends(dashboard_service)]


def delivery_service(db: Db, objects: Objects) -> DeliveryAccess:
    from dataflow.platform.runtime import require_ready

    require_ready(db)
    return DeliveryAccess(make_datasets(db), make_executions(db), objects)


Delivery = Annotated[DeliveryAccess, Depends(delivery_service)]


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


def metric_service(db: Db, objects: Objects) -> MetricService:
    return make_metrics(db, objects)


Metrics = Annotated[MetricService, Depends(metric_service)]


def cleaning_service(db: Db, objects: Objects) -> CleaningService:
    return make_cleaning(db, objects)


Cleaning = Annotated[CleaningService, Depends(cleaning_service)]
