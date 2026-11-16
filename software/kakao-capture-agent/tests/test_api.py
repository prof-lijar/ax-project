import asyncio
import json
import sqlite3
from datetime import datetime, timezone

import httpx
import pytest

from app.api.client import UploadError, retry_delay, upload
from app.api.upload_worker import UploadWorker
from app.capture.screen_capture import encode_png
from mock_api.server import create_app


def test_multipart_persistence_and_idempotency(tmp_path, queue, config, frame, region):
    queue.enqueue(encode_png(frame), region, "live")
    job = queue.claim(config.api_url)
    app = create_app(tmp_path / "server", "test-token")

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            await upload(client, job, "test-token")
            await upload(client, job, "test-token")
            with pytest.raises(UploadError) as error:
                await upload(client, job, "wrong-token")
            assert error.value.authentication

    asyncio.run(exercise())
    with sqlite3.connect(tmp_path / "server/mock.db") as db:
        assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 1
        assert (
            json.loads(db.execute("SELECT metadata FROM captures").fetchone()[0])["chat_id"]
            == config.chat_id
        )


@pytest.mark.parametrize(
    "status,retryable,authentication",
    [
        (429, True, False),
        (503, True, False),
        (401, False, True),
        (422, False, False),
        (302, False, False),
    ],
)
def test_http_failure_classification(
    queue, config, frame, region, status, retryable, authentication
):
    queue.enqueue(encode_png(frame), region, "live")
    job = queue.claim(config.api_url)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(status, headers={"Retry-After": "90"})
            )
        ) as client:
            with pytest.raises(UploadError) as error:
                await upload(client, job, "token")
            assert error.value.retryable == retryable
            assert error.value.authentication == authentication

    asyncio.run(exercise())


def test_failure_recovery_with_same_capture_id(tmp_path, queue, config, frame, region):
    queue.enqueue(encode_png(frame), region, "history")
    job = queue.claim(config.api_url)
    app = create_app(tmp_path / "server", "token", failures=1)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            with pytest.raises(UploadError) as error:
                await upload(client, job, "token")
            assert error.value.retryable
            await upload(client, job, "token")

    asyncio.run(exercise())


def test_bad_acknowledgement_and_timeout(queue, config, frame, region):
    queue.enqueue(encode_png(frame), region, "live")
    job = queue.claim(config.api_url)

    def timeout(request):
        raise httpx.ReadTimeout("private host data", request=request)

    async def exercise():
        for handler in (
            lambda r: httpx.Response(200, json={"status": "accepted", "capture_id": "wrong"}),
            timeout,
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(UploadError) as error:
                    await upload(client, job, "token")
                assert error.value.retryable
                assert "private" not in str(error.value)

    asyncio.run(exercise())


def test_retry_after_seconds_and_dates():
    assert retry_delay(1, "90", random_value=0) == 90
    assert (
        retry_delay(
            1,
            "Wed, 01 Jan 2025 00:01:00 GMT",
            now=datetime(2025, 1, 1, tzinfo=timezone.utc),
            random_value=0,
        )
        == 60
    )
    assert retry_delay(2, "invalid", random_value=0) == 4
    assert retry_delay(20, "-1", random_value=0) == 300


def test_upload_worker_exhausts_retries_without_losing_image(
    monkeypatch, queue, config, frame, region
):
    queue.enqueue(encode_png(frame), region, "live")
    config.max_retries = 1
    worker = UploadWorker(queue, config, lambda _: "token", lambda _: None)
    calls = []

    async def failure(client, job, token):
        calls.append(job["capture_id"])
        if len(calls) == 2:
            worker.shutdown.set()
        raise UploadError("Temporary failure", retryable=True)

    monkeypatch.setattr("app.api.upload_worker.upload", failure)
    monkeypatch.setattr("app.api.upload_worker.retry_delay", lambda *_: 0)
    asyncio.run(worker.process())
    assert len(calls) == 2 and len(set(calls)) == 1
    assert queue.stats()["failed"] == 1
    assert len(list(queue.images.glob("*.png"))) == 1


def test_corrupted_image_is_never_sent(queue, config, frame, region):
    from pathlib import Path

    queue.enqueue(encode_png(frame), region, "live")
    job = queue.claim(config.api_url)
    Path(job["image_path"]).write_bytes(b"corrupt")

    def handler(request):
        pytest.fail("Corrupt image reached HTTP transport")

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(UploadError, match="integrity"):
                await upload(client, job, "token")

    asyncio.run(exercise())
