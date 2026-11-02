import hashlib
from pathlib import Path

import pytest
from ax_contracts import ChatAttachmentRef
from ax_integrations import AttachmentReadError, ChatAttachmentReader
from pydantic import ValidationError


def test_attachment_contract_accepts_50_mib_and_rejects_one_extra_byte(tmp_path):
    limit = 50 * 1024 * 1024
    assert _reference(tmp_path / "large.png", b"", byte_size=limit).byte_size == limit
    with pytest.raises(ValidationError):
        _reference(tmp_path / "large.png", b"", byte_size=limit + 1)


def _reference(
    path: Path,
    data: bytes,
    *,
    kind: str = "document",
    media_type: str = "text/plain",
    uri: str | None = None,
    byte_size: int | None = None,
    sha256: str | None = None,
) -> ChatAttachmentRef:
    return ChatAttachmentRef(
        attachment_id="upload_123",
        filename="notes.txt" if kind == "document" else "photo.png",
        kind=kind,
        media_type=media_type,
        uri=uri or path.as_uri(),
        byte_size=len(data) if byte_size is None else byte_size,
        sha256=sha256 or hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.asyncio
async def test_reader_builds_delimited_document_content(tmp_path: Path) -> None:
    data = b"quarterly facts\n"
    path = tmp_path / "normalized.txt"
    path.write_bytes(data)
    reference = _reference(path, data)

    content = await ChatAttachmentReader(tmp_path).build_user_content(
        "Summarize this",
        [reference],
        supports_vision=False,
    )

    assert content[0] == {"type": "text", "text": "Summarize this"}
    document_part = content[1]
    assert document_part["type"] == "text"
    assert "BEGIN UNTRUSTED ATTACHMENT" in document_part["text"]
    assert (
        'Original filename (untrusted JSON string): "notes.txt"'
        in document_part["text"]
    )
    assert "quarterly facts" in document_part["text"]
    assert reference.sha256 in document_part["text"]


@pytest.mark.asyncio
async def test_reader_builds_data_backed_image_only_with_vision(tmp_path: Path) -> None:
    data = b"normalized-image"
    path = tmp_path / "normalized.png"
    path.write_bytes(data)
    reference = _reference(
        path,
        data,
        kind="image",
        media_type="image/png",
    )
    reader = ChatAttachmentReader(tmp_path)

    with pytest.raises(AttachmentReadError) as exc_info:
        await reader.build_user_content(
            "Describe this",
            [reference],
            supports_vision=False,
        )
    assert exc_info.value.payload.code == "vision_not_supported"

    content = await reader.build_user_content(
        "Describe this",
        [reference],
        supports_vision=True,
    )
    assert content[1] == {
        "type": "text",
        "text": (
            'The next image has this untrusted original filename (JSON string): "photo.png"'
        ),
    }
    assert content[2] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,bm9ybWFsaXplZC1pbWFnZQ=="},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["outside", "traversal", "symlink"])
async def test_reader_rejects_unsafe_paths(tmp_path: Path, failure: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    if failure == "outside":
        uri = outside.as_uri()
    elif failure == "traversal":
        uri = f"file://{root}/../outside.txt"
    else:
        link = root / "link.txt"
        link.symlink_to(outside)
        uri = link.as_uri()
    reference = _reference(outside, b"secret", uri=uri)

    with pytest.raises(AttachmentReadError) as exc_info:
        await ChatAttachmentReader(root).build_user_content(
            "Read this",
            [reference],
            supports_vision=False,
        )

    assert exc_info.value.payload.code == "attachment_invalid"
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("byte_size", "sha256", "expected_code"),
    [
        (4, None, "attachment_integrity_error"),
        (None, "0" * 64, "attachment_integrity_error"),
    ],
)
async def test_reader_checks_declared_size_and_checksum(
    tmp_path: Path,
    byte_size: int | None,
    sha256: str | None,
    expected_code: str,
) -> None:
    data = b"facts"
    path = tmp_path / "normalized.txt"
    path.write_bytes(data)
    reference = _reference(
        path,
        data,
        byte_size=byte_size,
        sha256=sha256,
    )

    with pytest.raises(AttachmentReadError) as exc_info:
        await ChatAttachmentReader(tmp_path).build_user_content(
            "Read this",
            [reference],
            supports_vision=False,
        )
    assert exc_info.value.payload.code == expected_code


def test_reader_requires_a_real_absolute_non_symlink_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    link = tmp_path / "root-link"
    link.symlink_to(root, target_is_directory=True)

    with pytest.raises(ValueError, match="absolute"):
        ChatAttachmentReader(Path("relative"))
    with pytest.raises(ValueError, match="symlink"):
        ChatAttachmentReader(link)
    with pytest.raises(ValueError, match="existing directory"):
        ChatAttachmentReader(tmp_path / "missing")
