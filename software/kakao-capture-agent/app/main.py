"""Windows entry point; portable modules deliberately avoid importing desktop libraries."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if sys.platform != "win32":
        print(
            "The desktop application requires Windows 10/11. Portable tests and mock API run on Linux."
        )
        return 1
    from app.automation.window_manager import WindowsDesktop, enable_dpi_awareness
    from app.branding import set_windows_app_id

    set_windows_app_id()
    enable_dpi_awareness()
    if "--self-test" in sys.argv:
        from app.self_test import run

        position = sys.argv.index("--self-test")
        if position + 1 >= len(sys.argv):
            return 2
        return run(Path(sys.argv[position + 1]))
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.api.upload_worker import UploadWorker
    from app.automation.monitoring_service import MonitoringService
    from app.branding import configure_application
    from app.capture.screen_capture import ScreenCapture
    from app.config import data_directory, load, save
    from app.gui.main_window import MainWindow, Signals
    from app.storage.capture_queue import CaptureQueue
    from app.utils.logger import setup_logging
    from app.utils.windows import get_token, secure_directory, single_instance

    application = QApplication(sys.argv)
    try:
        configure_application(application)
        mutex = single_instance()
        root = data_directory()
        secure_directory(root)
        logger = setup_logging(root)
        config_path = root / "config.json"
        config = load(config_path)
        save(config_path, config)
        queue = CaptureQueue(root, config)
        desktop = WindowsDesktop(config)
        signals = Signals()
        monitor = MonitoringService(
            desktop,
            ScreenCapture(desktop),
            queue,
            config,
            signals.status.emit,
            signals.preview.emit,
            signals.activity.emit,
            text_preview=signals.text_preview.emit,
            setup_ready=signals.setup_ready.emit,
            preview_chat=signals.preview_chat.emit,
            image_test_output=signals.image_test_output.emit,
            image_test_text=signals.image_test_text.emit,
        )
        uploader = UploadWorker(queue, config, get_token, signals.upload.emit)
        window = MainWindow(config, config_path, desktop, monitor, uploader, queue, signals)
    except Exception as error:
        QMessageBox.critical(
            None,
            "Startup failed",
            f"Cannot start ({type(error).__name__}). Check configuration, permissions, and whether another instance is running. No capture has started.",
        )
        return 1
    import threading

    def statistics():
        while not monitor.shutdown.wait(2):
            try:
                signals.stats.emit(queue.stats())
            except Exception:
                signals.stats.emit({"error": True})

    logger.info("Agent started")
    monitor.start()
    uploader.start()
    stats_thread = threading.Thread(target=statistics, name="queue-status", daemon=True)
    stats_thread.start()
    window.show()
    for message in queue.recovery_messages:
        signals.activity.emit(message)
    if "--startup" in sys.argv and config.auto_start_monitoring:
        QTimer.singleShot(1000, lambda: window.action("start"))
    code = application.exec()
    monitor.command("stop")
    monitor.shutdown.set()
    uploader.shutdown.set()
    monitor.join()
    uploader.join()
    stats_thread.join(timeout=3)
    logger.info("Agent stopped")
    mutex.Close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
