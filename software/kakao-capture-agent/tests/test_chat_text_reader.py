import json
import os
import sys
import threading
from types import SimpleNamespace

import pytest

from app.automation import windows_chat_text
from app.automation.windows_chat_text import WindowsChatText
from app.models import AgentError, Cancelled, Region


@pytest.mark.parametrize("case", ["valid", "unsupported", "changed_target", "cancel"])
def test_bounded_helper_validates_target_and_never_uses_pixels(monkeypatch, case):
    target = SimpleNamespace(hwnd=42, pid=7)
    desktop = SimpleNamespace(
        config=SimpleNamespace(target=target), validate=lambda: Region(0, 0, 400, 500)
    )
    cancel, calls = threading.Event(), []

    class Process:
        alive = True

        def communicate(self, input=None, timeout=None):
            calls.append(input)
            if input:
                request = json.loads(input)
                assert request["hwnd"] == 42 and request["region"]["height"] == 500
            if case == "cancel" and self.alive:
                cancel.set()
                raise windows_chat_text.subprocess.TimeoutExpired("synthetic", 0.1)
            self.alive = False
            if case == "changed_target":
                desktop.config.target = SimpleNamespace(hwnd=99, pid=9)
            body = dict(
                ok=True, text="테스터: 안녕\r\n새 메시지", source="Windows TextPattern", key="42.1"
            )
            if case == "unsupported":
                body = dict(ok=False, reason="unsupported")
            return json.dumps(body).encode(), b""

        def poll(self):
            return None if self.alive else 0

        def kill(self):
            self.alive = False

    process = Process()
    monkeypatch.setattr(windows_chat_text, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setenv("SystemRoot", "C:/Windows")
    monkeypatch.setattr(windows_chat_text.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(windows_chat_text.subprocess, "Popen", lambda *a, **kw: process)
    reader = WindowsChatText(desktop)
    if case == "valid":
        result = reader.read(cancel)
        assert result.text == "테스터: 안녕\n새 메시지"
    else:
        with pytest.raises(Cancelled if case == "cancel" else AgentError):
            reader.read(cancel)
    assert not process.alive


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows accessibility provider")
def test_native_readonly_transcript_excludes_composer_and_reads_korean():
    import ctypes

    import win32api
    import win32con
    import win32gui
    import win32process

    ready, handles, errors = threading.Event(), {}, []

    def create_window():
        try:
            parent = win32gui.CreateWindowEx(
                0,
                "STATIC",
                "Synthetic UIA test",
                win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE,
                20,
                20,
                650,
                650,
                0,
                0,
                win32api.GetModuleHandle(None),
                None,
            )
            history = win32gui.CreateWindowEx(
                0,
                "EDIT",
                "테스터: 이전 메시지\r\n테스터: 새 질문",
                win32con.WS_CHILD
                | win32con.WS_VISIBLE
                | win32con.ES_MULTILINE
                | win32con.ES_READONLY
                | win32con.WS_VSCROLL,
                10,
                10,
                580,
                400,
                parent,
                0,
                win32api.GetModuleHandle(None),
                None,
            )
            composer = win32gui.CreateWindowEx(
                0,
                "EDIT",
                "PRIVATE DRAFT MUST NOT BE READ",
                win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.ES_MULTILINE,
                10,
                440,
                580,
                80,
                parent,
                0,
                win32api.GetModuleHandle(None),
                None,
            )
            handles.update(parent=parent, history=history, composer=composer)
            ready.set()
            while win32gui.IsWindow(parent):
                win32gui.PumpWaitingMessages()
                threading.Event().wait(0.01)
        except Exception as error:
            errors.append(error)
            ready.set()

    worker = threading.Thread(target=create_window)
    worker.start()
    assert ready.wait(3)
    try:
        assert not errors
        left, top, right, bottom = win32gui.GetWindowRect(handles["history"])
        desktop = SimpleNamespace(
            config=SimpleNamespace(target=SimpleNamespace(hwnd=handles["parent"], pid=os.getpid())),
            validate=lambda: Region(left, top, right - left, bottom - top),
            gui=win32gui,
            process=win32process,
            user=ctypes.WinDLL("user32", use_last_error=True),
        )
        reader = WindowsChatText(desktop)
        try:
            result = reader.read(threading.Event())
        except AgentError:
            pytest.fail(f"Native text reader diagnostics: {reader.diagnostic}")
        assert "새 질문" in result.text and "PRIVATE DRAFT" not in result.text
        assert result.key and result.source == "Windows read-only Edit text"
        # Some Windows hosts expose this editor only as a generic UIA pane. The
        # UIA path must either return the same safe text or explicitly report that.
        reader.native_text = lambda *args: None
        try:
            accessible = reader.read(threading.Event())
        except AgentError:
            assert reader.diagnostic.get("reason") == "unsupported", reader.diagnostic
        else:
            assert "새 질문" in accessible.text and "PRIVATE DRAFT" not in accessible.text
    finally:
        if handles:
            win32gui.PostMessage(handles["parent"], win32con.WM_CLOSE, 0, 0)
        worker.join(3)
    assert not worker.is_alive()


@pytest.mark.parametrize("allowed", [True, False])
def test_native_reader_never_reads_writable_or_foreign_controls(monkeypatch, allowed):
    import ctypes

    from app.automation.windows_composer import WindowsComposer

    calls = []
    region = Region(0, 0, 500, 500)
    target = SimpleNamespace(hwnd=42, pid=7)
    desktop = SimpleNamespace(
        config=SimpleNamespace(target=target),
        validate=lambda: region,
        gui=SimpleNamespace(
            EnumChildWindows=lambda parent, visit, arg: [visit(h, arg) for h in (43, 44, 45)],
            GetClassName=lambda h: "Edit",
            GetWindowLong=lambda h, index: 0x4 if h == 44 else 0x804,
            IsWindowVisible=lambda h: True,
            IsChild=lambda parent, h: True,
            GetWindowRect=lambda h: (0, 0, 500, 500),
        ),
        process=SimpleNamespace(
            GetWindowThreadProcessId=lambda h: (1, 7 if h == 44 or (h == 43 and allowed) else 99)
        ),
    )

    def message(self, handle, command, wparam=0, lparam=0):
        calls.append(handle)
        assert handle == 43
        if command == 0x000E:
            return 5
        text = ctypes.create_unicode_buffer("hello")
        ctypes.memmove(lparam, text, ctypes.sizeof(text))
        return 5

    monkeypatch.setattr(WindowsComposer, "message", message)
    result = WindowsChatText(desktop).native_text(region, target, threading.Event())
    if allowed:
        assert result.text == "hello" and calls == [43, 43]
    else:
        assert result is None and not calls
