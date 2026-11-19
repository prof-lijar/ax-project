"""Every chat entry point uses window-derived geometry, never a saved manual crop."""

from types import SimpleNamespace

import pytest

from app.automation.monitoring_service import MonitoringService
from app.config import load, save
from app.models import AgentError, Cancelled, Region, Selection, State, Target
from tests.test_automation import Capture, Desktop


@pytest.mark.parametrize(
    "command",
    [
        "start",
        "confirm_bottom",
        "preview",
        "save_local",
        "up",
        "down",
        "send_test",
        "test_workflow",
        "incoming_test",
        "auto_catch",
    ],
)
def test_all_chat_actions_refresh_old_region_and_generate_id(
    command, config, queue, frame, region, tmp_path
):
    config.target = Target(42, 1, "start", "kakao.exe", "chat", "Group")
    old = Selection(Region(4, 4, 32, 32), 100, 100, 144)
    config.selection, config.chat_id = old, ""
    config.test_reply_text = "다른 메시지\nCustom reply"
    desktop = Desktop(region)
    saved = tmp_path / "config.json"
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
        setup_ready=lambda: save(saved, config),
    )
    expected = desktop.suggest_chat_region()
    observed = []

    def ready(*args):
        assert config.selection == expected and config.selection != old
        assert config.chat_id.startswith("chat-")
        observed.append(args)
        return "prepared"

    service.reply_sender = SimpleNamespace(send=ready)
    service.test_workflow.run = ready
    service.incoming_workflow.arm = ready
    service.auto_catch.arm = ready
    service.scroller.restore = ready
    service.dispatch(command)
    assert config.selection == expected
    restored = load(saved)
    assert restored.selection == expected and restored.chat_id == config.chat_id
    assert restored.test_reply_text == "다른 메시지\nCustom reply"
    if command == "send_test":
        assert observed == [(config.test_reply_text,)]
    if command == "confirm_bottom":
        # History reuses the freshly detected area without another configuration step.
        config.max_scroll_steps = 1
        service.dispatch("history")
        assert service.state == State.LIVE_MONITORING


@pytest.mark.parametrize("failure", ["unsupported", "cancel", "target_changed"])
def test_setup_failure_cannot_capture_or_send(config, queue, region, failure):
    desktop = Desktop(region)
    original = config.selection
    calls = []
    service = MonitoringService(
        desktop,
        SimpleNamespace(grab=lambda: calls.append("capture")),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
        setup_ready=lambda: calls.append("saved"),
    )
    service.reply_sender = SimpleNamespace(send=lambda *a: calls.append("send"))

    def detect():
        if failure == "unsupported":
            raise AgentError("Unsupported composer")
        if failure == "cancel":
            service.stop_input.set()
        else:
            config.target = Target(99, 2, "new", "kakao.exe", "chat", "Other")
        return Selection(region, 300, 300, 96)

    desktop.suggest_chat_region = detect
    with pytest.raises(Cancelled if failure == "cancel" else AgentError):
        service.dispatch("send_test")
    assert calls == [] and config.selection == original
