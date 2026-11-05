import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.permissions import Role
from app.modules.auth.models import ScopeType


class ScopeIn(BaseModel):
    scope_type: ScopeType
    scope_id: uuid.UUID


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    is_active: bool
    must_change_password: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    roles: list[Role]
    scopes: list[ScopeIn]
    row_version: int
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,64}$")
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    roles: list[Role] = Field(min_length=1)
    scopes: list[ScopeIn] = Field(default_factory=list)
    temporary_password: str | None = Field(default=None, max_length=256)


class UserUpdate(BaseModel):
    row_version: int
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    roles: list[Role] | None = Field(default=None, min_length=1)
    scopes: list[ScopeIn] | None = None


class VersionIn(BaseModel):
    row_version: int


class ResetPasswordIn(BaseModel):
    row_version: int
    temporary_password: str | None = Field(default=None, max_length=256)


class UserWithPassword(BaseModel):
    """Returned once when a temporary password is set; never stored in clear."""

    user: UserOut
    temporary_password: str


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


class RoleInfo(BaseModel):
    role: Role
    label: str
    permissions: list[str]


class PermissionInfo(BaseModel):
    permission: str
    description: str
