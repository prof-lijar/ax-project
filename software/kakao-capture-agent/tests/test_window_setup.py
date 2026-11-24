"""Capture actions refresh their geometry. Manual replies only need the selected editor."""

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

    def ready(*args):
        assert config.selection == expected and config.selection != old
        assert config.chat_id.startswith("chat-")
        return "prepared"

    service.test_workflow.run = ready
    service.incoming_workflow.arm = ready
    service.auto_catch.arm = ready
    service.scroller.restore = ready
    service.dispatch(command)
    assert config.selection == expected
    restored = load(saved)
    assert restored.selection == expected and restored.chat_id == config.chat_id
    assert restored.test_reply_text == "다른 메시지\nCustom reply"
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
    service.test_workflow.run = lambda: calls.append("send")

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
        service.dispatch("test_workflow")
    assert calls == [] and config.selection == original


@pytest.mark.parametrize("other_editor,disabled", [(False, False), (True, False), (True, True)])
def test_manual_reply_works_without_detectable_capture_area(
    config, queue, frame, region, monkeypatch, other_editor, disabled
):
    import ctypes
    import sys

    from tests.test_windows_adapter import region_adapter

    # An expanded native KakaoTalk composer starts above the middle of the chat.
    editors = {43: {"name": "RICHEDIT50W", "style": 0, "rect": (-490, 100, -220, 290)}}
    editors[43]["enabled"] = not disabled
    if other_editor:
        editors[44] = {"rect": (-490, 10, -220, 50)}
    desktop = region_adapter(config, editors)
    config.target = Target(42, 100, "start", r"C:\Kakao\KakaoTalk.exe", "chat", "Group")
    desktop.gui.GetParent = lambda _: 42
    desktop.gui.GetDlgCtrlID = lambda h: 1006 if h == 43 else 10
    desktop.process = SimpleNamespace(GetWindowThreadProcessId=lambda _: (7, 100))
    with pytest.raises(AgentError, match="Cannot identify one message box below"):
        desktop.suggest_chat_region()
    desktop.suggest_chat_region = lambda: pytest.fail("Manual reply requested capture geometry")
    desktop.gui.WindowFromPoint = lambda _: 43
    desktop.api = SimpleNamespace(SetCursorPos=lambda _: None, GetAsyncKeyState=lambda _: 0)
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(failSafeCheck=lambda: None))
    actions = []
    draft = ""

    class ThreadInfo:
        def __call__(self, thread, pointer):
            pointer._obj.hwndActive, pointer._obj.hwndFocus = 42, 43
            return True

    class SendInput:
        def __call__(self, count, events, size):
            nonlocal draft
            if events[0].type == 1:
                actions.append(("enter", draft))
                draft = ""
            else:
                actions.append(("click", 43))
            return count

    desktop.user = SimpleNamespace(GetGUIThreadInfo=ThreadInfo(), SendInput=SendInput())
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )

    def message(handle, code, wp=0, lp=0):
        nonlocal draft
        assert handle == 43
        if code == 0x00C2:
            draft = ctypes.wstring_at(lp)
        elif code == 0x000D:
            data = ctypes.create_unicode_buffer(draft)
            ctypes.memmove(lp, data, ctypes.sizeof(data))
        else:
            assert code == 0x00B1

    monkeypatch.setattr(service.manual_reply_sender.composer, "message", message)
    if disabled:
        with pytest.raises(AgentError, match="Found 0"):
            service.dispatch("send_test")
        assert not actions
        return
    service.dispatch("send_test")
    assert actions == [("click", 43), ("enter", config.test_reply_text)]
    assert service.manual_reply_sender.composer_cleared and config.selection is None
