import hashlib
import json

import pytest

from app.capture.screen_capture import encode_png
from app.models import StorageFull
from app.storage.capture_queue import CaptureQueue


def test_restart_recovers_inflight_and_keeps_destination(queue, frame, region, config):
    png = encode_png(frame)
    capture_id = queue.enqueue(png, region, "live")
    job = queue.claim(config.api_url)
    assert job["capture_id"] == capture_id
    assert job["image_hash"] == hashlib.sha256(png).hexdigest()
    assert json.loads(job["metadata"])["region"]["left"] == -100
    reopened = CaptureQueue(queue.root, config)
    assert reopened.stats()["pending"] == 1
    config.api_url = "https://different.example/api"
    assert reopened.claim(config.api_url) is None
    assert reopened.stats()["other_destination"] == 1


def test_upload_retention_never_deletes_failed_images(queue, frame, region, config):
    a = queue.enqueue(encode_png(frame), region, "live")
    b = queue.enqueue(encode_png(frame), region, "history")
    queue.acknowledge(a)
    queue.fail(b, "Test failure", 1)
    queue.maintain()
    assert not (queue.images / f"{a}.png").exists()
    assert (queue.images / f"{b}.png").exists()
    assert queue.stats()["failed"] == 1
    queue.retry_failed(config.api_url)
    assert queue.claim(config.api_url)["capture_id"] == b


def test_capacity_pauses_without_discarding(queue, frame, region, config):
    capture_id = queue.enqueue(encode_png(frame), region, "live")
    config.storage_limit_bytes = queue.usage() + 1
    with pytest.raises(StorageFull):
        queue.enqueue(encode_png(frame), region, "live")
    assert (queue.images / f"{capture_id}.png").exists()
    assert queue.stats()["pending"] == 1


def test_recovery_reports_missing_and_retains_orphan(queue, frame, region, config):
    capture_id = queue.enqueue(encode_png(frame), region, "live")
    (queue.images / f"{capture_id}.png").unlink()
    orphan = queue.images / "orphan.png"
    orphan.write_bytes(encode_png(frame))
    (queue.images / "unfinished.tmp").write_bytes(b"partial")
    recovered = CaptureQueue(queue.root, config)
    assert recovered.stats()["failed"] == 1
    assert orphan.exists()
    assert not (queue.images / "unfinished.tmp").exists()


def test_local_captures_require_explicit_binding(queue, frame, region, config):
    destination = config.api_url
    config.api_url = ""
    queue.enqueue(encode_png(frame), region, "live")
    config.api_url = destination
    assert queue.claim(destination) is None
    queue.bind_local(destination, True)
    assert queue.claim(destination) is not None


@pytest.mark.parametrize("manual", [False, True])
def test_local_save_survives_restart_and_stays_private_until_assigned(
    queue, config, frame, region, manual
):
    config.local_only = not manual
    png = encode_png(frame)
    capture_id = queue.enqueue(png, region, "live", local_only=manual)
    config.local_only = False
    reopened = CaptureQueue(queue.root, config)
    reopened.maintain()
    assert (reopened.images / f"{capture_id}.png").read_bytes() == png
    assert reopened.stats()["unassigned"] == 1
    assert reopened.claim(config.api_url) is None
    reopened.bind_local(config.api_url, config.allow_local_http)
    assert reopened.claim(config.api_url)["capture_id"] == capture_id


def test_failed_database_commit_keeps_recoverable_image(queue, frame, region, monkeypatch):
    from contextlib import contextmanager

    real = queue.connect

    @contextmanager
    def broken():
        with real() as db:
            yield db
            raise OSError("simulated failure")

    monkeypatch.setattr(queue, "maintain", lambda: None)
    monkeypatch.setattr(queue, "connect", broken)
    with pytest.raises(OSError):
        queue.enqueue(encode_png(frame), region, "live")
    assert len(list(queue.images.glob("*.png"))) == 1
    assert not list(queue.images.glob("*.tmp"))
