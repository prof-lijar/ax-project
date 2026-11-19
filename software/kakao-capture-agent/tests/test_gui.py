from pathlib import Path

import pytest
from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QEvent

from app.automation.monitoring_service import MonitoringService
from app.config import load, save
from app.gui import main_window
from app.gui.settings_dialog import SettingsDialog
from app.models import State, Target, TargetUnavailable


@pytest.mark.parametrize(
    "reply_command", ["send_test", "test_workflow", "bizgo_test", "incoming_test", "auto_catch"]
)
def test_full_window_preview_and_settings(
    tmp_path, config, queue, frame, region, monkeypatch, qt_app, reply_command
):
    from app.capture.screen_capture import encode_png
    from app.gui.main_window import MainWindow, Signals
    from tests.test_automation import Capture, Desktop

    app = qt_app

    class Hotkey(QAbstractNativeEventFilter):
        registered = True

        def nativeEventFilter(self, event_type, message):
            return False, 0

        def close(self):
            pass

    monkeypatch.setattr(main_window, "EmergencyHotkey", lambda callback: Hotkey())
    signals = Signals()
    desktop = Desktop(region)
    monitor = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        signals.status.emit,
        signals.preview.emit,
        signals.activity.emit,
    )

    class Uploader:
        def is_alive(self):
            return False

    window = MainWindow(
        config, tmp_path / "config.json", desktop, monitor, Uploader(), queue, signals
    )
    window.show()
    assert all(button.text() != "Select Region" for button in window.setup_buttons)
    window.test_reply_edit.setPlainText("테스트 메시지\nDifferent reply")
    signals.preview.emit(encode_png(frame))
    signals.stats.emit(queue.stats())
    app.processEvents()
    assert window.preview_label.pixmap() is not None
    assert "Pending: 0" in window.queue_label.text()
    assert str(queue.images) in window.capture_folder_label.text()
    opened = []
    monkeypatch.setattr(
        main_window.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    window.open_captures_folder()
    assert Path(opened[0].toLocalFile()).resolve() == queue.images.resolve()
    window.update_status(State.LIVE_MONITORING.value, "")
    assert not window.save_local_button.isEnabled()
    assert window.send_test_button.isEnabled()
    window.update_status(State.STOPPED.value, "")
    assert window.save_local_button.isEnabled()
    assert window.send_test_button.isEnabled()
    config.target = Target(42, 1, "start", "kakao.exe", "chat", "test conversation")
    config.selection = None
    config.chat_id = ""
    config.llm_url = "https://llm.test/v1"
    config.llm_model = "vision"
    config.llm_supports_vision = True
    config.bizgo_sender = "01000000001"
    config.bizgo_recipient = "01000000002"
    if reply_command == "bizgo_test":
        config.target = config.selection = None
        config.chat_id = ""  # A standalone phone test does not require chat setup.
    if reply_command == "auto_catch":
        config.selection = None
        config.chat_id = ""  # Selecting a window suffices; worker creates the rest.
    if reply_command == "send_test":
        warnings = []
        monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *a: warnings.append(a))
        for invalid in ("", "x" * 2001):
            window.test_reply_edit.setPlainText(invalid)
            window.action("send_test")
            assert window.pending_action is None and monitor.commands.empty()
        assert len(warnings) == 2
        window.test_reply_edit.setPlainText("테스트 메시지\nDifferent reply")
    timers = []
    activation = []
    desktop.request_target_activation = lambda: activation.append(window.isMinimized()) or True
    monkeypatch.setattr(
        main_window.QTimer, "singleShot", lambda delay, action: timers.append(action)
    )
    monitor.state = State.LIVE_MONITORING
    monitor.want_live = True
    window.action(reply_command)
    if reply_command == "send_test":
        assert config.test_reply_text == "테스트 메시지\nDifferent reply"
        assert load(tmp_path / "config.json").test_reply_text == config.test_reply_text
        assert not window.test_reply_edit.isEnabled()
    window.action(reply_command)
    assert len(timers) == 1 and not window.send_test_button.isEnabled()
    assert not window.test_workflow_button.isEnabled()
    assert not window.bizgo_test_button.isEnabled()
    assert not window.auto_catch_button.isEnabled()
    assert activation == ([] if reply_command == "bizgo_test" else [False])
    assert monitor.stop_input.is_set() and not monitor.want_live
    window.action("stop")
    window.action(reply_command)
    assert len(timers) == 2
    timers[0]()  # The cancelled timer cannot dispatch a newly requested send early.
    assert monitor.commands.get_nowait() == "stop"
    assert monitor.commands.empty()
    timers[1]()
    assert monitor.commands.get_nowait() == reply_command
    assert monitor.commands.empty()

    def unavailable():
        raise TargetUnavailable("Target closed")

    if reply_command != "bizgo_test":
        desktop.request_target_activation = unavailable
        window.action(reply_command)
        assert window.pending_action is None
        assert window.send_test_button.isEnabled()
        assert window.test_workflow_button.isEnabled()
        assert len(timers) == 2
        assert monitor.commands.get_nowait() == "stop"  # Failed activation never queues a send.
        assert monitor.commands.empty()
    if reply_command == "auto_catch":
        monitor.state = State.AUTO_CATCHING
        window.update_status(State.AUTO_CATCHING.value, "watching")
        assert not window.auto_catch_button.isEnabled()
        window.action("auto_catch")
        assert len(timers) == 2
        monitor.state = State.STOPPED
        window.update_status(State.STOPPED.value, "")
    dialog = SettingsDialog(config, window)
    dialog.controls["chat_id"].setText("changed-chat")
    dialog.controls["local_only"].setChecked(True)
    dialog.controls["llm_model"].setText("changed-model")
    dialog.controls["auto_reply_suffix"].setText("(Auto reply)")
    dialog.controls["auto_catch_interval_seconds"].setValue(0.25)
    dialog.controls["bizgo_recipient"].setText("01000000003")
    dialog.controls["bizgo_enabled"].setChecked(True)
    dialog.controls["bizgo_sandbox"].setChecked(False)
    dialog.accept()
    assert dialog.result_config.chat_id == "changed-chat"
    assert config.chat_id != "changed-chat"
    save(tmp_path / "local-config.json", dialog.result_config)
    assert load(tmp_path / "local-config.json").local_only is True
    assert load(tmp_path / "local-config.json").llm_model == "changed-model"
    stored = load(tmp_path / "local-config.json")
    assert stored.bizgo_recipient == "01000000003" and stored.bizgo_enabled
    assert not stored.bizgo_sandbox
    assert stored.auto_reply_suffix == "(Auto reply)"
    assert stored.auto_catch_interval_seconds == 0.25
    window.closing = True
    window.close()
    app.removeNativeEventFilter(window.hotkey)
    dialog.deleteLater()
    window.deleteLater()
    signals.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
