import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, BusinessMixin, fk


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
