"""Private durable originals; only per-run normalized copies reach Agent Server."""

import asyncio
import mimetypes
import os
import shutil
import stat
import time
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from app.chat.attachments import (
    MAX_EXTRACTED_CHARACTERS,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ArtifactBatch,
    AttachmentProcessor,
    _ensure_artifact_root,
    _write_private_file,
)
from app.chat.errors import ChatRequestError
from app.chat.models import ChatAttachmentRef


def durable_write(path, content):
    _write_private_file(path, content)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    for directory in (path.parent, path.parent.parent):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class FileVault:
    def __init__(self, settings):
        self.settings = settings
        self.root = Path(os.getenv("AX_CHAT_FILE_ROOT", "/tmp/nexgent-chat-files"))
        if not self.root.is_absolute():
            raise RuntimeError("AX_CHAT_FILE_ROOT must be absolute")

    def directory(self, ident):
        ident = str(UUID(ident))
        root = _ensure_artifact_root(self.root)
        directory = root / ident
        if directory.is_symlink():
            raise ChatRequestError(
                "attachment_unavailable",
                "This attachment is unavailable.",
                status_code=503,
            )
        return directory

    async def prepare(self, files):
        batch = await AttachmentProcessor(self.settings).process(
            files, keep_originals=True
        )
        prepared = []
        try:
            for ref in batch.attachments:
                directory = self.directory(ref.attachment_id)
                directory.mkdir(mode=0o700)
                original = (
                    batch.request_dir / f"{ref.attachment_id}.original"
                ).read_bytes()
                prepared.append(
                    {
                        "id": ref.attachment_id,
                        "name": ref.filename,
                        "size": len(original),
                        "type": mimetypes.guess_type(ref.filename)[0]
                        or "application/octet-stream",
                        "sha256": sha256(original).hexdigest(),
                        "normalized": ref.model_dump(mode="json", exclude={"uri"}),
                    }
                )
                await asyncio.to_thread(durable_write, directory / "original", original)
                normalized = Path(ref.uri.removeprefix("file://")).read_bytes()
                await asyncio.to_thread(
                    durable_write, directory / "normalized", normalized
                )
            return prepared
        except BaseException:
            for file in prepared:
                self.remove(file["id"])
            raise
        finally:
            await batch.cleanup()

    def read(self, file, kind="original"):
        path = self.directory(file["id"]) / kind
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError("not a regular file")
                data = handle.read(10 * 1024 * 1024 + 1)
            expected = file if kind == "original" else file["normalized"]
            size = expected.get("size", expected.get("byte_size"))
            if len(data) != size or sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError("checksum mismatch")
            return data
        except (OSError, ValueError):
            raise ChatRequestError(
                "attachment_unavailable",
                "This attachment is unavailable.",
                status_code=503,
            ) from None

    def validate(self, files):
        if len(files) > MAX_FILES or sum(f["size"] for f in files) > MAX_TOTAL_BYTES:
            raise ChatRequestError(
                "attachment_limit",
                "Select at most five files totaling 25 MiB.",
                status_code=413,
            )
        size, characters = 0, 0
        for file in files:
            data = self.read(file, "normalized")
            size += len(data)
            if file["normalized"]["kind"] == "document":
                characters += len(data.decode("utf-8"))
        if size > MAX_TOTAL_BYTES or characters > MAX_EXTRACTED_CHARACTERS:
            raise ChatRequestError(
                "attachment_limit",
                "The combined file content exceeds the chat limit.",
                status_code=413,
            )

    def stage(self, files):
        self.validate(files)
        if not files:
            return ArtifactBatch(self.settings.artifact_root, None, ())
        root = _ensure_artifact_root(self.settings.artifact_root)
        directory = root / str(uuid4())
        directory.mkdir(mode=0o700)
        _write_private_file(directory / ".ax-chat-upload", b"")
        try:
            refs = []
            for file in files:
                path = directory / file["id"]
                _write_private_file(path, self.read(file, "normalized"))
                refs.append(ChatAttachmentRef(**file["normalized"], uri=path.as_uri()))
            return ArtifactBatch(root, directory, tuple(refs))
        except BaseException:
            shutil.rmtree(directory)
            raise

    def remove(self, ident):
        directory = self.directory(ident)
        if directory.exists():
            shutil.rmtree(directory)

    def clean_orphans(self, store):
        root = _ensure_artifact_root(self.root)
        for path in root.iterdir():
            try:
                ident = str(UUID(path.name))
            except ValueError:
                continue
            if (
                not path.is_symlink()
                and path.is_dir()
                and path.stat().st_mtime < time.time() - 3600
                and not store.file_exists(ident)
            ):
                self.remove(ident)
