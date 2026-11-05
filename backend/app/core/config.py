"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me"  # noqa: S105


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

    # Authentication. The secret signs access tokens; set a long random value in production.
    secret_key: str = DEV_SECRET
    access_token_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_days: int = Field(default=7, ge=1, le=90)
    # Send the refresh cookie only over HTTPS (on once LAN HTTPS is set up, Phase 15).
    cookie_secure: bool = False
    max_failed_logins: int = Field(default=5, ge=1)
    lockout_minutes: int = Field(default=15, ge=1)
    min_password_length: int = Field(default=10, ge=8)

    @model_validator(mode="after")
    def _production_needs_secret(self) -> "Settings":
        weak = self.secret_key == DEV_SECRET or len(self.secret_key) < 32
        if self.env == "production" and weak:
            raise ValueError(
                "FABTRACK_SECRET_KEY must be set to a random value of 32+ characters in production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
