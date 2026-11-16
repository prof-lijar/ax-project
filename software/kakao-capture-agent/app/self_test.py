"""Packaged Windows startup check using only synthetic images and temporary data."""

import json
import os
import tempfile
from pathlib import Path


def run(report_path):
    result = {"status": "failed"}
    try:
        # Exercise the real GUI/runtime imports without collecting screen pixels or sending input.
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        import mss
        import numpy as np
        import pyautogui
        import win32cred
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication

        from app.api.upload_worker import UploadWorker
        from app.automation.monitoring_service import MonitoringService
        from app.automation.window_manager import WindowsDesktop
        from app.capture.screen_capture import ScreenCapture, encode_png
        from app.config import Config, load, save
        from app.gui.main_window import MainWindow, Signals
        from app.models import Region
        from app.storage.capture_queue import CaptureQueue
        from app.utils.windows import secure_directory

        application = QApplication([])
        with tempfile.TemporaryDirectory(prefix="kakao-self-test-") as temporary:
            root = Path(temporary)
            secure_directory(root)
            config = Config(chat_id="synthetic-self-test")
            save(root / "config.json", config)
            assert load(root / "config.json") == config
            queue = CaptureQueue(root, config)
            png = encode_png(np.zeros((64, 64, 3), dtype=np.uint8))
            capture_id = queue.enqueue(png, Region(0, 0, 64, 64), "live")
            assert queue.stats()["pending"] == 1
            queue.acknowledge(capture_id)
            queue.maintain()
            assert not list(queue.images.glob("*.png"))
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
            )
            uploader = UploadWorker(queue, config, lambda _: "", signals.upload.emit)
            window = MainWindow(
                config, root / "config.json", desktop, monitor, uploader, queue, signals
            )
            window.show()
            signals.preview.emit(png)
            application.processEvents()
            assert window.preview_label.pixmap() is not None
            window.closing = True
            window.close()
            window.deleteLater()
            signals.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            application.processEvents()
        application.quit()
        result = {
            "status": "passed",
            "checks": [
                "native imports",
                "restricted data directory",
                "configuration",
                "SQLite schema",
                "synthetic PNG",
                "retention",
                "Qt window and preview",
            ],
            "screen_capture_performed": False,
            "input_sent": False,
            "mss_available": bool(mss),
            "pyautogui_available": bool(pyautogui),
            "credential_api_available": bool(win32cred),
        }
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1
