"""Stage templates, work orders, their stages and stage progress per lot/serial."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, Qty, enum_check, fk, status_column


class StageCode(enum.StrEnum):
    KITTING = "kitting"
    SMT = "smt"
    REFLOW = "reflow"
    AOI = "aoi"
    THT = "tht"
    WAVE_SOLDER = "wave_solder"
    HAND_SOLDER = "hand_solder"
    CLEANING = "cleaning"
    CONFORMAL_COAT = "conformal_coat"
    PROGRAMMING = "programming"
    FUNCTIONAL_TEST = "functional_test"
    FINAL_ASSEMBLY = "final_assembly"
    PACKING = "packing"
    CUSTOM = "custom"


# Default stage list from CLAUDE.md, in order: (code, name, requires_qc).
DEFAULT_STAGES: list[tuple[StageCode, str, bool]] = [
    (StageCode.KITTING, "Kitting", False),
    (StageCode.SMT, "SMT placement", False),
    (StageCode.REFLOW, "Reflow", True),
    (StageCode.AOI, "AOI", True),
    (StageCode.THT, "THT insertion", False),
    (StageCode.WAVE_SOLDER, "Wave / hand solder", True),
    (StageCode.CLEANING, "Cleaning", False),
    (StageCode.CONFORMAL_COAT, "Conformal coat", True),
    (StageCode.PROGRAMMING, "Programming", True),
    (StageCode.FUNCTIONAL_TEST, "Functional test", True),
    (StageCode.FINAL_ASSEMBLY, "Final assembly", True),
    (StageCode.PACKING, "Packing", True),
]


class WoStatus(enum.StrEnum):
    DRAFT = "draft"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class StageStatus(enum.StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AWAITING_QC = "awaiting_qc"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class StageTemplate(BusinessMixin, Base):
    __tablename__ = "stage_templates"
    __table_args__ = (
        Index(
            "uq_stage_templates_name_live",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class StageTemplateStep(BusinessMixin, Base):
    __tablename__ = "stage_template_steps"
    __table_args__ = (
        Index("uq_stage_template_steps_template_seq", "template_id", "seq", unique=True),
        enum_check("stage_code", StageCode),
        CheckConstraint("seq > 0", name="seq_pos"),
    )

    template_id: Mapped[uuid.UUID] = fk("stage_templates.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    stage_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    requires_qc: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkOrder(BusinessMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("uq_work_orders_number", "number", unique=True),
        enum_check("status", WoStatus),
        CheckConstraint("build_qty > 0", name="build_qty_pos"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="planned_dates_ordered",
        ),
    )

    number: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    module_id: Mapped[uuid.UUID | None] = fk("modules.id", nullable=True)
    assembly_id: Mapped[uuid.UUID] = fk("pcb_assemblies.id")
    build_qty: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = status_column(WoStatus, WoStatus.DRAFT)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    released_at: Mapped[datetime | None]
    release_override_reason: Mapped[str | None] = mapped_column(Text)
    # The BOQ this order is kitted from (its current revision at kitting time).
    boq_id: Mapped[uuid.UUID | None] = fk("boqs.id", nullable=True)
    track_serials: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class WorkOrderStage(BusinessMixin, Base):
    __tablename__ = "work_order_stages"
    __table_args__ = (
        Index("uq_work_order_stages_wo_seq", "work_order_id", "seq", unique=True),
        enum_check("stage_code", StageCode),
        enum_check("status", StageStatus),
        CheckConstraint("seq > 0", name="seq_pos"),
    )

    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    stage_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    requires_qc: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = status_column(StageStatus, StageStatus.NOT_STARTED)


class StageProgress(BusinessMixin, Base):
    """Progress of one lot (or one serial within it) through one work-order stage."""

    __tablename__ = "stage_progress"
    __table_args__ = (
        Index(
            "uq_stage_progress_stage_lot",
            "work_order_stage_id",
            "lot_id",
            unique=True,
            postgresql_where=text("serial_unit_id IS NULL AND is_deleted = false"),
        ),
        Index(
            "uq_stage_progress_stage_serial",
            "work_order_stage_id",
            "serial_unit_id",
            unique=True,
            postgresql_where=text("serial_unit_id IS NOT NULL AND is_deleted = false"),
        ),
        enum_check("status", StageStatus),
        CheckConstraint("qty_passed >= 0 AND qty_failed >= 0", name="qty_nonneg"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="times_ordered",
        ),
    )

    work_order_stage_id: Mapped[uuid.UUID] = fk("work_order_stages.id", ondelete="CASCADE")
    lot_id: Mapped[uuid.UUID] = fk("build_lots.id")
    serial_unit_id: Mapped[uuid.UUID | None] = fk("serial_units.id", nullable=True)
    status: Mapped[str] = status_column(StageStatus, StageStatus.NOT_STARTED)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    qty_passed: Mapped[int] = mapped_column(Integer, default=0)
    qty_failed: Mapped[int] = mapped_column(Integer, default=0)
    operator_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)


class KitKind(enum.StrEnum):
    ISSUE = "issue"
    RETURN = "return"


class KitIssue(BusinessMixin, Base):
    """Parts issued to (or returned from) a work order against a BOQ line. Each row is
    backed by one inventory ledger entry (ISSUE or RETURN, ref boq_line) and records the
    part lot, which is what unit genealogy reads."""

    __tablename__ = "kit_issues"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_pos"),
        enum_check("kind", KitKind),
    )

    work_order_id: Mapped[uuid.UUID] = fk("work_orders.id")
    boq_line_id: Mapped[uuid.UUID] = fk("boq_lines.id")
    part_id: Mapped[uuid.UUID] = fk("parts.id")
    location_id: Mapped[uuid.UUID] = fk("inventory_locations.id")
    kind: Mapped[str] = mapped_column(String(8), default=KitKind.ISSUE.value)
    qty: Mapped[Decimal] = mapped_column(Qty)
    lot_code: Mapped[str | None] = mapped_column(String(64), index=True)
    ledger_entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_ledger.id", ondelete="RESTRICT"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)


class SerialSequence(Base):
    """Running number per assembly and year for serial numbers; incremented under a row
    lock so concurrent generation never repeats a number."""

    __tablename__ = "serial_sequences"

    assembly_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pcb_assemblies.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)
