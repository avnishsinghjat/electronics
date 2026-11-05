"""QC reports (draft -> reviewed -> approved -> issued), document drafts and design
evaluations."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, JsonB, enum_check, fk, status_column


class ReportStatus(enum.StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ISSUED = "issued"


class EvaluationStatus(enum.StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    SIGNED_OFF = "signed_off"
    REJECTED = "rejected"


class QcReport(BusinessMixin, Base):
    __tablename__ = "qc_reports"
    __table_args__ = (
        Index("uq_qc_reports_number_revision", "number", "revision", unique=True),
        enum_check("status", ReportStatus),
        CheckConstraint("revision >= 1", name="revision_pos"),
        CheckConstraint(
            "status <> 'issued' OR (pdf_sha256 IS NOT NULL AND issued_at IS NOT NULL)",
            name="issued_has_hash",
        ),
    )

    number: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    scope: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
    status: Mapped[str] = status_column(ReportStatus, ReportStatus.DRAFT)
    client_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    source_data: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    pdf_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    reviewed_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    reviewed_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    approved_at: Mapped[datetime | None]
    issued_at: Mapped[datetime | None]


class DocumentDraft(BusinessMixin, Base):
    __tablename__ = "document_drafts"
    __table_args__ = (
        Index("uq_document_drafts_number_revision", "number", "revision", unique=True),
        enum_check("status", ReportStatus),
    )

    number: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    doc_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    project_id: Mapped[uuid.UUID | None] = fk("projects.id", nullable=True)
    module_id: Mapped[uuid.UUID | None] = fk("modules.id", nullable=True)
    assembly_id: Mapped[uuid.UUID | None] = fk("pcb_assemblies.id", nullable=True)
    status: Mapped[str] = status_column(ReportStatus, ReportStatus.DRAFT)
    content: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
    source_data: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    approved_at: Mapped[datetime | None]


class DesignEvaluation(BusinessMixin, Base):
    __tablename__ = "design_evaluations"
    __table_args__ = (enum_check("status", EvaluationStatus),)

    assembly_id: Mapped[uuid.UUID] = fk("pcb_assemblies.id")
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = status_column(EvaluationStatus, EvaluationStatus.PENDING)
    kicad_version: Mapped[str | None] = mapped_column(String(32))
    source_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    notes: Mapped[str | None] = mapped_column(Text)
    signed_off_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    signed_off_at: Mapped[datetime | None]
