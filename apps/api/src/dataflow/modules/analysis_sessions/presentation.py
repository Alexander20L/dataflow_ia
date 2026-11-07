from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from dataflow.bootstrap.dependencies import AnalysisSessions, CurrentIdentity
from dataflow.modules.analysis_sessions.contracts import (
    AnalysisSessionView,
    SelectInputRequest,
    SessionInputPage,
)

router = APIRouter(prefix="/api/v1", tags=["Analysis sessions"])


@router.post(
    "/projects/{project_id}/analysis-sessions",
    response_model=AnalysisSessionView,
    status_code=201,
    operation_id="openAnalysisSession",
)
def open_session(
    project_id: UUID, response: Response, identity: CurrentIdentity, service: AnalysisSessions
) -> AnalysisSessionView:
    """Crea la sesión del proyecto o devuelve la existente (200): una por proyecto."""
    view, created = service.open(identity.user.id, project_id)
    if not created:
        response.status_code = 200
    return view


@router.get(
    "/projects/{project_id}/analysis-session",
    response_model=AnalysisSessionView,
    operation_id="getProjectAnalysisSession",
)
def project_session(
    project_id: UUID, identity: CurrentIdentity, service: AnalysisSessions
) -> AnalysisSessionView:
    return service.for_project(identity.user.id, project_id)


@router.get(
    "/analysis-sessions/{session_id}",
    response_model=AnalysisSessionView,
    operation_id="getAnalysisSession",
)
def get_session(
    session_id: UUID, identity: CurrentIdentity, service: AnalysisSessions
) -> AnalysisSessionView:
    return service.get(identity.user.id, session_id)


@router.post(
    "/analysis-sessions/{session_id}/inputs",
    response_model=AnalysisSessionView,
    operation_id="selectAnalysisSessionInput",
)
def select_input(
    session_id: UUID,
    body: SelectInputRequest,
    request: Request,
    identity: CurrentIdentity,
    service: AnalysisSessions,
) -> AnalysisSessionView:
    """Sustituye la fuente activa por una versión lista; si no lo está, la activa no cambia."""
    return service.select(
        identity.user.id,
        session_id,
        body.version_id,
        body.expected_revision,
        request.state.correlation_id,
    )


@router.get(
    "/analysis-sessions/{session_id}/inputs",
    response_model=SessionInputPage,
    operation_id="listAnalysisSessionInputs",
)
def history(
    session_id: UUID,
    identity: CurrentIdentity,
    service: AnalysisSessions,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionInputPage:
    return service.history(identity.user.id, session_id, limit, offset)
