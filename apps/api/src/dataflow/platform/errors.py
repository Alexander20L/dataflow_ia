from typing import Any


class ApplicationError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 400, details: dict[str, Any] | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        # Detalle estructurado opcional (p. ej. valores que no convierten); sin datos sensibles
        # en logs: sólo se persiste y se muestra a quien puede leer la ejecución.
        self.details = details
        super().__init__(message)
