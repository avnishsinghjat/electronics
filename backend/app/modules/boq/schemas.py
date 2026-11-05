import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RevisionSummary(BaseModel):
    id: uuid.UUID
    revision: str
    status: str
    build_qty: int
    line_count: int
    released_at: datetime | None
    created_at: datetime
    row_version: int


class BoqOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    project_name: str
    module_id: uuid.UUID | None
    module_code: str | None
    assembly_id: uuid.UUID | None
    assembly_label: str | None
    name: str
    notes: str | None
    row_version: int
    revisions: list[RevisionSummary]


class BoqCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    module_id: uuid.UUID | None = None
    assembly_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)
    build_qty: int | None = Field(default=None, ge=0, le=10_000_000)
    create_revision: bool = True


class LineOut(BaseModel):
    id: uuid.UUID
    line_key: str
    line_no: int
    part_id: uuid.UUID | None
    ref_des: str | None
    qty_per_unit: Decimal
    mpn: str | None
    manufacturer: str | None
    description: str | None
    value: str | None
    package: str | None
    category: str | None
    unit: str
    dnp: bool
    attrition_pct: Decimal
    attrition_override: bool
    unit_price: Decimal | None
    preferred_vendor_id: uuid.UUID | None
    notes: str | None
    # From the status service (single source of truth).
    required_qty: Decimal
    ordered_qty: Decimal
    received_qty: Decimal
    issued_qty: Decimal
    shortfall: Decimal
    pending_receipt: Decimal
    status: str


class RevisionOut(BaseModel):
    id: uuid.UUID
    boq_id: uuid.UUID
    revision: str
    status: str
    build_qty: int
    attrition_by_category: dict[str, float]
    released_at: datetime | None
    notes: str | None
    row_version: int
    lines: list[LineOut]


class LineIn(BaseModel):
    line_key: str | None = Field(default=None, max_length=64)
    part_id: uuid.UUID | None = None
    ref_des: str | None = Field(default=None, max_length=10000)
    qty_per_unit: Decimal = Field(ge=0, le=Decimal("1e9"))
    mpn: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    value: str | None = Field(default=None, max_length=64)
    package: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=32)
    unit: str = Field(default="pcs", min_length=1, max_length=16)
    dnp: bool = False
    attrition_pct: Decimal | None = Field(default=None, ge=0, le=100)
    unit_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class LinesSave(BaseModel):
    row_version: int
    lines: list[LineIn] = Field(max_length=20000)


class BuildUpdate(BaseModel):
    row_version: int
    build_qty: int | None = Field(default=None, ge=0, le=10_000_000)
    attrition_by_category: dict[str, float] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VersionIn(BaseModel):
    row_version: int


class DiffLine(BaseModel):
    line_key: str
    change: str  # added | removed | qty_changed | substituted | changed | unchanged
    from_line: dict[str, Any] | None
    to_line: dict[str, Any] | None
    changed_fields: list[str]


class CompareOut(BaseModel):
    boq_id: uuid.UUID
    from_revision: str
    to_revision: str
    summary: dict[str, int]
    lines: list[DiffLine]


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_id: uuid.UUID
    file_id: uuid.UUID
    file_name: str
    status: str
    encoding: str | None
    delimiter: str | None
    sheet: str | None
    header_row: int | None
    headers: list[str] | None
    preview_rows: list[list[str]]
    total_rows: int
    mapping: dict[str, int] | None
    suggested_template_id: uuid.UUID | None
    result: dict[str, Any] | None
    error: str | None
    revision_id: uuid.UUID | None
    row_version: int


class MappingIn(BaseModel):
    row_version: int
    header_row: int = Field(ge=0)
    mapping: dict[str, int]
    decimal_comma: bool = False
    save_template_name: str | None = Field(default=None, min_length=1, max_length=120)
    template_client: str | None = Field(default=None, max_length=200)


class CommitIn(BaseModel):
    row_version: int
    release: bool = False
    build_qty: int | None = Field(default=None, ge=0, le=10_000_000)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    client_name: str | None
    mapping: dict[str, str]
    row_version: int


class FieldInfo(BaseModel):
    field: str
    label: str
