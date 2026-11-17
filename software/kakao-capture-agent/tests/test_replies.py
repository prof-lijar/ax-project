import sys
import threading
from types import SimpleNamespace

import pytest

from app.automation.reply_service import TEST_REPLY
from app.automation.reply_service import TestReplySender as ReplySender
from app.automation.windows_composer import WindowsComposer
from app.models import AgentError, Cancelled, Region, State, TargetUnavailable


class Composer:
    def __init__(self, text=""):
        self.handle = 10
        self.text = text
        self.writes = []
        self.submits = []

    def prepare(self, cancel):
        pass

    def focused(self):
        if self.handle is None:
            raise TargetUnavailable("Focus lost")
        return self.handle

    def read(self, handle):
        return self.text

    def write(self, handle, text):
        self.writes.append((handle, text))
        self.text = text

    def submit(self, handle):
        self.submits.append(handle)


def test_fixed_reply_exact_text_and_one_send():
    composer, events = Composer(), []
    sender = ReplySender(composer, lambda *a: events.append(a), threading.Event())
    result = sender.send()
    assert composer.writes == [(10, "[AI가 답장드렸습니다]")]
    assert composer.submits == [10]
    assert [e[0] for e in events] == ["reply_attempt", "reply_submitted"]
    assert "Verify" in result


@pytest.mark.parametrize("draft", ["existing private text", " ", "\n"])
def test_existing_draft_is_preserved(draft):
    composer = Composer(draft)
    with pytest.raises(AgentError, match="draft"):
        ReplySender(composer, lambda *a: None, threading.Event()).send()
    assert composer.text == draft
    assert not composer.writes and not composer.submits


@pytest.mark.parametrize("failure", ["focus", "other_control", "cancel", "modified_text"])
def test_interrupted_reply_never_presses_enter(failure):
    composer, cancel = Composer(), threading.Event()
    original = composer.write

    def write(handle, text):
        original(handle, text)
        if failure == "focus":
            composer.handle = None
        elif failure == "other_control":
            composer.handle = 99
        elif failure == "cancel":
            cancel.set()
        else:
            composer.text += "other text"

    composer.write = write
    with pytest.raises(AgentError):
        ReplySender(composer, lambda *a: None, cancel).send()
    assert not composer.submits


def test_cancel_before_reply_sends_no_input():
    composer, cancel = Composer(), threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        ReplySender(composer, lambda *a: None, cancel).send()
    assert not composer.writes and not composer.submits


def test_uncertain_send_is_not_retried_or_cleared():
    composer, calls = Composer(), []

    def uncertain(handle):
        calls.append(handle)
        raise AgentError("uncertain")

    composer.submit = uncertain
    with pytest.raises(AgentError):
        ReplySender(composer, lambda *a: None, threading.Event()).send()
    assert calls == [10]
    assert composer.text == TEST_REPLY


def test_audit_failure_prevents_sending():
    composer = Composer()

    def failed(*a):
        raise OSError("storage failure")

    with pytest.raises(OSError):
        ReplySender(composer, failed, threading.Event()).send()
    assert not composer.writes and not composer.submits


def test_prepare_automatically_activates_and_focuses_unique_composer(monkeypatch):
    actions = []
    desktop = SimpleNamespace(
        config=SimpleNamespace(target=SimpleNamespace(hwnd=42)),
        activate_target=lambda: actions.append("activate"),
        validate=lambda: Region(0, 0, 100, 100),
        focus_reply_control=lambda handle, cancel: actions.append(("focus", handle)),
        gui=SimpleNamespace(
            EnumChildWindows=lambda root, visit, data: [visit(43, data), visit(44, data)]
        ),
    )
    composer = WindowsComposer(desktop)

    def validate(handle, region):
        if handle == 44:
            raise AgentError("Not an editor")

    monkeypatch.setattr(composer, "validate_control", validate)
    monkeypatch.setattr(composer, "focused", lambda: 43)
    composer.prepare(threading.Event())
    assert actions == ["activate", ("focus", 43)]


@pytest.mark.parametrize("count", [0, 2])
def test_prepare_refuses_missing_or_ambiguous_composer(count, monkeypatch):
    clicks = []
    desktop = SimpleNamespace(
        config=SimpleNamespace(target=SimpleNamespace(hwnd=42)),
        activate_target=lambda: None,
        validate=lambda: Region(0, 0, 100, 100),
        focus_reply_control=lambda *a: clicks.append(a),
        gui=SimpleNamespace(
            EnumChildWindows=lambda root, visit, data: [visit(i, data) for i in range(count)]
        ),
    )
    composer = WindowsComposer(desktop)
    monkeypatch.setattr(composer, "validate_control", lambda *a: None)
    with pytest.raises(AgentError, match=f"Found {count}"):
        composer.prepare(threading.Event())
    assert not clicks


def test_preparation_failure_never_types_or_submits():
    composer = Composer()

    def denied(cancel):
        raise TargetUnavailable("Windows denied activation")

    composer.prepare = denied
    with pytest.raises(TargetUnavailable):
        ReplySender(composer, lambda *a: None, threading.Event()).send()
    assert not composer.writes and not composer.submits


def test_send_is_manual_stopped_only_and_failure_cannot_auto_resume(config, frame, region, queue):
    from app.automation.monitoring_service import MonitoringService
    from tests.test_automation import Capture, Desktop

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
    calls = []
    service.reply_sender = SimpleNamespace(send=lambda: calls.append(True) or "requested")
    service.state = State.LIVE_MONITORING
    service.dispatch("send_test")
    service.state = State.PAUSED
    service.dispatch("send_test")
    assert not calls
    service.state = State.STOPPED
    service.dispatch("send_test")
    assert calls == [True] and service.state == State.STOPPED
    assert service.stop_input.is_set() and not service.want_live

    def lost():
        raise TargetUnavailable("Focus lost")

    service.reply_sender.send = lost
    with pytest.raises(TargetUnavailable) as error:
        service.dispatch("send_test")
    service.pause(error.value)
    assert not service.recoverable and not service.want_live


@pytest.mark.parametrize(
    "name,style", [("Edit", 0), ("RichEdit50W", 4 | 0x800), ("Edit", 4 | 0x20), ("Button", 4)]
)
def test_composer_rejects_search_password_readonly_and_other_controls(name, style):
    desktop = SimpleNamespace(
        gui=SimpleNamespace(
            GetClassName=lambda _: name,
            GetWindowLong=lambda *_: style,
            IsWindowEnabled=lambda _: True,
            IsWindowVisible=lambda _: True,
        )
    )
    with pytest.raises(AgentError, match="[Uu]nsupported"):
        WindowsComposer(desktop).validate_control(10, Region(0, 0, 100, 100))


@pytest.mark.parametrize("capture", [Region(0, 0, 300, 300), Region(10, 260, 80, 32)])
def test_composer_is_independent_of_capture_rectangle(config, capture):
    from tests.test_windows_adapter import adapter

    desktop = adapter(config)
    desktop.gui.GetClassName = lambda _: "RichEdit50W"
    desktop.gui.GetWindowLong = lambda *_: 4
    desktop.gui.IsWindowEnabled = lambda _: True
    desktop.gui.IsWindowVisible = lambda _: True
    desktop.gui.GetWindowRect = lambda _: (-490, 150, -410, 200)
    WindowsComposer(desktop).validate_control(43, capture)


def test_zero_candidates_reports_control_reasons_without_reading_text(config):
    from tests.test_windows_adapter import adapter

    desktop = adapter(config)
    desktop.activate_target = lambda: None
    desktop.gui.EnumChildWindows = lambda root, visit, data: [visit(43, data), visit(44, data)]
    desktop.gui.GetClassName = lambda handle: "RichEdit50W" if handle == 43 else "CustomControl"
    desktop.gui.GetWindowLong = lambda handle, _: 0x804 if handle == 43 else 0
    messages = []
    composer = WindowsComposer(desktop, messages.append)
    with pytest.raises(AgentError, match="Found 0"):
        composer.prepare(threading.Event())
    assert any("class=RichEdit50W" in text and "read-only" in text for text in messages)
    assert any(
        "class=CustomControl" in text and "Unsupported control class" in text for text in messages
    )


def test_native_composer_focus_ownership_and_obstruction_guards(config, monkeypatch):
    from tests.test_windows_adapter import adapter

    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(failSafeCheck=lambda: None))
    desktop = adapter(config)
    desktop.process = SimpleNamespace(GetWindowThreadProcessId=lambda _: (7, 100))
    desktop.api = SimpleNamespace(GetAsyncKeyState=lambda _: 0)
    desktop.gui.IsChild = lambda parent, child: parent == 42 and child == 43
    desktop.gui.GetClassName = lambda _: "RichEdit50W"
    desktop.gui.GetWindowLong = lambda *_: 4
    desktop.gui.IsWindowEnabled = lambda _: True
    desktop.gui.IsWindowVisible = lambda _: True
    desktop.gui.IsIconic = lambda _: False
    desktop.gui.GetWindowRect = lambda _: (-490, 150, -410, 200)

    class ThreadInfo:
        focus = 43

        def __call__(self, thread, pointer):
            pointer._obj.hwndActive = 42
            pointer._obj.hwndFocus = self.focus
            return True

    info = ThreadInfo()
    desktop.user = SimpleNamespace(GetGUIThreadInfo=info)
    composer = WindowsComposer(desktop)
    assert composer.focused() == 43
    info.focus = 99
    with pytest.raises(AgentError, match="message box does not have focus"):
        composer.focused()
    info.focus = 43
    desktop.api.GetAsyncKeyState = lambda _: 0x8000
    with pytest.raises(AgentError, match="Release"):
        composer.focused()
    desktop.api.GetAsyncKeyState = lambda _: 0
    desktop.gui.GetWindow = lambda handle, _: 99 if handle == 42 else 0
    with pytest.raises(AgentError, match="overlaps the message box"):
        composer.focused()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires standard Win32 edit controls")
def test_native_unicode_text_and_targeted_enter(monkeypatch):
    """Only a synthetic hidden control receives window messages; no chat/global input."""
    import ctypes

    import win32con
    import win32gui

    parent = win32gui.CreateWindowEx(
        0, "STATIC", "synthetic reply test", 0, 0, 0, 200, 200, 0, 0, 0, None
    )
    child = win32gui.CreateWindowEx(
        0, "EDIT", "", win32con.WS_CHILD | win32con.ES_MULTILINE, 0, 0, 100, 100, parent, 0, 0, None
    )
    try:
        composer = WindowsComposer(
            SimpleNamespace(user=ctypes.WinDLL("user32", use_last_error=True))
        )
        monkeypatch.setattr(composer, "focused", lambda: child)
        received = []

        def procedure(hwnd, message, wparam, lparam):
            if message in (win32con.WM_KEYDOWN, win32con.WM_KEYUP):
                received.append((hwnd, message, wparam))
            return win32gui.CallWindowProc(original, hwnd, message, wparam, lparam)

        original = win32gui.SetWindowLong(child, win32con.GWL_WNDPROC, procedure)
        assert composer.read(child) == ""
        composer.write(child, TEST_REPLY)
        assert composer.read(child) == TEST_REPLY
        composer.submit(child)
        win32gui.PumpWaitingMessages()
        assert received == [(child, win32con.WM_KEYDOWN, 13), (child, win32con.WM_KEYUP, 13)]
    finally:
        win32gui.DestroyWindow(parent)
