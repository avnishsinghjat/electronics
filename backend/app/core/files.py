"""Content-addressed file store under DATA_DIR plus the ``files`` metadata table.

Bytes are stored once per SHA-256 at ``objects/ab/cd/<sha256>``; every upload gets
its own metadata row (who, what, which entity), so the same photo can be linked to
several records without duplicating storage.
"""

import hashlib
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.context import current_actor_id
from app.core.errors import AppError
from app.core.models import Base, BusinessMixin, JsonB, fk

CHUNK = 1024 * 1024


class StoredFile(BusinessMixin, Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_ref", "ref_type", "ref_id"),)

    sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(64))
    ref_id: Mapped[uuid.UUID | None]
    exif_json: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    captured_at: Mapped[datetime | None]


def object_path(sha256: str) -> str:
    return f"objects/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def write_object(data_dir: Path, content: bytes) -> tuple[str, str]:
    """Write bytes into the store (atomic, idempotent). Returns (sha256, relative path)."""
    sha = hashlib.sha256(content).hexdigest()
    rel = object_path(sha)
    target = data_dir / rel
    if target.exists():
        return sha, rel
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return sha, rel


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


async def store_file(
    session: AsyncSession,
    data_dir: Path,
    content: bytes,
    *,
    original_name: str,
    mime: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    captured_at: datetime | None = None,
    exif: dict[str, Any] | None = None,
) -> StoredFile:
    if not content:
        raise AppError("File is empty", code="empty_file")
    sha, rel = write_object(data_dir, content)
    record = StoredFile(
        sha256=sha,
        original_name=Path(original_name).name[:255] or "upload",
        mime=mime[:127],
        size_bytes=len(content),
        storage_path=rel,
        uploaded_by=current_actor_id.get(),
        ref_type=ref_type,
        ref_id=ref_id,
        captured_at=captured_at,
        exif_json=exif,
    )
    session.add(record)
    await session.flush()
    return record


def verify_object(data_dir: Path, record: StoredFile) -> bool:
    """True if the stored bytes still hash to the recorded SHA-256 (evidence integrity)."""
    path = data_dir / record.storage_path
    return path.is_file() and hash_file(path) == record.sha256
