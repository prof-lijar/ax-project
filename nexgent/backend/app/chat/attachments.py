import asyncio
import math
import os
import shutil
import time
import unicodedata
import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile

from app.chat.config import ChatSettings
from app.chat.errors import ChatRequestError
from app.chat.models import ChatAttachmentRef

MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 100_000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_MEMBERS = 10_000
MAX_DECODED_IMAGE_PIXELS = 40_000_000
MAX_NORMALIZED_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_SIDE = 4096
READ_CHUNK_BYTES = 1024 * 1024

GENERIC_MEDIA_TYPES = {"", "application/octet-stream"}
DOCUMENT_MEDIA_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "application/csv", "text/plain"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
}
IMAGE_MEDIA_TYPES = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
}
CANONICAL_IMAGE_TYPES = {
    ".png": ("PNG", "image/png", ".png"),
    ".jpg": ("JPEG", "image/jpeg", ".jpg"),
    ".jpeg": ("JPEG", "image/jpeg", ".jpg"),
    ".webp": ("WEBP", "image/webp", ".webp"),
}


@dataclass(frozen=True, slots=True)
class ArtifactBatch:
    root: Path
    request_dir: Path | None
    attachments: tuple[ChatAttachmentRef, ...]

    async def cleanup(self) -> None:
        if self.request_dir is None:
            return
        _remove_request_directory(self.root, self.request_dir)


class AttachmentProcessor:
    def __init__(self, settings: ChatSettings) -> None:
        self._settings = settings

    async def process(self, uploads: list[UploadFile], *, keep_originals: bool = False) -> ArtifactBatch:
        if len(uploads) > MAX_FILES:
            raise ChatRequestError(
                "too_many_files",
                f"Attach no more than {MAX_FILES} files.",
                status_code=413,
            )
        if not uploads:
            return ArtifactBatch(
                root=self._settings.artifact_root,
                request_dir=None,
                attachments=(),
            )

        root = _ensure_artifact_root(self._settings.artifact_root)
        request_dir = root / str(uuid4())
        request_dir.mkdir(mode=0o700)
        _write_private_file(request_dir / ".ax-chat-upload", b"")

        references: list[ChatAttachmentRef] = []
        total_bytes = 0
        extracted_characters = 0
        try:
            for upload in uploads:
                filename = _safe_filename(upload.filename)
                extension = Path(filename).suffix.lower()
                media_type = (
                    (upload.content_type or "").split(";", 1)[0].strip().lower()
                )
                kind = _validate_declared_type(extension, media_type, filename)
                content = await _read_upload(upload, filename)
                total_bytes += len(content)
                if total_bytes > MAX_TOTAL_BYTES:
                    raise ChatRequestError(
                        "total_size_exceeded",
                        "The combined attachment size exceeds 25 MiB.",
                        status_code=413,
                        filename=filename,
                    )

                if kind == "document":
                    normalized, extracted_count = await asyncio.to_thread(
                        _normalize_document,
                        extension,
                        content,
                        filename,
                    )
                    extracted_characters += extracted_count
                    if extracted_characters > MAX_EXTRACTED_CHARACTERS:
                        raise ChatRequestError(
                            "extracted_text_too_large",
                            "The combined extracted document text exceeds 100,000 characters.",
                            status_code=413,
                            filename=filename,
                        )
                    normalized_media_type = "text/plain"
                    artifact_extension = ".txt"
                else:
                    (
                        normalized,
                        normalized_media_type,
                        artifact_extension,
                    ) = await asyncio.to_thread(
                        _normalize_image,
                        extension,
                        content,
                        filename,
                    )

                if len(normalized) > MAX_FILE_BYTES:
                    raise ChatRequestError(
                        "normalized_file_too_large",
                        "The normalized attachment exceeds 10 MiB.",
                        status_code=413,
                        filename=filename,
                    )

                attachment_id = str(uuid4())
                if keep_originals:
                    _write_private_file(request_dir / f"{attachment_id}.original", content)
                artifact_path = request_dir / f"{attachment_id}{artifact_extension}"
                _write_private_file(artifact_path, normalized)
                references.append(
                    ChatAttachmentRef(
                        attachment_id=attachment_id,
                        filename=filename,
                        kind=kind,
                        media_type=normalized_media_type,
                        uri=artifact_path.as_uri(),
                        byte_size=len(normalized),
                        sha256=sha256(normalized).hexdigest(),
                    )
                )
        except BaseException:
            _remove_request_directory(root, request_dir)
            raise
        finally:
            for upload in uploads:
                await upload.close()

        return ArtifactBatch(
            root=root,
            request_dir=request_dir,
            attachments=tuple(references),
        )


async def _read_upload(upload: UploadFile, filename: str) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise ChatRequestError(
                "file_too_large",
                "Each attachment must be 10 MiB or smaller.",
                status_code=413,
                filename=filename,
            )
        chunks.append(chunk)
    if size == 0:
        raise ChatRequestError(
            "empty_file",
            "Empty files cannot be attached.",
            filename=filename,
        )
    return b"".join(chunks)


def _safe_filename(raw_filename: str | None) -> str:
    if not raw_filename:
        raise ChatRequestError("missing_filename", "Every attachment needs a filename.")
    filename = raw_filename.replace("\\", "/").rsplit("/", 1)[-1]
    filename = unicodedata.normalize("NFC", filename)
    filename = "".join(
        character
        for character in filename
        if not unicodedata.category(character).startswith("C")
    ).strip()
    if filename in {"", ".", ".."}:
        raise ChatRequestError(
            "invalid_filename", "The attachment filename is invalid."
        )
    if len(filename) > 255:
        raise ChatRequestError(
            "invalid_filename",
            "Attachment filenames must be 255 characters or fewer.",
        )
    return filename


def _validate_declared_type(extension: str, media_type: str, filename: str) -> str:
    if extension in DOCUMENT_MEDIA_TYPES:
        expected = DOCUMENT_MEDIA_TYPES[extension]
        kind = "document"
    elif extension in IMAGE_MEDIA_TYPES:
        expected = IMAGE_MEDIA_TYPES[extension]
        kind = "image"
    else:
        raise ChatRequestError(
            "unsupported_file_type",
            "Supported files are PDF, TXT, Markdown, CSV, DOCX, PNG, JPEG, and WebP.",
            status_code=415,
            filename=filename,
        )
    if media_type not in expected | GENERIC_MEDIA_TYPES:
        raise ChatRequestError(
            "media_type_mismatch",
            "The attachment media type does not match its filename extension.",
            status_code=415,
            filename=filename,
        )
    return kind


def _normalize_document(
    extension: str, content: bytes, filename: str
) -> tuple[bytes, int]:
    if extension == ".pdf":
        text = _extract_pdf_text(content, filename)
    elif extension == ".docx":
        text = _extract_docx_text(content, filename)
    else:
        if b"\x00" in content:
            raise ChatRequestError(
                "malformed_document",
                "The text attachment contains binary data.",
                filename=filename,
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ChatRequestError(
                "invalid_text_encoding",
                "Text, Markdown, and CSV attachments must use UTF-8 encoding.",
                filename=filename,
            ) from exc
        if not text.strip():
            raise ChatRequestError(
                "empty_document",
                "The attachment does not contain readable text.",
                filename=filename,
            )
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized.encode("utf-8"), len(normalized)


def _extract_pdf_text(content: bytes, filename: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ChatRequestError(
            "attachment_processor_unavailable",
            "PDF processing is temporarily unavailable.",
            status_code=503,
            filename=filename,
        ) from exc
    if not content.startswith(b"%PDF-"):
        raise ChatRequestError(
            "signature_mismatch",
            "The PDF signature is invalid.",
            status_code=415,
            filename=filename,
        )
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ChatRequestError(
                "encrypted_pdf",
                "Encrypted PDFs are not supported.",
                status_code=415,
                filename=filename,
            )
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            if sum(map(len, pages)) > MAX_EXTRACTED_CHARACTERS:
                break
    except ChatRequestError:
        raise
    except Exception as exc:
        raise ChatRequestError(
            "malformed_pdf",
            "The PDF could not be read.",
            filename=filename,
        ) from exc
    text = "\n\n".join(pages).strip()
    if not text:
        raise ChatRequestError(
            "pdf_has_no_text",
            "The PDF has no embedded text. Attach page images instead.",
            status_code=415,
            filename=filename,
        )
    return text


def _extract_docx_text(content: bytes, filename: str) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ChatRequestError(
            "attachment_processor_unavailable",
            "DOCX processing is temporarily unavailable.",
            status_code=503,
            filename=filename,
        ) from exc
    if not content.startswith(b"PK"):
        raise ChatRequestError(
            "signature_mismatch",
            "The DOCX signature is invalid.",
            status_code=415,
            filename=filename,
        )
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            names = {member.filename for member in members}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ChatRequestError(
                    "signature_mismatch",
                    "The file is not a valid DOCX document.",
                    status_code=415,
                    filename=filename,
                )
            if (
                len(members) > MAX_DOCX_MEMBERS
                or sum(member.file_size for member in members)
                > MAX_DOCX_UNCOMPRESSED_BYTES
            ):
                raise ChatRequestError(
                    "document_expansion_too_large",
                    "The expanded DOCX document is too large.",
                    status_code=413,
                    filename=filename,
                )
            if any(member.flag_bits & 0x1 for member in members):
                raise ChatRequestError(
                    "encrypted_document",
                    "Encrypted DOCX documents are not supported.",
                    status_code=415,
                    filename=filename,
                )
        document = Document(BytesIO(content))
        blocks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells]
                if any(values):
                    blocks.append("\t".join(values))
    except ChatRequestError:
        raise
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise ChatRequestError(
            "malformed_docx",
            "The DOCX document could not be read.",
            filename=filename,
        ) from exc
    text = "\n".join(blocks).strip()
    if not text:
        raise ChatRequestError(
            "empty_document",
            "The DOCX document does not contain readable paragraphs or tables.",
            filename=filename,
        )
    return text


def _normalize_image(
    extension: str, content: bytes, filename: str
) -> tuple[bytes, str, str]:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise ChatRequestError(
            "attachment_processor_unavailable",
            "Image processing is temporarily unavailable.",
            status_code=503,
            filename=filename,
        ) from exc
    expected_format, media_type, artifact_extension = CANONICAL_IMAGE_TYPES[extension]
    _validate_image_signature(extension, content, filename)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as probe:
                if probe.format != expected_format:
                    raise ChatRequestError(
                        "signature_mismatch",
                        "The image content does not match its filename extension.",
                        status_code=415,
                        filename=filename,
                    )
                if probe.width * probe.height > MAX_DECODED_IMAGE_PIXELS:
                    raise ChatRequestError(
                        "image_dimensions_too_large",
                        "The image dimensions are too large to process safely.",
                        status_code=413,
                        filename=filename,
                    )
                if getattr(probe, "n_frames", 1) != 1:
                    raise ChatRequestError(
                        "animated_image_not_supported",
                        "Animated images are not supported.",
                        status_code=415,
                        filename=filename,
                    )
                probe.verify()

            with Image.open(BytesIO(content)) as source:
                source.load()
                normalized = ImageOps.exif_transpose(source)
                target_width, target_height = _bounded_dimensions(
                    normalized.width, normalized.height
                )
                if (target_width, target_height) != normalized.size:
                    normalized = normalized.resize(
                        (target_width, target_height), Image.Resampling.LANCZOS
                    )
                if expected_format == "JPEG":
                    normalized = normalized.convert("RGB")
                elif normalized.mode not in {"RGB", "RGBA", "L"}:
                    normalized = normalized.convert(
                        "RGBA" if "A" in normalized.getbands() else "RGB"
                    )

                output = BytesIO()
                if expected_format == "PNG":
                    normalized.save(output, format="PNG", optimize=True)
                elif expected_format == "JPEG":
                    normalized.save(output, format="JPEG", quality=90, optimize=True)
                else:
                    normalized.save(output, format="WEBP", quality=90, method=4)
    except ChatRequestError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ) as exc:
        raise ChatRequestError(
            "malformed_image",
            "The image could not be decoded safely.",
            filename=filename,
        ) from exc
    normalized_bytes = output.getvalue()
    if len(normalized_bytes) > MAX_FILE_BYTES:
        raise ChatRequestError(
            "normalized_image_too_large",
            "The normalized image exceeds 10 MiB.",
            status_code=413,
            filename=filename,
        )
    return normalized_bytes, media_type, artifact_extension


def _validate_image_signature(extension: str, content: bytes, filename: str) -> None:
    valid = False
    if extension == ".png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = content.startswith(b"\xff\xd8\xff")
    elif extension == ".webp":
        valid = (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    if not valid:
        raise ChatRequestError(
            "signature_mismatch",
            "The image signature does not match its filename extension.",
            status_code=415,
            filename=filename,
        )


def _bounded_dimensions(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, MAX_IMAGE_SIDE / width, MAX_IMAGE_SIDE / height)
    pixels = width * height
    if pixels * scale * scale > MAX_NORMALIZED_IMAGE_PIXELS:
        scale = math.sqrt(MAX_NORMALIZED_IMAGE_PIXELS / pixels)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _ensure_artifact_root(root: Path) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("AX_CHAT_ARTIFACT_ROOT must be a real directory")
    os.chmod(root, 0o700)
    return root.resolve()


def _write_private_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as target:
            target.write(content)
            target.flush()
    finally:
        os.close(descriptor)


def _remove_request_directory(root: Path, request_dir: Path) -> None:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_request = request_dir.resolve(strict=True)
    except FileNotFoundError:
        return
    if resolved_request.parent != resolved_root or request_dir.is_symlink():
        raise RuntimeError("Refusing to remove an unsafe attachment directory")
    shutil.rmtree(resolved_request)


def cleanup_stale_artifacts(root: Path, stale_after_seconds: int) -> int:
    resolved_root = _ensure_artifact_root(root)
    cutoff = time.time() - stale_after_seconds
    removed = 0
    for candidate in resolved_root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            UUID(candidate.name)
        except ValueError:
            continue
        marker = candidate / ".ax-chat-upload"
        try:
            marker_stat = marker.lstat()
        except FileNotFoundError:
            continue
        if marker.is_symlink() or not marker.is_file() or marker_stat.st_mtime > cutoff:
            continue
        _remove_request_directory(resolved_root, candidate)
        removed += 1
    return removed


def attachment_path_from_uri(uri: str) -> Path:
    """Test/support helper for reading a generated local artifact URI."""
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise ValueError("attachment URI is not a local file URI")
    return Path(unquote(parsed.path))
