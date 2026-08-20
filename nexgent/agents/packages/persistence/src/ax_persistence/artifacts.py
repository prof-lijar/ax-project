"""Private atomic filesystem artifacts for resumable bulk jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4


class ArtifactStoreError(RuntimeError):
    """Safe bulk-artifact storage failure."""


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    uri: str
    sha256: str
    byte_size: int


class LocalBulkArtifactStore:
    """Job-scoped files with private permissions and atomic replacement."""

    def __init__(self, root: Path, *, minimum_free_bytes: int = 1_073_741_824) -> None:
        if not root.is_absolute():
            raise ValueError("bulk artifact root must be absolute")
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must not be negative")
        self.root = root
        self.minimum_free_bytes = minimum_free_bytes

    def prepare(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ArtifactStoreError("bulk artifact root is unavailable")
        self.root.chmod(0o700)

    def ensure_capacity(self) -> None:
        self.prepare()
        if shutil.disk_usage(self.root).free < self.minimum_free_bytes:
            raise ArtifactStoreError("bulk artifact storage has insufficient capacity")

    def write_json(
        self, job_id: UUID, relative_name: str, value: Any
    ) -> StoredArtifact:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return self.write_bytes(job_id, relative_name, payload)

    def write_text(
        self, job_id: UUID, relative_name: str, value: str
    ) -> StoredArtifact:
        return self.write_bytes(job_id, relative_name, value.encode("utf-8"))

    def write_bytes(
        self, job_id: UUID, relative_name: str, payload: bytes
    ) -> StoredArtifact:
        return self.write_file(
            job_id, relative_name, lambda stream: stream.write(payload)
        )

    def write_file(
        self,
        job_id: UUID,
        relative_name: str,
        writer: Callable[[BinaryIO], object],
    ) -> StoredArtifact:
        self.ensure_capacity()
        destination = self._path(job_id, relative_name, create_parent=True)
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            with temporary.open("xb") as stream:
                os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
                writer(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, ValueError) as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ArtifactStoreError("bulk artifact write failed") from exc
        return self.describe(destination)

    def read_json(self, uri: str) -> Any:
        try:
            return json.loads(self._uri_path(uri).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ArtifactStoreError("bulk JSON artifact is unavailable") from exc

    def read_verified_json(self, uri: str, expected_sha256: str) -> Any:
        path = self._uri_path(uri)
        if self.describe(path).sha256 != expected_sha256:
            raise ArtifactStoreError("bulk artifact checksum does not match")
        return self.read_json(uri)

    def read_text(self, uri: str) -> str:
        try:
            return self._uri_path(uri).read_text(encoding="utf-8")
        except (OSError, ValueError, UnicodeError) as exc:
            raise ArtifactStoreError("bulk text artifact is unavailable") from exc

    def local_path(self, uri: str) -> Path:
        return self._uri_path(uri)

    def describe(self, path: Path) -> StoredArtifact:
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
        except OSError as exc:
            raise ArtifactStoreError("bulk artifact is unavailable") from exc
        return StoredArtifact(path.as_uri(), digest.hexdigest(), size)

    def remove_job(self, job_id: UUID) -> None:
        directory = self._job_directory(job_id, create=False)
        if not directory.exists():
            return
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            raise ArtifactStoreError("bulk artifacts could not be removed") from exc

    def _uri_path(self, uri: str) -> Path:
        if not uri.startswith("file://"):
            raise ArtifactStoreError("bulk artifact URI is invalid")
        candidate = Path(uri.removeprefix("file://"))
        try:
            candidate.relative_to(self.root)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root.resolve(strict=True))
        except ValueError as exc:
            raise ArtifactStoreError(
                "bulk artifact is outside its storage root"
            ) from exc
        except OSError as exc:
            raise ArtifactStoreError("bulk artifact is unavailable") from exc
        if candidate.is_symlink() or not resolved.is_file():
            raise ArtifactStoreError("bulk artifact is unavailable")
        return resolved

    def _path(self, job_id: UUID, relative_name: str, *, create_parent: bool) -> Path:
        relative = Path(relative_name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ArtifactStoreError("bulk artifact name is invalid")
        directory = self._job_directory(job_id, create=True)
        path = directory.joinpath(relative)
        if create_parent:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            current = path.parent
            while current != self.root:
                if current.is_symlink():
                    raise ArtifactStoreError("bulk artifact directory is unsafe")
                current = current.parent
            path.parent.chmod(0o700)
        return path

    def _job_directory(self, job_id: UUID, *, create: bool) -> Path:
        self.prepare()
        directory = self.root / str(job_id)
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ArtifactStoreError("bulk job artifact directory is unsafe")
        return directory
