"""Regression checks for 50 MiB uploads and durable original downloads."""
import asyncio
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.chat.attachments import MAX_FILE_BYTES, MAX_TOTAL_BYTES, _read_upload
from app.chat.errors import ChatRequestError
from app.chat.vault import FileVault


def test_upload_accepts_exactly_50_mib_and_rejects_one_more_byte():
    limit = 50 * 1024 * 1024
    assert MAX_FILE_BYTES == MAX_TOTAL_BYTES == limit
    data = b"x" * limit
    async def run():
        upload = UploadFile(file=BytesIO(data), filename="large.pdf")
        try:
            assert len(await _read_upload(upload, "large.pdf")) == limit
        finally:
            await upload.close()
        upload = UploadFile(file=BytesIO(data + b"x"), filename="large.pdf")
        try:
            with pytest.raises(ChatRequestError) as error:
                await _read_upload(upload, "large.pdf")
            assert error.value.status_code == 413
        finally:
            await upload.close()
    asyncio.run(run())


def test_saved_original_larger_than_old_limit_is_read_in_full(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_FILE_ROOT", str(tmp_path))
    vault = FileVault(None)
    ident = str(uuid4())
    directory = vault.directory(ident)
    directory.mkdir()
    data = b"x" * (11 * 1024 * 1024)
    (directory / "original").write_bytes(data)
    assert vault.read({"id": ident, "size": len(data), "sha256": sha256(data).hexdigest()}) == data
