"""Master part list and preferred vendors."""

import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, fk


class PartCategory(enum.StrEnum):
    PASSIVE = "Passive"
    IC = "IC"
    DISCRETE = "Discrete"
    CONNECTOR = "Connector"
    ELECTROMECHANICAL = "Electromechanical"
    MAGNETICS = "Magnetics"
    OPTO = "Opto"
    CRYSTAL = "Crystal"
    MECHANICAL = "Mechanical"
    PCB = "PCB"
    CONSUMABLE = "Consumable"
    OTHER = "Other"


class Part(BusinessMixin, Base):
    __tablename__ = "parts"
    __table_args__ = (
        # One live part per MPN + manufacturer, case- and space-insensitive.
        Index(
            "uq_parts_mpn_manufacturer_live",
            func.upper(func.replace(text("mpn"), " ", "")),
            func.upper(func.coalesce(text("manufacturer"), "")),
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_parts_category", "category"),
        CheckConstraint("length(trim(mpn)) > 0", name="mpn_not_blank"),
        CheckConstraint("msl_level IS NULL OR msl_level BETWEEN 1 AND 6", name="msl_range"),
    )

    mpn: Mapped[str] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300))
    package: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), default=PartCategory.OTHER.value)
    unit: Mapped[str] = mapped_column(String(16), default="pcs")
    msl_level: Mapped[int | None] = mapped_column(Integer)
    min_stock: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class PartPreferredVendor(BusinessMixin, Base):
    __tablename__ = "part_preferred_vendors"
    __table_args__ = (
        Index(
            "uq_part_preferred_vendors_part_vendor_live",
            "part_id",
            "vendor_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("rank >= 1", name="rank_pos"),
    )

    part_id: Mapped[uuid.UUID] = fk("parts.id")
    vendor_id: Mapped[uuid.UUID] = fk("vendors.id")
    rank: Mapped[int] = mapped_column(Integer, default=1)
    vendor_part_number: Mapped[str | None] = mapped_column(String(100))
