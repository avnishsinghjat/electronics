import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.models import Base, BusinessMixin, enum_check, fk, utcnow
from app.core.permissions import Role


class ScopeType(enum.StrEnum):
    DIVISION = "division"
    PROJECT = "project"


class User(BusinessMixin, Base):
    __tablename__ = "users"
    __audit_redact__ = ("password_hash",)
    __table_args__ = (
        Index("uq_users_username_lower", func.lower(text("username")), unique=True),
        CheckConstraint("failed_logins >= 0", name="failed_logins_nonneg"),
        CheckConstraint("username ~ '^[A-Za-z0-9._-]{3,64}$'", name="username_format"),
    )

    username: Mapped[str] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(BusinessMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("uq_user_roles_user_role", "user_id", "role", unique=True),
        enum_check("role", Role),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(32))


class UserScope(BusinessMixin, Base):
    """Restricts a user to divisions/projects. No scope rows = access to everything the
    user's roles allow. A division scope includes all projects in that division."""

    __tablename__ = "user_scopes"
    __table_args__ = (
        Index("uq_user_scopes_user_scope", "user_id", "scope_type", "scope_id", unique=True),
        enum_check("scope_type", ScopeType),
    )

    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    scope_type: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[uuid.UUID] = mapped_column(index=True)


class RefreshToken(Base):
    """Server-side record of a refresh token. Rotated on every use; reusing a rotated
    token revokes its whole family (stolen-token detection)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None]
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))
