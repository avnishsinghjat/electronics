"""QC Template -> Checklist Items -> QC Inspection -> Results (+ photo evidence in
``files`` with ref_type 'qc_result') -> NCR -> Disposition."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, enum_check, fk, status_column


class ItemType(enum.StrEnum):
    VISUAL = "visual"
    MEASUREMENT = "measurement"
    FUNCTIONAL = "functional"
    DOCUMENT = "document"
    TEXT = "text"


class TemplateStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class InspectionStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


class ResultValue(enum.StrEnum):
    PENDING = "pending"
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    NA = "na"


class Severity(enum.StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class Disposition(enum.StrEnum):
    REWORK = "rework"
    USE_AS_IS = "use_as_is"
    SCRAP = "scrap"
    RETURN_TO_VENDOR = "return_to_vendor"


class NcrStatus(enum.StrEnum):
    OPEN = "open"
    DISPOSITIONED = "dispositioned"
    REWORK_DONE = "rework_done"
    CLOSED = "closed"


class QcTemplate(BusinessMixin, Base):
    __tablename__ = "qc_templates"
    __table_args__ = (
        Index("uq_qc_templates_code_version", "code", "version", unique=True),
        enum_check("status", TemplateStatus),
        CheckConstraint("version >= 1", name="version_pos"),
    )

    code: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200))
    stage_code: Mapped[str] = mapped_column(String(32), index=True)
    assembly_id: Mapped[uuid.UUID | None] = fk("pcb_assemblies.id", nullable=True)
    ipc_class: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = status_column(TemplateStatus, TemplateStatus.DRAFT)
    description: Mapped[str | None] = mapped_column(Text)


class QcTemplateItem(BusinessMixin, Base):
    __tablename__ = "qc_template_items"
    __table_args__ = (
        Index("uq_qc_template_items_template_seq", "template_id", "seq", unique=True),
        enum_check("item_type", ItemType),
        CheckConstraint(
            "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
            name="limits_ordered",
        ),
        CheckConstraint("min_photos >= 0", name="min_photos_nonneg"),
        CheckConstraint("NOT photo_required OR min_photos >= 1", name="photo_required_count"),
    )

    template_id: Mapped[uuid.UUID] = fk("qc_templates.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    item_type: Mapped[str] = mapped_column(String(16))
    prompt: Mapped[str] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str | None] = mapped_column(String(16))
    photo_required: Mapped[bool] = mapped_column(Boolean, default=False)
    min_photos: Mapped[int] = mapped_column(Integer, default=0)
    reference_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)


class QcInspection(BusinessMixin, Base):
    __tablename__ = "qc_inspections"
    __table_args__ = (
        Index("uq_qc_inspections_number", "number", unique=True),
        enum_check("status", InspectionStatus),
        CheckConstraint(
            "lot_id IS NOT NULL OR serial_unit_id IS NOT NULL OR grn_line_id IS NOT NULL",
            name="has_subject",
        ),
    )

    number: Mapped[str] = mapped_column(String(32))
    template_id: Mapped[uuid.UUID] = fk("qc_templates.id")
    work_order_stage_id: Mapped[uuid.UUID | None] = fk("work_order_stages.id", nullable=True)
    lot_id: Mapped[uuid.UUID | None] = fk("build_lots.id", nullable=True)
    serial_unit_id: Mapped[uuid.UUID | None] = fk("serial_units.id", nullable=True)
    grn_line_id: Mapped[uuid.UUID | None] = fk("grn_lines.id", nullable=True)
    stage_code: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = status_column(InspectionStatus, InspectionStatus.PENDING)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    reinspection_of_id: Mapped[uuid.UUID | None] = fk("qc_inspections.id", nullable=True)


class QcResult(BusinessMixin, Base):
    __tablename__ = "qc_results"
    __table_args__ = (
        Index("uq_qc_results_inspection_item", "inspection_id", "template_item_id", unique=True),
        enum_check("result", ResultValue),
    )

    inspection_id: Mapped[uuid.UUID] = fk("qc_inspections.id", ondelete="CASCADE")
    template_item_id: Mapped[uuid.UUID] = fk("qc_template_items.id")
    result: Mapped[str] = mapped_column(String(16), default=ResultValue.PENDING.value, index=True)
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Ncr(BusinessMixin, Base):
    __tablename__ = "ncrs"
    __table_args__ = (
        Index("uq_ncrs_number", "number", unique=True),
        enum_check("status", NcrStatus),
        enum_check("severity", Severity),
        enum_check("disposition", Disposition, nullable=True),
        CheckConstraint(
            "status <> 'closed' OR (disposition IS NOT NULL AND closed_at IS NOT NULL)",
            name="closed_has_disposition",
        ),
    )

    number: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    inspection_id: Mapped[uuid.UUID | None] = fk("qc_inspections.id", nullable=True)
    qc_result_id: Mapped[uuid.UUID | None] = fk("qc_results.id", nullable=True)
    serial_unit_id: Mapped[uuid.UUID | None] = fk("serial_units.id", nullable=True)
    lot_id: Mapped[uuid.UUID | None] = fk("build_lots.id", nullable=True)
    defect_category: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    description: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str | None] = mapped_column(String(32))
    rework_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = status_column(NcrStatus, NcrStatus.OPEN)
    reinspection_id: Mapped[uuid.UUID | None] = fk("qc_inspections.id", nullable=True)
    closed_by: Mapped[uuid.UUID | None]
    closed_at: Mapped[datetime | None]
