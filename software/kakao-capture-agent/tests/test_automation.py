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


def test_manual_local_capture_saves_identical_frames_without_scrolling(
    config, frame, region, queue
):
    from app.capture.screen_capture import encode_png

    desktop = Desktop(region)
    messages = []
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        messages.append,
    )
    service.dispatch("save_local")
    service.dispatch("save_local")
    assert service.state == State.STOPPED
    assert service.stop_input.is_set()
    assert not service.want_live
    assert not desktop.calls
    assert service.detector.baseline is None
    files = list(queue.images.glob("*.png"))
    assert len(files) == 2
    assert all(path.read_bytes() == encode_png(frame) for path in files)
    assert queue.claim(config.api_url) is None
    assert any(str(files[0]) in message for message in messages)
    desktop.valid = False
    with pytest.raises(TargetUnavailable):
        service.dispatch("save_local")
    assert len(list(queue.images.glob("*.png"))) == 2


def test_focus_recovery_stays_quiet_until_target_is_ready(
    config, frame, region, queue, monkeypatch
):
    desktop = Desktop(region)
    desktop.valid = False
    statuses, previews = [], []
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *args: statuses.append(args),
        previews.append,
        lambda _: None,
    )
    service.state = State.LIVE_MONITORING
    service.want_live = True
    service.pause(TargetUnavailable("Target unavailable"))
    for _ in range(3):
        with pytest.raises(TargetUnavailable) as error:
            service.try_recover()
        service.pause(error.value)
        assert service.stop_input.is_set()
    assert statuses == [(State.PAUSED.value, "Target unavailable")]
    assert not previews and not desktop.calls
    assert queue.stats().get("pending", 0) == 0
    desktop.valid = True
    monkeypatch.setattr(service.scroller, "restore", lambda: "test bottom verified")
    service.try_recover()
    assert service.state == State.LIVE_MONITORING
    assert len(previews) == 1


def test_paused_recovery_reports_changed_reason_and_stops_for_reselection(
    config, frame, region, queue
):
    from app.models import ReselectionRequired

    desktop = Desktop(region)
    statuses = []
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *args: statuses.append(args),
        lambda _: None,
        lambda _: None,
    )
    service.state = State.LIVE_MONITORING
    service.want_live = True
    service.pause(TargetUnavailable("Focus lost"))
    service.pause(TargetUnavailable("Desktop locked"))
    service.pause(ReselectionRequired("Target closed"))
    assert len(statuses) == 3
    assert service.reason == "Target closed"
    assert not service.recoverable


def test_manual_action_reservation_prevents_recovery_during_countdown(config, frame, region, queue):
    desktop = Desktop(region)
    statuses = []
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *args: statuses.append(args),
        lambda _: None,
        lambda _: None,
    )
    service.state = State.LIVE_MONITORING
    service.want_live = True
    service.pause(TargetUnavailable("Focus lost"))
    service.suspend_recovery()
    service.try_recover()
    assert not service.recoverable and not service.want_live
    assert service.stop_input.is_set()
    assert statuses == [(State.PAUSED.value, "Focus lost")]
    assert not desktop.calls
