"""BOQ (per project, optionally per module) -> revisions (A, B, C...) -> lines."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, Money, Qty, enum_check, fk, status_column

_LIVE = text("is_deleted = false")


class RevisionStatus(enum.StrEnum):
    DRAFT = "draft"
    RELEASED = "released"
    SUPERSEDED = "superseded"


class Boq(BusinessMixin, Base):
    __tablename__ = "boqs"
    __table_args__ = (
        Index(
            "uq_boqs_project_module_name_live",
            "project_id",
            text("coalesce(module_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "name",
            unique=True,
            postgresql_where=_LIVE,
        ),
    )

    project_id: Mapped[uuid.UUID] = fk("projects.id")
    module_id: Mapped[uuid.UUID | None] = fk("modules.id", nullable=True)
    assembly_id: Mapped[uuid.UUID | None] = fk("pcb_assemblies.id", nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class BoqRevision(BusinessMixin, Base):
    __tablename__ = "boq_revisions"
    __table_args__ = (
        Index("uq_boq_revisions_boq_revision", "boq_id", "revision", unique=True),
        # Only one released revision per BOQ.
        Index(
            "uq_boq_revisions_one_released",
            "boq_id",
            unique=True,
            postgresql_where=text("status = 'released' AND is_deleted = false"),
        ),
        enum_check("status", RevisionStatus),
        CheckConstraint("build_qty >= 0", name="build_qty_nonneg"),
    )

    boq_id: Mapped[uuid.UUID] = fk("boqs.id")
    revision: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = status_column(RevisionStatus, RevisionStatus.DRAFT)
    build_qty: Mapped[int] = mapped_column(Integer, default=1)
    source_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    released_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)


class BoqLine(BusinessMixin, Base):
    __tablename__ = "boq_lines"
    __table_args__ = (
        Index("uq_boq_lines_revision_line_key", "revision_id", "line_key", unique=True),
        Index("uq_boq_lines_revision_line_no", "revision_id", "line_no", unique=True),
        CheckConstraint("qty_per_unit >= 0", name="qty_per_unit_nonneg"),
        CheckConstraint("attrition_pct >= 0 AND attrition_pct <= 100", name="attrition_range"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="unit_price_nonneg"),
        CheckConstraint("line_no > 0", name="line_no_pos"),
    )

    revision_id: Mapped[uuid.UUID] = fk("boq_revisions.id", ondelete="CASCADE")
    # Stable across revisions so lines can be diffed (Phase 5).
    line_key: Mapped[str] = mapped_column(String(64))
    line_no: Mapped[int] = mapped_column(Integer)
    part_id: Mapped[uuid.UUID | None] = fk("parts.id", nullable=True)
    ref_des: Mapped[str | None] = mapped_column(Text)
    qty_per_unit: Mapped[Decimal] = mapped_column(Qty)
    mpn: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(300))
    value: Mapped[str | None] = mapped_column(String(64))
    package: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(16), default="pcs")
    dnp: Mapped[bool] = mapped_column(Boolean, default=False)
    attrition_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    preferred_vendor_id: Mapped[uuid.UUID | None] = fk("vendors.id", nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
