from typing import Literal

from pydantic import BaseModel

ComponentStatus = Literal["ok", "degraded", "error"]


class DatabaseHealth(BaseModel):
    status: ComponentStatus
    latency_ms: float | None
    detail: str | None = None


class DiskHealth(BaseModel):
    status: ComponentStatus
    path: str
    free_bytes: int | None
    total_bytes: int | None
    detail: str | None = None


class LlmHealth(BaseModel):
    status: Literal["not_configured", "ok", "degraded", "error", "disabled"]
    provider: str | None
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    air_gapped: bool
    database: DatabaseHealth
    disk: DiskHealth
    llm: LlmHealth
