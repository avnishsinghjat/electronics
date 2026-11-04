"""Declarative base, naming conventions and the business-record mixin."""

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Quantities: up to 14 integer digits and 4 decimals (wire in metres, paste in grams).
Qty = Numeric(18, 4)
Money = Numeric(14, 4)
JsonB = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(),
        Decimal: Qty,
        int: Integer(),
    }


class Audited:
    """Marker: rows of this class are written to the audit log on insert/update/delete."""


class BusinessMixin(Audited):
    """id (UUIDv7), timestamps, actors, soft delete and optimistic-lock row_version."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.__table__.c.row_version}  # type: ignore[attr-defined]


def fk(
    target: str,
    *,
    nullable: bool = False,
    ondelete: str = "RESTRICT",
    index: bool = True,
) -> Any:
    """Foreign key column, always indexed (rule: an index on every FK)."""
    return mapped_column(ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def enum_check(
    column: str, values: type[enum.StrEnum], *, nullable: bool = False
) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    expr = f"{column} IN ({allowed})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=f"{column}_valid")


def status_column(enum_cls: type[enum.StrEnum], default: enum.StrEnum) -> Any:
    """Indexed short string column holding a StrEnum value (validated by enum_check)."""
    return mapped_column(String(32), default=default.value, index=True)


__all__ = [
    "Audited",
    "Base",
    "BigInteger",
    "BusinessMixin",
    "JsonB",
    "Money",
    "Qty",
    "enum_check",
    "fk",
    "status_column",
    "utcnow",
]
