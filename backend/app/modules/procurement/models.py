"""Vendor -> Purchase Requisition -> Purchase Order -> PO Line (allocated to BOQ lines)
-> Goods Receipt (GRN) -> Inventory Ledger; rejected quantities -> Vendor Return."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, JsonB, Money, Qty, enum_check, fk, status_column

_LIVE = text("is_deleted = false")


class PrStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"


class PoStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class GrnStatus(enum.StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    CANCELLED = "cancelled"


class InspectionResult(enum.StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    HOLD = "hold"
    PARTIAL = "partial"


class ReturnStatus(enum.StrEnum):
    OPEN = "open"
    SHIPPED = "shipped"
    CREDITED = "credited"
    REPLACED = "replaced"
    CLOSED = "closed"


class Vendor(BusinessMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("uq_vendors_code_live", "code", unique=True, postgresql_where=_LIVE),
        # GSTIN: 15 characters, 2-digit state code, PAN, entity, 'Z', checksum.
        CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="gstin_format",
        ),
        CheckConstraint("lead_time_days IS NULL OR lead_time_days >= 0", name="lead_time_nonneg"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    contacts: Mapped[list[dict[str, str]]] = mapped_column(JsonB, default=list)
    payment_terms: Mapped[str | None] = mapped_column(String(100))
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    notes: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class PurchaseRequisition(BusinessMixin, Base):
    __tablename__ = "purchase_requisitions"
    __table_args__ = (
        Index("uq_purchase_requisitions_number", "number", unique=True),
        enum_check("status", PrStatus),
    )

    number: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    status: Mapped[str] = status_column(PrStatus, PrStatus.DRAFT)
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    approved_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)


class PrLine(BusinessMixin, Base):
    __tablename__ = "pr_lines"
    __table_args__ = (CheckConstraint("qty > 0", name="qty_pos"),)

    requisition_id: Mapped[uuid.UUID] = fk("purchase_requisitions.id", ondelete="CASCADE")
    boq_line_id: Mapped[uuid.UUID | None] = fk("boq_lines.id", nullable=True)
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    qty: Mapped[Decimal] = mapped_column(Qty)
    suggested_vendor_id: Mapped[uuid.UUID | None] = fk("vendors.id", nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)


class PurchaseOrder(BusinessMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("uq_purchase_orders_number", "number", unique=True),
        enum_check("status", PoStatus),
    )

    number: Mapped[str] = mapped_column(String(32))
    vendor_id: Mapped[uuid.UUID] = fk("vendors.id")
    requisition_id: Mapped[uuid.UUID | None] = fk("purchase_requisitions.id", nullable=True)
    status: Mapped[str] = status_column(PoStatus, PoStatus.DRAFT)
    order_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    issued_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)


class PoLine(BusinessMixin, Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        Index("uq_po_lines_po_line_no", "purchase_order_id", "line_no", unique=True),
        CheckConstraint("qty_ordered > 0", name="qty_ordered_pos"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="unit_price_nonneg"),
        CheckConstraint("line_no > 0", name="line_no_pos"),
    )

    purchase_order_id: Mapped[uuid.UUID] = fk("purchase_orders.id", ondelete="CASCADE")
    line_no: Mapped[int] = mapped_column(Integer)
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    qty_ordered: Mapped[Decimal] = mapped_column(Qty)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    expected_date: Mapped[date | None] = mapped_column(Date, index=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class PoLineAllocation(BusinessMixin, Base):
    """How much of a PO line serves which BOQ line (and therefore which project)."""

    __tablename__ = "po_line_allocations"
    __table_args__ = (
        Index(
            "uq_po_line_allocations_line_boq_live",
            "po_line_id",
            "boq_line_id",
            unique=True,
            postgresql_where=_LIVE,
        ),
        CheckConstraint("qty > 0", name="qty_pos"),
    )

    po_line_id: Mapped[uuid.UUID] = fk("po_lines.id", ondelete="CASCADE")
    boq_line_id: Mapped[uuid.UUID] = fk("boq_lines.id")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    qty: Mapped[Decimal] = mapped_column(Qty)


class GoodsReceipt(BusinessMixin, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index("uq_goods_receipts_number", "number", unique=True),
        enum_check("status", GrnStatus),
    )

    number: Mapped[str] = mapped_column(String(32))
    purchase_order_id: Mapped[uuid.UUID] = fk("purchase_orders.id")
    status: Mapped[str] = status_column(GrnStatus, GrnStatus.DRAFT)
    received_at: Mapped[datetime | None]
    received_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    delivery_note_ref: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)


class GrnLine(BusinessMixin, Base):
    __tablename__ = "grn_lines"
    __table_args__ = (
        CheckConstraint("qty_received > 0", name="qty_received_pos"),
        CheckConstraint(
            "qty_accepted >= 0 AND qty_rejected >= 0 AND qty_on_hold >= 0", name="qty_parts_nonneg"
        ),
        CheckConstraint(
            "qty_accepted + qty_rejected + qty_on_hold = qty_received", name="qty_parts_sum"
        ),
        CheckConstraint("msl_level IS NULL OR msl_level BETWEEN 1 AND 6", name="msl_range"),
        enum_check("inspection_result", InspectionResult),
    )

    goods_receipt_id: Mapped[uuid.UUID] = fk("goods_receipts.id", ondelete="CASCADE")
    po_line_id: Mapped[uuid.UUID] = fk("po_lines.id")
    location_id: Mapped[uuid.UUID | None] = fk("inventory_locations.id", nullable=True)
    qty_received: Mapped[Decimal] = mapped_column(Qty)
    qty_accepted: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    qty_rejected: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    qty_on_hold: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    batch_lot: Mapped[str | None] = mapped_column(String(64))
    date_code: Mapped[str | None] = mapped_column(String(32))
    msl_level: Mapped[int | None] = mapped_column(Integer)
    inspection_result: Mapped[str] = mapped_column(
        String(16), default=InspectionResult.ACCEPT.value
    )
    notes: Mapped[str | None] = mapped_column(Text)


class VendorReturn(BusinessMixin, Base):
    __tablename__ = "vendor_returns"
    __table_args__ = (
        Index("uq_vendor_returns_number", "number", unique=True),
        CheckConstraint("qty > 0", name="qty_pos"),
        enum_check("status", ReturnStatus),
    )

    number: Mapped[str] = mapped_column(String(32))
    grn_line_id: Mapped[uuid.UUID] = fk("grn_lines.id")
    vendor_id: Mapped[uuid.UUID] = fk("vendors.id")
    qty: Mapped[Decimal] = mapped_column(Qty)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = status_column(ReturnStatus, ReturnStatus.OPEN)
