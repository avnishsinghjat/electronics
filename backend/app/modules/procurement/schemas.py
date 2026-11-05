import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
Qty = Field(gt=0, max_digits=14, decimal_places=4)


class VersionIn(BaseModel):
    row_version: int


class NoteIn(BaseModel):
    row_version: int
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- vendors


class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)


class _VendorFields(BaseModel):
    gstin: str | None = Field(default=None, pattern=GSTIN)
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    contacts: list[Contact] = Field(default_factory=list, max_length=20)
    payment_terms: str | None = Field(default=None, max_length=100)
    lead_time_days: int | None = Field(default=None, ge=0, le=730)
    rating: Decimal | None = Field(default=None, ge=0, le=5, max_digits=2, decimal_places=1)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("gstin", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v


class VendorCreate(_VendorFields):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,31}$")
    name: str = Field(min_length=1, max_length=200)


class VendorUpdate(_VendorFields):
    row_version: int
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,31}$")
    name: str = Field(min_length=1, max_length=200)


class VendorOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    gstin: str | None
    address: str | None
    city: str | None
    state: str | None
    contacts: list[Contact]
    payment_terms: str | None
    lead_time_days: int | None
    rating: Decimal | None
    notes: str | None
    is_sample: bool
    open_po_count: int
    row_version: int


# ---------------------------------------------------------------- requisitions


class PrFromShortfall(BaseModel):
    """boq_line_ids empty = every line of the project with a shortfall."""

    boq_line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)
    notes: str | None = Field(default=None, max_length=2000)


class PrLineIn(BaseModel):
    boq_line_id: uuid.UUID | None = None
    part_id: uuid.UUID
    qty: Decimal = Qty
    suggested_vendor_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class PrUpdate(BaseModel):
    row_version: int
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[PrLineIn] = Field(min_length=1, max_length=5000)


class PrDecision(BaseModel):
    row_version: int
    approve: bool
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _reason(self) -> "PrDecision":
        if not self.approve and not (self.note or "").strip():
            raise ValueError("Give a reason when rejecting")
        return self


class PrLineOut(BaseModel):
    id: uuid.UUID
    boq_line_id: uuid.UUID | None
    boq_ref: str | None
    part_id: uuid.UUID
    mpn: str
    manufacturer: str | None
    description: str
    unit: str
    qty: Decimal
    suggested_vendor_id: uuid.UUID | None
    suggested_vendor_name: str | None
    notes: str | None


class PrOut(BaseModel):
    id: uuid.UUID
    number: str
    project_id: uuid.UUID
    project_code: str
    project_name: str
    status: str
    submitted_at: datetime | None
    approved_by_name: str | None
    approved_at: datetime | None
    decision_note: str | None
    notes: str | None
    created_at: datetime
    created_by_name: str | None
    line_count: int
    purchase_orders: list["PoRef"]
    row_version: int


class PrDetail(PrOut):
    lines: list[PrLineOut]


class PoRef(BaseModel):
    id: uuid.UUID
    number: str
    status: str


# ---------------------------------------------------------------- purchase orders


class AllocationIn(BaseModel):
    boq_line_id: uuid.UUID
    qty: Decimal = Qty


class PoLineIn(BaseModel):
    id: uuid.UUID | None = None  # existing line (kept on edit of a draft)
    part_id: uuid.UUID
    qty_ordered: Decimal = Qty
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    expected_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    allocations: list[AllocationIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _allocations_fit(self) -> "PoLineIn":
        if sum((a.qty for a in self.allocations), Decimal(0)) > self.qty_ordered:
            raise ValueError("Allocations exceed the ordered quantity")
        if len({a.boq_line_id for a in self.allocations}) != len(self.allocations):
            raise ValueError("A BOQ line is allocated twice on one PO line")
        return self


class PoCreate(BaseModel):
    vendor_id: uuid.UUID
    order_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    lines: list[PoLineIn] = Field(min_length=1, max_length=2000)


class PoUpdate(PoCreate):
    row_version: int


class PoLinePatch(BaseModel):
    """Follow-up on an issued order: new promised date or a note."""

    row_version: int
    expected_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class AllocationOut(BaseModel):
    id: uuid.UUID
    boq_line_id: uuid.UUID
    boq_ref: str
    project_id: uuid.UUID
    project_code: str
    qty: Decimal
    received: Decimal


class PoLineOut(BaseModel):
    id: uuid.UUID
    line_no: int
    part_id: uuid.UUID
    mpn: str
    manufacturer: str | None
    description: str
    unit: str
    msl_level: int | None
    qty_ordered: Decimal
    unit_price: Decimal | None
    amount: Decimal | None
    expected_date: date | None
    is_cancelled: bool
    notes: str | None
    qty_accepted: Decimal
    qty_rejected: Decimal
    qty_on_hold: Decimal
    outstanding: Decimal
    allocations: list[AllocationOut]
    row_version: int


class PoOut(BaseModel):
    id: uuid.UUID
    number: str
    vendor_id: uuid.UUID
    vendor_code: str
    vendor_name: str
    requisition_id: uuid.UUID | None
    requisition_number: str | None
    status: str
    order_date: date | None
    issued_at: datetime | None
    currency: str
    notes: str | None
    total: Decimal
    line_count: int
    next_expected: date | None
    project_codes: list[str]
    created_at: datetime
    row_version: int


class GrnRef(BaseModel):
    id: uuid.UUID
    number: str
    received_at: datetime | None


class PoDetail(PoOut):
    lines: list[PoLineOut]
    receipts: list[GrnRef]


# ---------------------------------------------------------------- goods receipts


class GrnLineIn(BaseModel):
    po_line_id: uuid.UUID
    location_id: uuid.UUID
    qty_received: Decimal = Qty
    qty_accepted: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=4)
    qty_rejected: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=4)
    qty_on_hold: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=4)
    batch_lot: str | None = Field(default=None, max_length=64)
    date_code: str | None = Field(default=None, max_length=32)
    msl_level: int | None = Field(default=None, ge=1, le=6)
    reject_reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _split(self) -> "GrnLineIn":
        if self.qty_accepted + self.qty_rejected + self.qty_on_hold != self.qty_received:
            raise ValueError("Accepted + rejected + on hold must equal the quantity received")
        if self.qty_rejected > 0 and not (self.reject_reason or "").strip():
            raise ValueError("Give the reason for the rejected quantity")
        return self


class GrnCreate(BaseModel):
    purchase_order_id: uuid.UUID
    delivery_note_ref: str | None = Field(default=None, max_length=100)
    received_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[GrnLineIn] = Field(min_length=1, max_length=500)


class GrnPatch(BaseModel):
    row_version: int
    coc_file_id: uuid.UUID | None = None
    delivery_note_ref: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class HoldResolution(BaseModel):
    row_version: int
    accept_qty: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=4)
    reject_qty: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=4)
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _something(self) -> "HoldResolution":
        if self.accept_qty + self.reject_qty <= 0:
            raise ValueError("Accept or reject some of the quantity on hold")
        if self.reject_qty > 0 and not (self.reason or "").strip():
            raise ValueError("Give the reason for the rejected quantity")
        return self


class GrnLineOut(BaseModel):
    id: uuid.UUID
    po_line_id: uuid.UUID
    po_line_no: int
    part_id: uuid.UUID
    mpn: str
    description: str
    location_id: uuid.UUID | None
    location_code: str | None
    qty_received: Decimal
    qty_accepted: Decimal
    qty_rejected: Decimal
    qty_on_hold: Decimal
    batch_lot: str | None
    date_code: str | None
    msl_level: int | None
    inspection_result: str
    notes: str | None
    allocated: list[AllocationOut]
    row_version: int


class GrnOut(BaseModel):
    id: uuid.UUID
    number: str
    purchase_order_id: uuid.UUID
    po_number: str
    vendor_name: str
    status: str
    received_at: datetime | None
    received_by_name: str | None
    delivery_note_ref: str | None
    coc_file_id: uuid.UUID | None
    notes: str | None
    qty_accepted: Decimal
    qty_rejected: Decimal
    qty_on_hold: Decimal
    row_version: int


class GrnDetail(GrnOut):
    lines: list[GrnLineOut]
    returns: list["ReturnOut"]


class ReturnOut(BaseModel):
    id: uuid.UUID
    number: str
    grn_id: uuid.UUID
    grn_number: str
    po_number: str
    vendor_id: uuid.UUID
    vendor_name: str
    mpn: str
    qty: Decimal
    reason: str
    status: str
    created_at: datetime
    row_version: int


class ReturnUpdate(BaseModel):
    row_version: int
    status: str = Field(pattern="^(open|shipped|credited|replaced|closed)$")
    note: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- tracker


class TrackerPo(BaseModel):
    po_id: uuid.UUID
    po_number: str
    vendor_name: str
    expected_date: date | None
    outstanding: Decimal


class TrackerLine(BaseModel):
    boq_line_id: uuid.UUID
    boq_id: uuid.UUID
    boq_name: str
    revision: str
    module_id: uuid.UUID | None
    module_code: str | None
    line_no: int
    ref_des: str | None
    part_id: uuid.UUID | None
    mpn: str | None
    manufacturer: str | None
    description: str | None
    category: str | None
    unit: str
    dnp: bool
    required_qty: Decimal
    ordered_qty: Decimal
    received_qty: Decimal
    issued_qty: Decimal
    shortfall: Decimal
    pending_receipt: Decimal
    being_ordered: Decimal  # on open requisitions and draft purchase orders
    status: str
    vendors: list[str]
    purchase_orders: list[TrackerPo]
    expected_date: date | None
    days_overdue: int
    value_pending: Decimal


class ModuleReadiness(BaseModel):
    module_id: uuid.UUID | None
    module_code: str | None
    module_name: str
    lines: int
    lines_received: int
    clear_to_build: bool
    reason: str | None


class TrackerKpis(BaseModel):
    lines: int
    lines_required: int
    pct_fully_received: float
    lines_to_order: int
    lines_awaiting_delivery: int
    overdue_lines: int
    value_pending: Decimal


class TrackerOut(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    kpis: TrackerKpis
    modules: list[ModuleReadiness]
    lines: list[TrackerLine]
    unreleased_boqs: list[str]


class PendingLine(BaseModel):
    po_id: uuid.UUID
    po_number: str
    po_status: str
    po_line_id: uuid.UUID
    line_no: int
    vendor_id: uuid.UUID
    vendor_name: str
    part_id: uuid.UUID
    mpn: str
    description: str
    qty_ordered: Decimal
    qty_received: Decimal
    outstanding: Decimal
    unit_price: Decimal | None
    value_pending: Decimal | None
    expected_date: date | None
    days_overdue: int
    project_codes: list[str]
    row_version: int


PrOut.model_rebuild()
GrnDetail.model_rebuild()
