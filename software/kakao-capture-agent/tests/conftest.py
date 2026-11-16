import numpy as np
import pytest

from app.config import Config
from app.models import Region
from app.storage.capture_queue import CaptureQueue


@pytest.fixture
def config():
    return Config(
        chat_id="test-chat",
        api_url="http://127.0.0.1:8000/api/v1/captures",
        allow_local_http=True,
        debounce_seconds=0,
        max_debounce_seconds=1,
    )


@pytest.fixture
def queue(tmp_path, config):
    return CaptureQueue(tmp_path / "agent", config)


@pytest.fixture
def region():
    return Region(-100, 10, 80, 100)


@pytest.fixture
def frame():
    return np.random.default_rng(3).integers(0, 256, (100, 80, 3), dtype=np.uint8)


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    app.quit()
