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
    import win32api
    import win32con
    import win32gui

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
        )
        reader = WindowsChatText(desktop)
        try:
            result = reader.read(threading.Event())
        except AgentError:
            pytest.fail(f"Native text reader diagnostics: {reader.diagnostic}")
        assert "새 질문" in result.text and "PRIVATE DRAFT" not in result.text
        assert result.key and result.source.startswith("Windows")
    finally:
        if handles:
            win32gui.PostMessage(handles["parent"], win32con.WM_CLOSE, 0, 0)
        worker.join(3)
    assert not worker.is_alive()
