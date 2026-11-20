"""Servicio `connector` (Fase 32B, ADR-050): copia esquemas de bases PostgreSQL públicas fuera de
la API.

Corre en su propio contenedor, en una red de salida aislada (sin acceso a la base de DataFlow ni
a la red interna) y sin credenciales de DataFlow ni clave de IA. Sólo responde a la API, que se
identifica con un token compartido. Cada copia se hace en el mismo subproceso aislado que la
API usaba (`dataflow.modules.ingestion.processor`), que repite `database-destination-v1` justo
antes de conectar. No guarda nada: la contraseña y el certificado viven sólo durante la copia.

    python -m dataflow.bootstrap.connector
"""

import secrets
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from dataflow.modules.ingestion.analytical import IsolatedAnalyzer
from dataflow.modules.ingestion.contracts import ConnectorSnapshotRequest
from dataflow.platform.config import Settings, get_settings
from dataflow.platform.destinations import DestinationPolicy
from dataflow.platform.errors import ApplicationError

# La petición sólo lleva datos de conexión, la política y el certificado (hasta 16 KB).
MAX_REQUEST = 128 * 1024


def refusal(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


async def limited_body(request: Request) -> bytes | None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST:
            return None
    return bytes(body)


def create_app(settings: Settings | None = None, scratch: Path | None = None) -> FastAPI:
    settings = settings or get_settings()
    token = settings.connector_secret()
    if token is None:
        raise RuntimeError(
            "El conector necesita el token compartido con la API (DATAFLOW_CONNECTOR_TOKEN o "
            "DATAFLOW_CONNECTOR_TOKEN_FILE, de al menos 32 caracteres)."
        )
    expected = f"Bearer {token}".encode()
    root = scratch or Path(tempfile.gettempdir()) / "dataflow-connector"
    app = FastAPI(title="DataFlow AI connector", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/snapshot/postgresql")
    async def snapshot_postgresql(request: Request) -> Response:
        offered = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(offered, expected):
            return refusal("CONNECTOR_UNAUTHORIZED", "Petición no autorizada.", 401)
        body = await limited_body(request)
        if body is None:
            return refusal("CONNECTOR_TOO_LARGE", "La petición es demasiado grande.", 413)
        try:
            payload = ConnectorSnapshotRequest.model_validate_json(body)
        except ValidationError:
            return refusal("CONNECTOR_INVALID", "Petición no válida.", 422)
        # El plan admite como mucho 100 s; la copia (Fase 33) usa su propio plazo, aparte.
        analyzer = IsolatedAnalyzer(
            root,
            min(payload.timeout_seconds, 60),
            payload.max_rows,
            payload.max_columns,
            payload.max_bytes,
            payload.max_cell_bytes,
        )
        policy = DestinationPolicy(
            tuple(payload.policy.allowed_hosts),
            payload.policy.public,
            tuple(payload.policy.denied),
        )
        try:
            result = await run_in_threadpool(
                analyzer.snapshot_postgresql,
                payload.connection,
                analyzer.config(None),
                policy,
                payload.timeout_seconds,
            )
        except ApplicationError as exc:
            return JSONResponse(
                {"code": exc.code, "message": exc.message, "details": exc.details},
                status_code=exc.status,
            )
        return Response(result.model_dump_json(), media_type="application/json")

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104 - sólo en su red interna de Compose
        port=settings.connector_port,
        proxy_headers=False,
        limit_concurrency=8,
        access_log=False,
    )


if __name__ == "__main__":
    main()
