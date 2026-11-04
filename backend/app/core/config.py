"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FABTRACK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fabtrack"
    data_dir: Path = Path("./var/data")
    log_level: str = "INFO"
    log_json: bool = True
    # Air-gapped mode blocks every outbound call at the LLM gateway (Phase 9). Default ON.
    air_gapped: bool = True
    db_pool_size: int = Field(default=10, ge=1)
    db_connect_timeout_s: float = Field(default=5.0, gt=0)
    worker_heartbeat_file: Path = Path("./var/worker.heartbeat")
    worker_poll_interval_s: float = Field(default=2.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
