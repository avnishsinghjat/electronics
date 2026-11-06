import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.modules.production.models import StageCode


class VersionIn(BaseModel):
    row_version: int


# ---------------------------------------------------------------- stage templates


class StepIn(BaseModel):
    stage_code: StageCode
    name: str = Field(min_length=1, max_length=120)
    requires_qc: bool = False


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    copy_from_id: uuid.UUID | None = None


class TemplateUpdate(BaseModel):
    row_version: int
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[StepIn] = Field(min_length=1, max_length=40)


class StepOut(BaseModel):
    id: uuid.UUID
    seq: int
    stage_code: str
    name: str
    requires_qc: bool


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_default: bool
    assembly_count: int
    steps: list[StepOut]
    row_version: int


# ---------------------------------------------------------------- work orders


class WoCreate(BaseModel):
    assembly_id: uuid.UUID
    build_qty: int = Field(ge=1, le=1_000_000)
    planned_start: date | None = None
    planned_end: date | None = None
    track_serials: bool = True
    boq_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _dates(self) -> "WoCreate":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("The planned end is before the planned start")
        return self


class WoUpdate(BaseModel):
    row_version: int
    build_qty: int = Field(ge=1, le=1_000_000)
    planned_start: date | None = None
    planned_end: date | None = None
    track_serials: bool = True
    boq_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _dates(self) -> "WoUpdate":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("The planned end is before the planned start")
        return self


class ReleaseIn(BaseModel):
    row_version: int
    override_reason: str | None = Field(default=None, max_length=2000)


class Readiness(BaseModel):
    clear_to_build: bool
    reason: str | None
    lines: int
    lines_received: int


class StageSummary(BaseModel):
    id: uuid.UUID
    seq: int
    stage_code: str
    name: str
    requires_qc: bool
    status: str
    units_in: int  # units that reached this stage
    units_done: int  # passed here (or completed, for lot tracking)
    units_failed: int
    units_awaiting_qc: int


class WoOut(BaseModel):
    id: uuid.UUID
    number: str
    project_id: uuid.UUID
    project_code: str
    project_name: str
    module_id: uuid.UUID | None
    module_code: str | None
    assembly_id: uuid.UUID
    assembly_label: str
    boq_id: uuid.UUID | None
    build_qty: int
    status: str
    planned_start: date | None
    planned_end: date | None
    released_at: datetime | None
    release_override_reason: str | None
    track_serials: bool
    notes: str | None
    lot_id: uuid.UUID | None
    lot_number: str | None
    current_stage: str | None
    units_completed: int
    units_failed: int
    serial_count: int
    created_at: datetime
    row_version: int


class WoDetail(WoOut):
    stages: list[StageSummary]
    readiness: Readiness | None


# ---------------------------------------------------------------- kitting


class KitLine(BaseModel):
    boq_line_id: uuid.UUID
    line_no: int
    ref_des: str | None
    part_id: uuid.UUID | None
    mpn: str | None
    description: str | None
    unit: str
    dnp: bool
    required: Decimal  # for this order's build quantity
    issued: Decimal
    shortage: Decimal
    available: Decimal  # usable stock, any project
    reserved_for_project: Decimal


class KitOut(BaseModel):
    boq_id: uuid.UUID | None
    boq_name: str | None
    revision: str | None
    lines: list[KitLine]
    complete: bool


class StockLot(BaseModel):
    location_id: uuid.UUID
    location_code: str
    lot_code: str | None
    qty: Decimal


class KitIssueIn(BaseModel):
    boq_line_id: uuid.UUID
    location_id: uuid.UUID
    qty: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    lot_code: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class KitBatchIn(BaseModel):
    issues: list[KitIssueIn] = Field(min_length=1, max_length=500)


class KitRecord(BaseModel):
    id: uuid.UUID
    kind: str
    boq_line_id: uuid.UUID
    mpn: str
    location_code: str
    lot_code: str | None
    qty: Decimal
    note: str | None
    created_at: datetime
    created_by_name: str | None


# ---------------------------------------------------------------- serials and progress


class SerialsIn(BaseModel):
    count: int | None = Field(default=None, ge=1, le=10_000)


class UnitOut(BaseModel):
    id: uuid.UUID
    serial_number: str
    status: str
    current_stage: str | None
    current_stage_id: uuid.UUID | None
    current_stage_status: str | None


class ProgressIn(BaseModel):
    """Lot tracking: qty_passed/qty_failed when completing. Serial tracking: passed."""

    action: str = Field(pattern="^(start|finish|complete)$")
    serial_unit_id: uuid.UUID | None = None
    qty_passed: int | None = Field(default=None, ge=0)
    qty_failed: int | None = Field(default=None, ge=0)
    passed: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ProgressOut(BaseModel):
    id: uuid.UUID
    work_order_stage_id: uuid.UUID
    stage_name: str
    seq: int
    serial_unit_id: uuid.UUID | None
    serial_number: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    qty_passed: int
    qty_failed: int
    operator_name: str | None
    notes: str | None


class GenealogyPart(BaseModel):
    boq_line_id: uuid.UUID
    ref_des: str | None
    mpn: str
    lot_code: str | None
    qty: Decimal  # net issued to the work order from that lot


class Genealogy(BaseModel):
    serial_number: str
    work_order_id: uuid.UUID
    work_order_number: str
    lot_number: str | None
    assembly_label: str
    parts: list[GenealogyPart]


class ScanResult(BaseModel):
    serial_unit_id: uuid.UUID
    serial_number: str
    work_order_id: uuid.UUID
    work_order_number: str
    unit_status: str
    stage: ProgressOut | None
    stage_id: uuid.UUID | None
    stage_name: str | None
    stage_requires_qc: bool
    next_action: str | None  # start | finish | complete | None (done or waiting for QC)


# ---------------------------------------------------------------- board


class BoardCard(BaseModel):
    work_order_id: uuid.UUID
    number: str
    project_code: str
    assembly_label: str
    build_qty: int
    status: str
    stage_name: str | None
    stage_seq: int | None
    stage_count: int
    units_at_stage: int
    units_done_at_stage: int
    awaiting_qc: int
    planned_end: date | None


class BoardColumn(BaseModel):
    key: str
    label: str
    cards: list[BoardCard]
