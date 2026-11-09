import json
import logging
import time
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from dataflow.bootstrap.schemas import ErrorResponse
from dataflow.modules.analytics.presentation import router as analytics_router
from dataflow.modules.cleaning.presentation import router as cleaning_router
from dataflow.modules.copilot.presentation import router as copilot_router
from dataflow.modules.executions.presentation import router as executions_router
from dataflow.modules.identity.presentation import router as identity_router
from dataflow.modules.ingestion.presentation import analysis_router
from dataflow.modules.ingestion.presentation import router as ingestion_router
from dataflow.modules.projects.presentation import router as projects_router
from dataflow.platform.config import get_settings
from dataflow.platform.database import engine, session_factory
from dataflow.platform.errors import ApplicationError
from dataflow.platform.runtime import require_ready

logger = logging.getLogger("dataflow.http")
logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(
    title="DataFlow AI API",
    version="0.22.0",
    description="DataFlow AI: análisis automático de archivos propios (sin intervención manual).",
    responses={
        status: {"model": ErrorResponse}
        for status in [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503]
    },
)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "correlation_id": request.state.correlation_id,
        },
    )


@app.middleware("http")
async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
    try:
        correlation = str(UUID(request.headers.get("x-correlation-id", "")))
    except ValueError:
        correlation = str(uuid4())
    request.state.correlation_id = correlation
    started = time.perf_counter()
    origin = request.headers.get("origin")
    settings = get_settings()
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        (origin and origin not in settings.allowed_origins)
        or (settings.cookie_name in request.cookies and not origin)
    ):
        response: Response = error_response(
            request, 403, "ORIGIN_FORBIDDEN", "Origen no permitido."
        )
    else:
        response = await call_next(request)
    response.headers["x-correlation-id"] = correlation
    response.headers["cache-control"] = "no-store"
    response.headers["x-content-type-options"] = "nosniff"
    logger.info(
        json.dumps(
            {
                "event": "http.request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "correlation_id": correlation,
            }
        )
    )
    return response


@app.exception_handler(ApplicationError)
async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # No devolver inputs: podrían contener contraseñas.
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Revisa los campos enviados.",
            "correlation_id": request.state.correlation_id,
            "details": [
                {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        json.dumps(
            {
                "event": "http.error",
                "type": type(exc).__name__,
                "correlation_id": request.state.correlation_id,
            }
        )
    )
    return error_response(request, 500, "INTERNAL_ERROR", "No se pudo completar la operación.")


@app.get("/health/live", operation_id="liveness")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", operation_id="readiness")
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise ApplicationError("DATABASE_UNAVAILABLE", "Base de datos no disponible.", 503) from exc
    with session_factory() as db:
        require_ready(db)
    return {"status": "ready"}


app.include_router(identity_router)
app.include_router(projects_router)
app.include_router(ingestion_router)
app.include_router(executions_router)
app.include_router(analysis_router)
app.include_router(cleaning_router)
app.include_router(analytics_router)
app.include_router(copilot_router)
