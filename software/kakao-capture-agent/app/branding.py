"""VoyagerI identity and resources shared by source and packaged launches."""

import ctypes
import sys
from pathlib import Path

APP_NAME = "VoyagerI"
WINDOW_TITLE = APP_NAME
WINDOWS_APP_ID = "Nextor.VoyagerI.Desktop"
ASSETS = Path(__file__).resolve().parent / "assets"


def set_windows_app_id():
    """Give the running window its own taskbar identity before Qt creates UI."""
    if sys.platform != "win32":
        return
    setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_int32
    result = setter(WINDOWS_APP_ID)
    if result < 0:
        raise OSError(f"Could not set VoyagerI taskbar identity (HRESULT {result:#x})")


def application_icon():
    from PySide6.QtGui import QIcon

    icon = QIcon(str(ASSETS / "voyageri.ico"))
    if icon.isNull():
        raise RuntimeError("VoyagerI application icon is missing or unreadable")
    return icon


def configure_application(application):
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(WINDOW_TITLE)
    application.setWindowIcon(application_icon())
