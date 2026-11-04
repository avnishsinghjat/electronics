"""Locations, the append-only inventory ledger, the materialised stock balance and
project reservations. Stock on hand is ALWAYS SUM(ledger.qty_delta); the balance table
is maintained in the same transaction as each ledger row (see service.post_movement)."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, Qty, enum_check, fk, status_column, utcnow


class LocationKind(enum.StrEnum):
    STORES = "stores"
    BIN = "bin"
    MSL_CABINET = "msl_cabinet"
    WIP = "wip"
    QUARANTINE = "quarantine"
    SCRAP = "scrap"


class LedgerReason(enum.StrEnum):
    GRN = "GRN"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    ADJUST = "ADJUST"
    SCRAP = "SCRAP"
    TRANSFER = "TRANSFER"


class ReservationStatus(enum.StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"


class InventoryLocation(BusinessMixin, Base):
    __tablename__ = "inventory_locations"
    __table_args__ = (
        Index(
            "uq_inventory_locations_code_live",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        enum_check("kind", LocationKind),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    parent_id: Mapped[uuid.UUID | None] = fk("inventory_locations.id", nullable=True)


class LedgerEntry(Base):
    """Append-only. UPDATE and DELETE are rejected by a database trigger."""

    __tablename__ = "inventory_ledger"
    __table_args__ = (
        enum_check("reason", LedgerReason),
        CheckConstraint("qty_delta <> 0", name="qty_delta_nonzero"),
        CheckConstraint(
            "(reason IN ('GRN', 'RETURN') AND qty_delta > 0)"
            " OR (reason IN ('ISSUE', 'SCRAP') AND qty_delta < 0)"
            " OR reason IN ('ADJUST', 'TRANSFER')",
            name="reason_sign",
        ),
        Index("ix_inventory_ledger_ref", "ref_type", "ref_id"),
        Index("ix_inventory_ledger_part_location", "part_id", "location_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    part_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parts.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"), index=True
    )
    qty_delta: Mapped[Decimal] = mapped_column(Qty)
    reason: Mapped[str] = mapped_column(String(16), index=True)
    ref_type: Mapped[str | None] = mapped_column(String(64))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    lot_code: Mapped[str | None] = mapped_column(String(64), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class StockBalance(Base):
    """Materialised SUM(ledger) per part and location; never written directly."""

    __tablename__ = "stock_balances"
    __table_args__ = (CheckConstraint("qty_on_hand >= 0", name="qty_on_hand_nonneg"),)

    part_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parts.id", ondelete="RESTRICT"), primary_key=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    qty_on_hand: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StockReservation(BusinessMixin, Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_pos"),
        enum_check("status", ReservationStatus),
    )

    part_id: Mapped[uuid.UUID] = fk("parts.id")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    location_id: Mapped[uuid.UUID | None] = fk("inventory_locations.id", nullable=True)
    qty: Mapped[Decimal] = mapped_column(Qty)
    status: Mapped[str] = status_column(ReservationStatus, ReservationStatus.ACTIVE)
    note: Mapped[str | None] = mapped_column(Text)
