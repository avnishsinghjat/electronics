"""Division -> Project -> Module -> PCB Assembly -> Build Lot -> Serialised Unit."""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, enum_check, fk, status_column


class ProjectStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LotStatus(enum.StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SCRAPPED = "scrapped"


class UnitStatus(enum.StrEnum):
    IN_PRODUCTION = "in_production"
    PASSED = "passed"
    FAILED = "failed"
    REWORK = "rework"
    SCRAPPED = "scrapped"
    SHIPPED = "shipped"


_LIVE = text("is_deleted = false")


class Division(BusinessMixin, Base):
    __tablename__ = "divisions"
    __table_args__ = (Index("uq_divisions_code_live", "code", unique=True, postgresql_where=_LIVE),)

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(BusinessMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("uq_projects_code_live", "code", unique=True, postgresql_where=_LIVE),
        enum_check("status", ProjectStatus),
        CheckConstraint(
            "due_date IS NULL OR start_date IS NULL OR due_date >= start_date", name="dates_ordered"
        ),
    )

    division_id: Mapped[uuid.UUID] = fk("divisions.id")
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    client_po_ref: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = status_column(ProjectStatus, ProjectStatus.DRAFT)
    # FK to users is added with the users table in Phase 3.
    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Module(BusinessMixin, Base):
    """A deliverable unit of a project (e.g. "Controller module", qty 50)."""

    __tablename__ = "modules"
    __table_args__ = (
        Index(
            "uq_modules_project_code_live",
            "project_id",
            "code",
            unique=True,
            postgresql_where=_LIVE,
        ),
        CheckConstraint("qty_to_deliver >= 0", name="qty_to_deliver_nonneg"),
    )

    project_id: Mapped[uuid.UUID] = fk("projects.id")
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    qty_to_deliver: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text)


class PcbAssembly(BusinessMixin, Base):
    """A board revision used in a module."""

    __tablename__ = "pcb_assemblies"
    __table_args__ = (
        Index(
            "uq_pcb_assemblies_module_code_rev_live",
            "module_id",
            "code",
            "revision",
            unique=True,
            postgresql_where=_LIVE,
        ),
        CheckConstraint("layer_count BETWEEN 1 AND 64", name="layer_count_range"),
        CheckConstraint("qty_per_module > 0", name="qty_per_module_pos"),
        CheckConstraint(
            "(size_x_mm IS NULL OR size_x_mm > 0) AND (size_y_mm IS NULL OR size_y_mm > 0)",
            name="size_pos",
        ),
    )

    module_id: Mapped[uuid.UUID] = fk("modules.id")
    code: Mapped[str] = mapped_column(String(32))  # used in serial numbers
    board_name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[str] = mapped_column(String(16))
    qty_per_module: Mapped[int] = mapped_column(Integer, default=1)
    layer_count: Mapped[int] = mapped_column(Integer, default=2)
    size_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    size_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    finish: Mapped[str | None] = mapped_column(String(64))
    kicad_project_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    assembly_drawing_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    stage_template_id: Mapped[uuid.UUID | None] = fk("stage_templates.id", nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)


class BuildLot(BusinessMixin, Base):
    __tablename__ = "build_lots"
    __table_args__ = (
        Index("uq_build_lots_lot_number_live", "lot_number", unique=True, postgresql_where=_LIVE),
        enum_check("status", LotStatus),
        CheckConstraint("qty > 0", name="qty_pos"),
    )

    assembly_id: Mapped[uuid.UUID] = fk("pcb_assemblies.id")
    work_order_id: Mapped[uuid.UUID | None] = fk("work_orders.id", nullable=True)
    lot_number: Mapped[str] = mapped_column(String(32))
    qty: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = status_column(LotStatus, LotStatus.PLANNED)


class SerialUnit(BusinessMixin, Base):
    __tablename__ = "serial_units"
    __table_args__ = (
        Index(
            "uq_serial_units_assembly_serial_live",
            "assembly_id",
            "serial_number",
            unique=True,
            postgresql_where=_LIVE,
        ),
        enum_check("status", UnitStatus),
    )

    assembly_id: Mapped[uuid.UUID] = fk("pcb_assemblies.id")
    lot_id: Mapped[uuid.UUID | None] = fk("build_lots.id", nullable=True)
    serial_number: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = status_column(UnitStatus, UnitStatus.IN_PRODUCTION)
