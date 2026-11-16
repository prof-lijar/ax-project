import threading

import pytest

from app.automation.monitoring_service import MonitoringService
from app.automation.scroll_controller import ScrollController
from app.models import AgentError, Cancelled, State, TargetUnavailable


class Desktop:
    def __init__(self, region):
        self.region = region
        self.valid = True
        self.calls = []

    def validate(self):
        if not self.valid:
            raise TargetUnavailable("Target unavailable")
        return self.region

    def scroll(self, direction, cancel):
        self.validate()
        self.calls.append(direction)

    def at_bottom(self):
        self.validate()
        return None


class Capture:
    def __init__(self, desktop, frame):
        self.desktop, self.frame = desktop, frame

    def grab(self):
        return self.frame, self.desktop.validate()


def test_scroll_cancellation_sends_no_events(config, frame, region):
    desktop = Desktop(region)
    stop = threading.Event()
    stop.set()
    scroll = ScrollController(
        desktop, Capture(desktop, frame), config, stop, threading.Event(), lambda _: None
    )
    with pytest.raises(Cancelled):
        scroll.move(1)
    assert not desktop.calls


def test_invalid_target_sends_no_events(config, frame, region):
    desktop = Desktop(region)
    desktop.valid = False
    scroll = ScrollController(
        desktop,
        Capture(desktop, frame),
        config,
        threading.Event(),
        threading.Event(),
        lambda _: None,
    )
    with pytest.raises(TargetUnavailable):
        scroll.move(1)
    assert not desktop.calls


def test_stationary_image_alone_does_not_prove_bottom(config, frame, region, monkeypatch):
    desktop = Desktop(region)
    scroll = ScrollController(
        desktop,
        Capture(desktop, frame),
        config,
        threading.Event(),
        threading.Event(),
        lambda _: None,
    )
    monkeypatch.setattr(scroll, "settle", lambda *a: None)
    with pytest.raises(AgentError, match="uncalibrated"):
        scroll.restore()
    assert len(desktop.calls) == 3


def test_history_must_restore_before_resume(config, frame, region, queue, monkeypatch):
    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    service.state = State.LIVE_MONITORING
    service.stop_input.clear()
    monkeypatch.setattr(service.scroller, "settle", lambda *a: None)
    with pytest.raises(AgentError):
        service.history()
    assert service.state == State.RESTORING_POSITION
    assert queue.stats()["pending"] == 1


def test_stop_discards_queued_history_and_sets_cancellation(config, frame, region, queue):
    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    service.command("history")
    service.command("stop")
    assert service.stop_input.is_set()
    assert service.history_cancel.is_set()
    assert service.commands.get_nowait() == "stop"
    assert service.commands.empty()


def test_preview_interruption_cannot_auto_start_monitoring(config, frame, region, queue):
    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    desktop.valid = False
    with pytest.raises(TargetUnavailable):
        service.dispatch("preview")
    service.pause(TargetUnavailable("Focus lost"))
    assert not service.recoverable
    assert not service.want_live


def test_interrupted_history_records_incomplete_boundaries(
    config, frame, region, queue, monkeypatch
):
    import json

    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    service.state = State.LIVE_MONITORING
    service.stop_input.clear()

    def invalid(*a, **kw):
        raise TargetUnavailable("Target disappeared")

    monkeypatch.setattr(service.scroller, "move", invalid)
    with pytest.raises(TargetUnavailable):
        service.history()
    with queue.connect() as db:
        detail = json.loads(
            db.execute("SELECT detail FROM events WHERE kind='history'").fetchone()[0]
        )
    assert detail["outcome"] == "failed; coverage incomplete"
    assert detail["first_capture_id"]
    assert detail["steps"] == 0


def test_live_baseline_is_not_advanced_when_storage_fails(
    config, frame, region, queue, monkeypatch
):
    from app.models import StorageFull

    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )

    def full(*a, **kw):
        raise StorageFull("full")

    monkeypatch.setattr(queue, "enqueue", full)
    with pytest.raises(StorageFull):
        service.record(frame, region, "live")
    assert service.detector.baseline is None
