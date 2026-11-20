"""Cliente de la API hacia el servicio `connector` (Fase 32B, ADR-050).

Implementa `SnapshotConnector`: envía la conexión (con la contraseña y el certificado, sólo
para esta copia), la política de destinos y los límites, y devuelve la copia o el mismo error
que habría dado el subproceso local. Sin proxies ni redirecciones: el conector vive en una red
interna.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from dataflow.modules.executions.public import ProcessingConfig
from dataflow.modules.ingestion.contracts import PostgresConnection, SqlSnapshot
from dataflow.platform.destinations import DestinationPolicy
from dataflow.platform.errors import ApplicationError

# Margen sobre el plazo de la copia: el conector arranca el subproceso y serializa el resultado.
MARGIN_SECONDS = 15


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def default_opener() -> Callable[..., Any]:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open


def unavailable() -> ApplicationError:
    return ApplicationError(
        "DATABASE_CONNECTOR_UNAVAILABLE",
        "El servicio de conexión a bases de datos no responde. Inténtalo más tarde.",
        503,
    )


class HttpConnector:
    def __init__(
        self,
        url: str,
        token: str,
        max_bytes: int,
        max_cell_bytes: int,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("DATAFLOW_CONNECTOR_URL debe ser http:// o https://")
        self.endpoint = url.rstrip("/") + "/v1/snapshot/postgresql"
        self.token = token
        self.max_bytes, self.max_cell_bytes = max_bytes, max_cell_bytes
        self.opener = opener or default_opener()

    def snapshot_postgresql(
        self,
        connection: PostgresConnection,
        config: ProcessingConfig,
        policy: DestinationPolicy,
        timeout: int | None = None,
    ) -> SqlSnapshot:
        seconds = timeout or config.timeout_seconds
        certificate = connection.ca_certificate
        body = {
            "connection": {
                **connection.model_dump(exclude={"password", "ca_certificate"}),
                "password": connection.password.get_secret_value(),
                "ca_certificate": certificate.get_secret_value() if certificate else None,
            },
            "policy": {
                "allowed_hosts": list(policy.allowed_hosts),
                "public": policy.public,
                "denied": list(policy.denied),
            },
            "max_rows": config.max_rows,
            "max_columns": config.max_columns,
            "timeout_seconds": seconds,
            "max_bytes": self.max_bytes,
            "max_cell_bytes": self.max_cell_bytes,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        # El CSV de una copia en JSON ocupa como mucho unas tres veces su tamaño (escapes).
        limit = self.max_bytes * 3 + 1024 * 1024
        try:
            with self.opener(request, timeout=seconds + MARGIN_SECONDS) as response:
                content = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            raise self.refused(exc) from exc
        except (OSError, ValueError) as exc:
            raise unavailable() from exc
        if len(content) > limit:
            raise unavailable()
        try:
            return SqlSnapshot.model_validate_json(content)
        except ValueError as exc:
            raise unavailable() from exc

    def refused(self, exc: urllib.error.HTTPError) -> ApplicationError:
        """El error de la copia tal como lo dio el subproceso; uno del propio conector
        (token, petición) es una avería, no algo que la persona pueda corregir."""
        try:
            payload = json.loads(exc.read(64 * 1024) or b"{}")
        except (OSError, ValueError):
            return unavailable()
        code = payload.get("code") if isinstance(payload, dict) else None
        if not isinstance(code, str) or code.startswith("CONNECTOR_"):
            return unavailable()
        details = payload.get("details")
        return ApplicationError(
            code,
            str(payload.get("message", "")),
            exc.code,
            details if isinstance(details, dict) else None,
        )
