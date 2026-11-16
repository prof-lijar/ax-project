from types import SimpleNamespace

import pytest

from app.automation.window_manager import WindowsDesktop
from app.models import Region, ReselectionRequired, Selection, Target, TargetUnavailable


def adapter(config):
    desktop = WindowsDesktop.__new__(WindowsDesktop)
    desktop.config = config
    config.target = Target(42, 100, "start", "kakao.exe", "chat", "authorized chat")
    config.selection = Selection(Region(10, 20, 80, 100), 300, 300, 144)
    desktop.session_available = lambda: True
    desktop.geometry = lambda: (Region(-500, 0, 300, 300), 144)
    desktop.monitors = lambda: [Region(-1920, 0, 3840, 1080)]
    desktop.con = SimpleNamespace(GW_HWNDPREV=3)
    desktop.gui = SimpleNamespace(GetForegroundWindow=lambda: 42, GetWindow=lambda *_: 0)
    return desktop


def test_native_guard_rejects_lock_foreground_and_small_obstruction(config):
    desktop = adapter(config)
    assert desktop.validate() == Region(-490, 20, 80, 100)
    desktop.session_available = lambda: False
    with pytest.raises(TargetUnavailable, match="desktop"):
        desktop.validate()
    desktop.session_available = lambda: True
    desktop.gui.GetForegroundWindow = lambda: 99
    with pytest.raises(TargetUnavailable, match="foreground"):
        desktop.validate()
    desktop.gui.GetForegroundWindow = lambda: 42
    desktop.gui.GetWindow = lambda *_: 99
    desktop.gui.IsWindowVisible = lambda _: True
    desktop.gui.IsIconic = lambda _: False
    desktop.gui.GetWindowRect = lambda _: (-485, 25, -484, 26)
    with pytest.raises(TargetUnavailable, match="overlaps"):
        desktop.validate()


def test_window_handle_reuse_requires_reselection(config):
    desktop = adapter(config)
    del desktop.geometry
    desktop.identify = lambda _: Target(
        42, 200, "other-start", "kakao.exe", "chat", "authorized chat"
    )
    with pytest.raises(ReselectionRequired):
        desktop.geometry()
