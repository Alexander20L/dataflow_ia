from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATAFLOW_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dataflow:dataflow_local@127.0.0.1:55432/dataflow"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3100",
    ]
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    cookie_name: str = "dataflow_session"
    registration_enabled: bool = True
    storage_path: Path = Path(".data/objects")
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024)
    max_owner_storage_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    max_csv_rows: int = Field(default=100_000, ge=1, le=100_000)
    max_csv_columns: int = Field(default=128, ge=1, le=128)
    processing_timeout_seconds: int = Field(default=45, ge=5, le=60)
    # Fase 11C: pipelines automáticos simultáneos por propietario; los demás quedan para revisión.
    automation_max_running_per_owner: int = Field(default=5, ge=1, le=100)

    # Fase 12B: SQL Server. La clave cifra las contraseñas de las conexiones guardadas (Fernet,
    # 32 bytes en base64 url-safe); sin clave no se pueden guardar conexiones. Igual que la de IA:
    # DATAFLOW_SOURCES_KEY o DATAFLOW_SOURCES_KEY_FILE (secreto de Docker).
    sources_key: SecretStr | None = None
    sources_key_file: Path | None = None
    sql_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=200 * 1024 * 1024)
    sql_driver: str = Field(default="ODBC Driver 18 for SQL Server", min_length=1, max_length=80)

    # Copiloto IA (Fase 10, ADR-022). Desactivado por defecto: sin IA todo lo demás funciona.
    # La clave nunca se registra ni llega al frontend: DATAFLOW_AI_API_KEY (local, en un .env
    # ignorado por git) o DATAFLOW_AI_API_KEY_FILE (secreto de Docker en /run/secrets).
    ai_provider: Literal["disabled", "fake", "anthropic"] = "disabled"
    ai_model: str = Field(default="claude-opus-5-5", min_length=1, max_length=80)
    ai_effort: Literal["low", "medium", "high"] = "low"
    ai_api_key: SecretStr | None = None
    ai_api_key_file: Path | None = None
    ai_timeout_seconds: int = Field(default=30, ge=5, le=120)
    ai_max_output_tokens: int = Field(default=4000, ge=500, le=16000)
    ai_user_daily_tokens: int = Field(default=200_000, ge=1)
    ai_project_monthly_cost_usd: Decimal = Field(default=Decimal("5"), ge=0)

    def ai_key(self) -> str | None:
        """Clave del proveedor: el archivo (secreto de Docker) tiene prioridad sobre la
        variable. Vacía o ilegible: sin clave."""
        if self.ai_api_key_file is not None:
            try:
                value = self.ai_api_key_file.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return value or None
        if self.ai_api_key is not None:
            return self.ai_api_key.get_secret_value().strip() or None
        return None

    def sources_cipher_key(self) -> str | None:
        if self.sources_key_file is not None:
            try:
                value = self.sources_key_file.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return value or None
        if self.sources_key is not None:
            return self.sources_key.get_secret_value().strip() or None
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
