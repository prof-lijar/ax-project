import ctypes
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QImage

from app import branding


def test_windows_icon_sizes_and_qt_loading(qt_app):
    branding.configure_application(qt_app)
    assert qt_app.applicationName() == "VoyagerI"
    assert qt_app.applicationDisplayName() == branding.WINDOW_TITLE
    icon = qt_app.windowIcon()
    data = (branding.ASSETS / "voyageri.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind) == (0, 1)
    sizes = set()
    for index in range(count):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + index * 16
        )
        width, height = width or 256, height or 256
        assert width == height and planes == 1 and bits == 32
        frame = QImage.fromData(data[offset : offset + length], "PNG")
        assert not frame.isNull() and frame.width() == width and frame.hasAlphaChannel()
        assert not icon.pixmap(width, height).isNull()
        sizes.add(width)
    assert {16, 20, 24, 32, 40, 48, 64, 96, 128, 256} == sizes


@pytest.mark.parametrize("result", [0, -2147467259])
def test_taskbar_id_uses_unicode_and_checks_hresult(monkeypatch, result):
    setter = Mock(return_value=result)
    monkeypatch.setattr(branding.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter)),
        raising=False,
    )
    if result < 0:
        with pytest.raises(OSError, match="taskbar identity"):
            branding.set_windows_app_id()
    else:
        branding.set_windows_app_id()
    setter.assert_called_once_with("Nextor.VoyagerI.Desktop")
    assert setter.argtypes == [ctypes.c_wchar_p]
    assert setter.restype == ctypes.c_int32
