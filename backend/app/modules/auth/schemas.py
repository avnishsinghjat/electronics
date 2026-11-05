import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ScopeOut(BaseModel):
    scope_type: str
    scope_id: uuid.UUID


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    roles: list[Role]
    permissions: list[str]
    scopes: list[ScopeOut]
    must_change_password: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_at: datetime
    user: MeOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
