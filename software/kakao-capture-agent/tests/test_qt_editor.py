import os
import subprocess
import sys
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.automation import window_manager, windows_composer
from app.automation.qt_editor import qt_editor_session, uses_qt_editor
from app.automation.windows_composer import WindowsComposer, WindowsReplySender
from app.models import AgentError, Region, Target
from tests.test_windows_adapter import adapter


def qt_target(hwnd=42):
    return Target(hwnd, 100, "start", r"C:\Program Files\KakaoTalkUI.exe", "QWindow", "chat")


class Editor:
    key = "qt.input"

    def __init__(self, target):
        self.target = target
        self.region = Region(-490, 100, 280, 80)
        self.text = ""

    def locate(self):
        return self.region

    def refresh_bounds(self):
        return self.region

    def action(self, operation, text=None):
        if operation == "write":
            self.text = text
        return {"text": self.text}


def test_qt_capture_setup_uses_background_selected_window_bounds(config, monkeypatch):
    desktop = adapter(config)
    config.target = qt_target()
    editor = Editor(config.target)
    monkeypatch.setattr(window_manager, "qt_editor_session", lambda target: nullcontext(editor))
    desktop.gui.GetForegroundWindow = lambda: 999
    selection = desktop.suggest_chat_region()
    assert selection.region == Region(0, 0, 300, 100)
    editor.region = Region(-600, 100, 200, 40)
    with pytest.raises(AgentError, match="conversation area"):
        desktop.suggest_chat_region()


@pytest.mark.parametrize("require_capture", [True, False])
@pytest.mark.parametrize("changed_target", [True, False])
def test_qt_sender_scopes_reply_to_original_selected_chat(
    config, monkeypatch, require_capture, changed_target
):
    desktop = adapter(config)
    config.target = qt_target()
    editor = Editor(config.target)
    if not require_capture:
        config.selection = None
    desktop.api = SimpleNamespace(GetAsyncKeyState=lambda _: 0)
    desktop.user = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(failSafeCheck=lambda: None))
    monkeypatch.setattr(windows_composer, "qt_editor_session", lambda *args: nullcontext(editor))
    keys = []

    def press(user, check):
        if changed_target:
            config.target = qt_target(78)
        check()
        keys.append(editor.text)
        editor.text = ""

    monkeypatch.setattr(windows_composer, "press_enter", press)
    sender = WindowsReplySender(
        WindowsComposer(desktop, require_capture=require_capture),
        lambda *args: None,
        threading.Event(),
    )
    if changed_target:
        with pytest.raises(AgentError, match="changed"):
            sender.send("다른\n내용")
        assert not keys and not sender.composer_cleared
    else:
        sender.send("다른\n내용")
        assert keys == ["다른\n내용"] and sender.composer_cleared


def test_foreground_picker_checks_exact_titled_kakao_window(config):
    desktop = adapter(config)
    desktop.gui.IsWindowVisible = lambda _: True
    desktop.gui.IsIconic = lambda _: False
    desktop.identify = lambda hwnd: qt_target(hwnd)
    assert desktop.foreground_chat_target() == qt_target()
    desktop.identify = lambda hwnd: Target(hwnd, 100, "start", "other.exe", "other", "chat")
    with pytest.raises(AgentError, match="active window"):
        desktop.foreground_chat_target()


@pytest.mark.skipif(sys.platform != "win32", reason="Uses Windows UI Automation and Qt Quick")
@pytest.mark.parametrize("verify_write", [False, True], ids=["discovery", "write-readback"])
def test_windows_helper_with_real_windowless_qml_editor(tmp_path, verify_write):
    # A separate Qt event loop services UI Automation while the test queries it.
    (tmp_path / "TextObjectTextArea.qml").write_text(
        "import QtQuick\nTextEdit { property bool sampleEditor: true; "
        'Accessible.role: Accessible.EditableText; Accessible.name: "Synthetic input"; '
        "activeFocusOnTab: true; focus: true }",
        encoding="utf-8",
    )
    qml = tmp_path / "Chat.qml"
    qml.write_text(
        "import QtQuick\nWindow { visible: true; width: 300; height: 300; "
        "TextObjectTextArea { x: 10; y: 180; width: 280; height: 100 } }",
        encoding="utf-8",
    )
    ready = tmp_path / "hwnd"
    host = """
import os
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
app = QGuiApplication([])
engine = QQmlApplicationEngine()
engine.load(QUrl.fromLocalFile(sys.argv[1]))
window = engine.rootObjects()[0]
window.requestActivate()
def ready():
    file = Path(sys.argv[2])
    pending = file.with_suffix(".pending")
    pending.write_text(f"{int(window.winId())} {os.getpid()}")
    pending.replace(file)
QTimer.singleShot(600, ready)
stop = QTimer()
stop.timeout.connect(lambda: app.quit() if Path(sys.argv[2]).with_suffix(".stop").exists() else None)
stop.start(100)
QTimer.singleShot(30000, app.quit)
app.exec()
"""
    env = dict(os.environ, QT_QPA_PLATFORM="windows", QT_QUICK_BACKEND="software")
    with subprocess.Popen([sys.executable, "-c", host, str(qml), str(ready)], env=env) as child:
        try:
            import time

            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and child.poll() is None:
                if ready.is_file() and ready.read_text():
                    break
                time.sleep(0.05)
            # A Windows venv launcher may have a different PID from the Qt host.
            hwnd, pid = map(int, ready.read_text().split())
            target = Target(hwnd, pid, "synthetic", "KakaoTalkUI.exe", "", "")
            assert uses_qt_editor(target)
            with qt_editor_session(target) as editor:
                bounds = editor.locate()
                assert bounds.width >= 100 and bounds.height >= 40 and editor.key
                if not verify_write:
                    return
                import win32gui

                if win32gui.GetForegroundWindow() != hwnd:
                    # Locate already verified the element in a separate, real Qt window.
                    pytest.skip("CI desktop did not grant foreground for the additional write/read test")
                assert editor.refresh_bounds() == bounds
                editor.action("focus")
                editor.action("write", text="합성 테스트\nSecond line")
                assert editor.action("read")["text"] == "합성 테스트\nSecond line"
        finally:
            ready.with_suffix(".stop").touch()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
