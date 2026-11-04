import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import acting_as
from app.core.errors import AppError
from app.core.files import object_path, store_file, verify_object, write_object

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fabtrack-test-image" * 50


async def test_store_file_content_addressed_with_metadata(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    ref = uuid.uuid4()
    uploader = uuid.uuid4()
    with acting_as(uploader):
        record = await store_file(
            db_session,
            tmp_path,
            JPEG_BYTES,
            original_name="../../etc/board photo.jpg",
            mime="image/jpeg",
            ref_type="qc_result",
            ref_id=ref,
        )
    sha = hashlib.sha256(JPEG_BYTES).hexdigest()
    assert record.sha256 == sha
    assert record.storage_path == f"objects/{sha[:2]}/{sha[2:4]}/{sha}"
    assert record.original_name == "board photo.jpg"  # path components stripped
    assert record.size_bytes == len(JPEG_BYTES)
    assert record.uploaded_by == uploader
    assert (record.ref_type, record.ref_id) == ("qc_result", ref)
    assert (tmp_path / record.storage_path).read_bytes() == JPEG_BYTES
    assert verify_object(tmp_path, record)


async def test_same_bytes_stored_once_two_records(db_session: AsyncSession, tmp_path: Path) -> None:
    a = await store_file(db_session, tmp_path, JPEG_BYTES, original_name="a.jpg", mime="image/jpeg")
    b = await store_file(db_session, tmp_path, JPEG_BYTES, original_name="b.jpg", mime="image/jpeg")
    assert a.id != b.id and a.storage_path == b.storage_path
    assert len(list((tmp_path / "objects").rglob("*"))) == 3  # two dirs + one file


async def test_empty_file_rejected(db_session: AsyncSession, tmp_path: Path) -> None:
    with pytest.raises(AppError):
        await store_file(db_session, tmp_path, b"", original_name="x", mime="text/plain")


async def test_tampered_object_detected(db_session: AsyncSession, tmp_path: Path) -> None:
    record = await store_file(
        db_session, tmp_path, JPEG_BYTES, original_name="a.jpg", mime="image/jpeg"
    )
    (tmp_path / record.storage_path).write_bytes(JPEG_BYTES + b"tampered")
    assert not verify_object(tmp_path, record)
    (tmp_path / record.storage_path).unlink()
    assert not verify_object(tmp_path, record)


def test_write_object_is_idempotent(tmp_path: Path) -> None:
    sha1, rel1 = write_object(tmp_path, b"abc")
    sha2, rel2 = write_object(tmp_path, b"abc")
    assert (sha1, rel1) == (sha2, rel2) == (hashlib.sha256(b"abc").hexdigest(), object_path(sha1))
    assert not list(tmp_path.rglob(".upload-*"))
