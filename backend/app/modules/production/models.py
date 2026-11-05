"""Stage templates, work orders, their stages and stage progress per lot/serial."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, enum_check, fk, status_column


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
