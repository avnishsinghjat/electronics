import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

QtyField = Field(gt=0, max_digits=14, decimal_places=4)


class LocationOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    parent_id: uuid.UUID | None


class StockRow(BaseModel):
    part_id: uuid.UUID
    mpn: str
    manufacturer: str | None
    description: str
    category: str
    unit: str
    msl_level: int | None
    location_id: uuid.UUID
    location_code: str
    location_kind: str
    qty_on_hand: Decimal


class PartStock(BaseModel):
    part_id: uuid.UUID
    mpn: str
    manufacturer: str | None
    description: str
    category: str
    unit: str
    msl_level: int | None
    min_stock: int | None
    on_hand: Decimal
    usable: Decimal
    reserved: Decimal
    available: Decimal
    low: bool
    locations: list[str]
    row_version: int


class LedgerRow(BaseModel):
    id: int
    created_at: datetime
    part_id: uuid.UUID
    mpn: str
    location_code: str
    qty_delta: Decimal
    reason: str
    ref_type: str | None
    ref_id: uuid.UUID | None
    ref_label: str | None
    lot_code: str | None
    project_code: str | None
    note: str | None
    user_name: str | None


class LedgerPage(BaseModel):
    items: list[LedgerRow]
    total: int


class TransferIn(BaseModel):
    part_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    qty: Decimal = QtyField
    lot_code: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class AdjustmentIn(BaseModel):
    part_id: uuid.UUID
    location_id: uuid.UUID
    qty_delta: Decimal = Field(max_digits=14, decimal_places=4)
    reason: str = Field(min_length=3, max_length=1000)
    lot_code: str | None = Field(default=None, max_length=64)


class AdjustmentDecision(BaseModel):
    row_version: int
    approve: bool
    note: str | None = Field(default=None, max_length=1000)


class AdjustmentOut(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    mpn: str
    location_id: uuid.UUID
    location_code: str
    qty_delta: Decimal
    reason: str
    lot_code: str | None
    status: str
    requested_by: uuid.UUID | None
    requested_by_name: str | None
    requested_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    row_version: int


class ReservationIn(BaseModel):
    part_id: uuid.UUID
    project_id: uuid.UUID
    qty: Decimal = QtyField
    location_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)


class ReservationOut(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    mpn: str
    project_id: uuid.UUID
    project_code: str
    location_code: str | None
    qty: Decimal
    status: str
    note: str | None
    created_at: datetime
    row_version: int


class VersionIn(BaseModel):
    row_version: int
