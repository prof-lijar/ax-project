from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QEvent

from app.automation.monitoring_service import MonitoringService
from app.gui import main_window
from app.gui.settings_dialog import SettingsDialog


def test_full_window_preview_and_settings(
    tmp_path, config, queue, frame, region, monkeypatch, qt_app
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
    signals.preview.emit(encode_png(frame))
    signals.stats.emit(queue.stats())
    app.processEvents()
    assert window.preview_label.pixmap() is not None
    assert "Pending: 0" in window.queue_label.text()
    dialog = SettingsDialog(config, window)
    dialog.controls["chat_id"].setText("changed-chat")
    dialog.accept()
    assert dialog.result_config.chat_id == "changed-chat"
    assert config.chat_id != "changed-chat"
    window.closing = True
    window.close()
    app.removeNativeEventFilter(window.hotkey)
    dialog.deleteLater()
    window.deleteLater()
    signals.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
