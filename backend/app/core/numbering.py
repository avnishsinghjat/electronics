"""Document numbering: PRJ-2026-0001, PO-2026-0001, GRN-, WO-, QC-, NCR-, RPT- ...

Gap-free and concurrency-safe: the counter row is locked with SELECT ... FOR UPDATE
and incremented inside the caller's transaction. If that transaction rolls back, the
increment rolls back with it, so no number is ever skipped or issued twice.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Integer, String, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.errors import AppError, NotFoundError
from app.core.models import Base

# Defaults inserted by migration 0002; editable by Admin (setup wizard, Phase 3).
DEFAULT_DOC_TYPES: dict[str, str] = {
    "PRJ": "Project",
    "PR": "Purchase requisition",
    "PO": "Purchase order",
    "GRN": "Goods receipt note",
    "RTN": "Vendor return",
    "WO": "Work order",
    "LOT": "Build lot",
    "QC": "QC inspection",
    "NCR": "Non-conformance report",
    "RPT": "QC report",
    "DOC": "Document draft",
}


class DocumentNumberConfig(Base):
    __tablename__ = "document_number_config"

    doc_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    description: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16))
    padding: Mapped[int] = mapped_column(Integer, default=4)
    yearly_reset: Mapped[bool] = mapped_column(Boolean, default=True)


class DocumentSequence(Base):
    __tablename__ = "document_sequences"

    doc_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


def format_number(prefix: str, year: int, value: int, padding: int, *, yearly: bool) -> str:
    return f"{prefix}-{year}-{value:0{padding}d}" if yearly else f"{prefix}-{value:0{padding}d}"


async def next_number(session: AsyncSession, doc_type: str, *, year: int | None = None) -> str:
    config = await session.get(DocumentNumberConfig, doc_type)
    if config is None:
        raise NotFoundError(f"Unknown document type {doc_type}", code="unknown_doc_type")
    year = year or datetime.now(UTC).year
    seq_year = year if config.yearly_reset else 0
    await session.execute(
        pg_insert(DocumentSequence)
        .values(doc_type=doc_type, year=seq_year, last_value=0)
        .on_conflict_do_nothing()
    )
    current = (
        await session.execute(
            select(DocumentSequence.last_value)
            .where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == seq_year)
            .with_for_update()
        )
    ).scalar_one()
    value = current + 1
    await session.execute(
        update(DocumentSequence)
        .where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == seq_year)
        .values(last_value=value)
    )
    return format_number(config.prefix, year, value, config.padding, yearly=config.yearly_reset)


async def set_prefix(session: AsyncSession, doc_type: str, prefix: str) -> DocumentNumberConfig:
    prefix = prefix.strip().upper()
    if not prefix or not prefix.replace("_", "").isalnum() or len(prefix) > 16:
        raise AppError("Prefix must be 1-16 letters, digits or underscores", code="invalid_prefix")
    config = await session.get(DocumentNumberConfig, doc_type)
    if config is None:
        raise NotFoundError(f"Unknown document type {doc_type}", code="unknown_doc_type")
    config.prefix = prefix
    await session.flush()
    return config
