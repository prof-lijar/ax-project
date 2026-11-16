"""Real loopback HTTP with both workers; desktop images remain synthetic."""

import socket
import sqlite3
import threading
import time

import uvicorn

from app.api.upload_worker import UploadWorker
from app.automation.monitoring_service import MonitoringService
from app.models import State
from mock_api.server import create_app
from tests.test_automation import Capture, Desktop


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for worker state")


def test_live_capture_upload_retries_while_capture_is_paused(
    tmp_path, queue, config, frame, region
):
    config.capture_interval_seconds = 1
    config.auto_resume = False
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    config.api_url = f"http://127.0.0.1:{listener.getsockname()[1]}/api/v1/captures"
    app = create_app(tmp_path / "backend", "test-token", failures=1)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    server_thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    desktop = Desktop(region)
    desktop.at_bottom = lambda: True
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    failed_once = threading.Event()
    worker = UploadWorker(
        queue,
        config,
        lambda _: "test-token",
        lambda message: failed_once.set() if "retry scheduled" in message else None,
    )
    server_thread.start()
    try:
        wait_until(lambda: server.started)
        service.start()
        worker.start()
        service.command("start")
        assert failed_once.wait(5)
        desktop.valid = False
        wait_until(lambda: service.state == State.PAUSED)
        wait_until(lambda: queue.stats().get("uploaded", 0) == 1)
        assert service.state == State.PAUSED
        with sqlite3.connect(tmp_path / "backend/mock.db") as db:
            assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 1
        queue.maintain()
        assert not list(queue.images.glob("*.png"))
    finally:
        service.command("stop")
        service.shutdown.set()
        worker.shutdown.set()
        if service.ident:
            service.join(timeout=5)
        if worker.ident:
            worker.join(timeout=5)
        server.should_exit = True
        server_thread.join(timeout=5)
        listener.close()
    assert not service.is_alive() and not worker.is_alive() and not server_thread.is_alive()
