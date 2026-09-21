import asyncio
import json
import time
from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from uuid import uuid4

import httpx
import pytest
from app.chat.agent_server import open_agent_stream
from app.chat.attachments import (
    _normalize_document,
    _normalize_image,
    attachment_path_from_uri,
    cleanup_stale_artifacts,
)
from app.chat.config import ChatSettings
from app.chat.errors import ChatRequestError
from app.chat.models import ChatAttachmentRef
from docx import Document
from PIL import Image
from pypdf import PdfWriter
from starlette.datastructures import Headers
from starlette.requests import Request


async def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    from conftest import authenticated_headers
    kwargs["headers"] = {**authenticated_headers(), **kwargs.get("headers", {})}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def _settings(root: Path, server_url: str = "http://agent-server") -> ChatSettings:
    return ChatSettings(
        agent_server_url=server_url,
        assistant_id="chat",
        artifact_root=root,
        stale_after_seconds=900,
        connect_timeout_seconds=1,
        write_timeout_seconds=1,
    )


class _FakeResponse:
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    async def aiter_raw(self):
        for chunk in self._chunks:
            yield chunk
        if self._error:
            raise self._error


class _FakeUpstream:
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self.response = _FakeResponse(chunks, error)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("DOCX paragraph")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "left"
    table.cell(0, 1).text = "right"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 8), "red").save(output, format=image_format)
    return output.getvalue()


def _upload(filename: str, content: bytes, content_type: str):
    from fastapi import UploadFile

    # UploadFile takes ownership and the processor closes it after consumption.
    file = SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115
    file.write(content)
    file.seek(0)
    return UploadFile(
        file,
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _pdf_with_text() -> bytes:
    stream = b"BT /F1 12 Tf 72 120 Td (PDF text) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(payload)


def test_chat_route_streams_and_cleans_normalized_attachments(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    captured = {}
    upstream = _FakeUpstream([b'event: custom\ndata: {"delta":"ok"}\n\n'])

    async def fake_open(prompt, attachments, settings):
        captured["prompt"] = prompt
        captured["attachments"] = attachments
        captured["contents"] = [
            attachment_path_from_uri(item.uri).read_bytes() for item in attachments
        ]
        return upstream

    import app.chat.router as chat_router_module

    monkeypatch.setattr(chat_router_module, "open_agent_stream", fake_open)
    from app.chat.router import stream_chat

    async def exercise():
        response = await stream_chat(
            Request({"type": "http", "method": "POST", "path": "/api/chat/stream"}),
            prompt="  summarize  ",
            files=[
                _upload("notes.md", b"# Heading\r\nbody", "text/markdown"),
                _upload("data.csv", b"a,b\n1,2", "text/csv"),
            ],
        )
        chunks = [chunk async for chunk in response.body_iterator]
        return response, b"".join(chunks)

    response, body = asyncio.run(exercise())

    assert response.status_code == 200
    assert body == b'event: custom\ndata: {"delta":"ok"}\n\n'
    assert captured["prompt"] == "summarize"
    assert [item.schema_version for item in captured["attachments"]] == ["1", "1"]
    assert captured["contents"] == [b"# Heading\nbody", b"a,b\n1,2"]
    assert upstream.closed is True
    assert list(tmp_path.iterdir()) == []


def test_chat_route_returns_stable_validation_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    from conftest import feature_app as create_app

    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "inspect"},
            files={"files": ("payload.exe", b"MZ", "application/octet-stream")},
        )
    )

    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "schema_version": "1",
            "code": "unsupported_file_type",
            "message": "Supported files are PDF, TXT, Markdown, CSV, DOCX, PNG, JPEG, and WebP.",
            "filename": "payload.exe",
        }
    }
    assert list(tmp_path.iterdir()) == []


def test_prompt_is_required():
    from conftest import feature_app as create_app

    response = asyncio.run(
        _request(create_app(), "POST", "/api/chat/stream", data={"prompt": " "})
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "prompt_required"


def test_file_count_and_size_limits_are_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    from conftest import feature_app as create_app

    too_many = [("files", (f"{index}.txt", b"x", "text/plain")) for index in range(6)]
    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "read"},
            files=too_many,
        )
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_many_files"

    import app.chat.attachments as attachment_module

    monkeypatch.setattr(attachment_module, "MAX_FILE_BYTES", 4)
    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "read"},
            files={"files": ("large.txt", b"12345", "text/plain")},
        )
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert list(tmp_path.iterdir()) == []


def test_combined_size_and_extracted_text_limits_are_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    import app.chat.attachments as attachment_module

    monkeypatch.setattr(attachment_module, "MAX_TOTAL_BYTES", 7)
    monkeypatch.setattr(attachment_module, "MAX_EXTRACTED_CHARACTERS", 5)
    from conftest import feature_app as create_app

    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "read"},
            files=[
                ("files", ("one.txt", b"1234", "text/plain")),
                ("files", ("two.txt", b"5678", "text/plain")),
            ],
        )
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "total_size_exceeded"

    monkeypatch.setattr(attachment_module, "MAX_TOTAL_BYTES", 100)
    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "read"},
            files=[
                ("files", ("one.txt", b"123", "text/plain")),
                ("files", ("two.txt", b"456", "text/plain")),
            ],
        )
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "extracted_text_too_large"
    assert list(tmp_path.iterdir()) == []


def test_document_normalization_accepts_supported_formats():
    cases = [
        (".txt", b"plain text", "plain text"),
        (".md", b"# markdown", "# markdown"),
        (".csv", b"a,b\n1,2", "a,b\n1,2"),
        (".pdf", _pdf_with_text(), "PDF text"),
        (".docx", _docx_bytes(), "DOCX paragraph\nleft\tright"),
    ]
    for extension, content, expected in cases:
        normalized, count = _normalize_document(extension, content, f"file{extension}")
        assert normalized.decode() == expected
        assert count == len(expected)


def test_images_are_validated_and_normalized_without_metadata():
    cases = [
        (".png", "PNG", "image/png"),
        (".jpg", "JPEG", "image/jpeg"),
        (".webp", "WEBP", "image/webp"),
    ]
    for extension, image_format, expected_media_type in cases:
        normalized, media_type, artifact_extension = _normalize_image(
            extension, _image_bytes(image_format), f"image{extension}"
        )
        with Image.open(BytesIO(normalized)) as image:
            assert image.size == (16, 8)
            assert image.getexif() == {}
        assert media_type == expected_media_type
        assert artifact_extension in {".png", ".jpg", ".webp"}


def test_rejects_mime_signature_encoding_encrypted_and_textless_pdf():
    with _raises_chat_error("signature_mismatch"):
        _normalize_image(".png", b"not-png", "bad.png")
    with _raises_chat_error("invalid_text_encoding"):
        _normalize_document(".txt", b"\xff", "bad.txt")

    encrypted = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(encrypted)
    with _raises_chat_error("encrypted_pdf"):
        _normalize_document(".pdf", encrypted.getvalue(), "secret.pdf")

    plain = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(plain)
    with _raises_chat_error("pdf_has_no_text"):
        _normalize_document(".pdf", plain.getvalue(), "scan.pdf")


class _raises_chat_error:
    def __init__(self, code: str) -> None:
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        assert isinstance(exception, ChatRequestError)
        assert exception.detail.code == self.code
        return True


def test_agent_server_payload_is_strict_and_requests_disconnect_cancellation(tmp_path):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=b"event: custom\ndata: {}\n\n",
        )

    attachment = ChatAttachmentRef(
        attachment_id=str(uuid4()),
        filename="notes.txt",
        kind="document",
        media_type="text/plain",
        uri=(tmp_path / "notes.txt").as_uri(),
        byte_size=4,
        sha256="0" * 64,
    )

    async def exercise():
        stream = await open_agent_stream(
            "hello",
            (attachment,),
            _settings(tmp_path, "http://agent-server"),
            transport=httpx.MockTransport(handler),
        )
        body = await stream.response.aread()
        await stream.close()
        return body

    assert asyncio.run(exercise()) == b"event: custom\ndata: {}\n\n"
    assert captured["payload"] == {
        "assistant_id": "chat",
        "input": {"message": "hello", "attachments": [attachment.model_dump()]},
        "stream_mode": ["custom"],
        "on_disconnect": "cancel",
    }


def test_text_only_agent_server_payload_omits_attachments(tmp_path):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=b'event: values\ndata: {"response":"done"}\n\n',
        )

    async def exercise():
        stream = await open_agent_stream(
            "hello",
            (),
            _settings(tmp_path, "http://agent-server"),
            transport=httpx.MockTransport(handler),
        )
        await stream.response.aread()
        await stream.close()

    asyncio.run(exercise())

    assert captured["payload"]["input"] == {"message": "hello"}
    assert captured["payload"]["stream_mode"] == ["custom", "values"]


def test_agent_server_failures_are_normalized(tmp_path):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"internal upstream detail")

    async def exercise():
        return await open_agent_stream(
            "hello",
            (),
            _settings(tmp_path),
            transport=httpx.MockTransport(handler),
        )

    try:
        asyncio.run(exercise())
    except ChatRequestError as error:
        assert error.detail.code == "agent_server_error"
        assert "upstream" not in error.detail.message
    else:
        raise AssertionError("expected a normalized Agent Server error")


def test_text_only_agent_server_payload_preserves_existing_input_shape(tmp_path):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=b"data: {}\n\n",
        )

    async def exercise():
        stream = await open_agent_stream(
            "hello",
            (),
            _settings(tmp_path),
            transport=httpx.MockTransport(handler),
        )
        await stream.close()

    asyncio.run(exercise())
    assert captured["payload"]["input"] == {"message": "hello"}


def test_stale_cleanup_removes_only_owned_expired_directories(tmp_path):
    stale = tmp_path / str(uuid4())
    stale.mkdir()
    marker = stale / ".ax-chat-upload"
    marker.write_bytes(b"")
    (stale / "artifact.txt").write_text("text")
    old = time.time() - 901
    marker.touch()
    import os

    os.utime(marker, (old, old))

    fresh = tmp_path / str(uuid4())
    fresh.mkdir()
    (fresh / ".ax-chat-upload").write_bytes(b"")
    unrelated = tmp_path / "keep-me"
    unrelated.mkdir()

    assert cleanup_stale_artifacts(tmp_path, 900) == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()


@pytest.mark.parametrize("with_attachment", [False, True])
def test_session_run_uses_thread_and_resets_transient_state(tmp_path, with_attachment):
    session_id = uuid4()
    captured = {}

    async def handler(request):
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, content=b""
        )

    attachments = ()
    if with_attachment:
        attachments = (
            ChatAttachmentRef(
                attachment_id=str(uuid4()),
                filename="notes.txt",
                kind="document",
                media_type="text/plain",
                uri=(tmp_path / "notes.txt").as_uri(),
                byte_size=4,
                sha256="0" * 64,
            ),
        )

    async def exercise():
        upstream = await open_agent_stream(
            "follow up",
            attachments,
            _settings(tmp_path),
            session_id=session_id,
            transport=httpx.MockTransport(handler),
        )
        await upstream.close()

    asyncio.run(exercise())
    assert captured["path"] == f"/threads/{session_id}/runs/stream"
    assert captured["payload"] == {
        "assistant_id": "chat",
        "input": {
            "message": "follow up",
            "attachments": [a.model_dump() for a in attachments],
            "response": "",
            "error": None,
        },
        "stream_mode": ["custom"],
        "on_disconnect": "cancel",
        "if_not_exists": "create",
        "multitask_strategy": "reject",
    }


def test_busy_session_returns_retryable_conflict(tmp_path):
    async def handler(request):
        return httpx.Response(409)

    async def exercise():
        with _raises_chat_error("chat_session_busy"):
            await open_agent_stream(
                "next",
                (),
                _settings(tmp_path),
                session_id=uuid4(),
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(exercise())


def test_route_validates_and_forwards_session_id(monkeypatch, tmp_path):
    import app.chat.router as chat_router
    from conftest import feature_app as create_app

    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path))
    session_id = uuid4()
    captured = []

    async def fake_open(prompt, attachments, settings, **kwargs):
        captured.append(kwargs["session_id"])
        return _FakeUpstream([b'event: custom\ndata: {"response_complete":"ok"}\n\n'])

    monkeypatch.setattr(chat_router, "open_agent_stream", fake_open)
    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "hello", "session_id": str(session_id)},
        )
    )
    assert response.status_code == 200
    assert captured == [session_id]
    response = asyncio.run(
        _request(
            create_app(),
            "POST",
            "/api/chat/stream",
            data={"prompt": "hello", "session_id": "../../other"},
        )
    )
    assert response.status_code == 422
    assert captured == [session_id]
