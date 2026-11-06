import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, JsonB, fk

# Default attrition % by part category; copied onto each new BOQ revision, editable there.
DEFAULT_ATTRITION: dict[str, float] = {
    "Passive": 2,
    "IC": 0,
    "Discrete": 1,
    "Connector": 0,
    "Electromechanical": 0,
    "Magnetics": 0,
    "Opto": 1,
    "Crystal": 0,
    "Mechanical": 0,
    "PCB": 0,
    "Consumable": 5,
    "Other": 0,
}


class CompanySettings(BusinessMixin, Base):
    """Singleton row (id fixed by the CHECK on ``singleton``)."""

    __tablename__ = "company_settings"
    __table_args__ = (CheckConstraint("singleton = 1", name="singleton"),)

    singleton: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    company_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    gstin: Mapped[str | None] = mapped_column(String(15))
    logo_file_id: Mapped[uuid.UUID | None] = fk("files.id", nullable=True)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    store_llm_transcripts: Mapped[bool] = mapped_column(Boolean, default=False)
    # Serial numbers: {serial_prefix}-{assembly code}-{year}-{running number}.
    serial_prefix: Mapped[str] = mapped_column(String(16), default="SN", server_default="SN")
    attrition_defaults: Mapped[dict[str, Any]] = mapped_column(
        JsonB, default=lambda: dict(DEFAULT_ATTRITION)
    )
