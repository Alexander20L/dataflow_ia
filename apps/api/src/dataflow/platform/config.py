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

    # Explicación IA (Fase 10, ADR-022; Fase 13B). `auto` (por defecto): Anthropic si hay clave
    # configurada; si no, desactivada (sin IA todo lo demás funciona). La clave nunca se registra
    # ni llega al frontend: DATAFLOW_AI_API_KEY (local, en un .env ignorado por git) o
    # DATAFLOW_AI_API_KEY_FILE (secreto de Docker en /run/secrets).
    ai_provider: Literal["auto", "disabled", "fake", "anthropic"] = "auto"
    ai_model: str = Field(default="claude-opus-5-5", min_length=1, max_length=80)
    ai_effort: Literal["low", "medium", "high"] = "low"
    ai_api_key: SecretStr | None = None
    ai_api_key_file: Path | None = None
    ai_timeout_seconds: int = Field(default=30, ge=5, le=120)
    ai_max_output_tokens: int = Field(default=4000, ge=500, le=16000)
    ai_user_daily_tokens: int = Field(default=200_000, ge=1)
    ai_project_monthly_cost_usd: Decimal = Field(default=Decimal("5"), ge=0)

    def effective_ai_provider(self) -> Literal["disabled", "fake", "anthropic"]:
        """Proveedor efectivo: `auto` se resuelve según haya clave o no."""
        if self.ai_provider == "auto":
            return "anthropic" if self.ai_key() else "disabled"
        return self.ai_provider

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
