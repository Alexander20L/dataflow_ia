from functools import lru_cache
from pathlib import Path

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
