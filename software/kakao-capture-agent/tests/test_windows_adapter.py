import sys
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


def test_reply_activates_only_verified_selected_window(config):
    desktop = adapter(config)
    foreground = [99]
    activated = []
    desktop.gui.GetForegroundWindow = lambda: foreground[0]

    def activate(handle):
        activated.append(handle)
        foreground[0] = handle

    desktop.gui.SetForegroundWindow = activate
    desktop.activate_target()
    assert activated == [42]
    desktop.activate_target()
    assert activated == [42]
    desktop.session_available = lambda: False
    with pytest.raises(TargetUnavailable):
        desktop.activate_target()
    assert activated == [42]


def test_reply_activation_refuses_reused_handle_and_windows_denial(config):
    desktop = adapter(config)
    activated = []
    desktop.gui.SetForegroundWindow = activated.append
    desktop.gui.GetForegroundWindow = lambda: 99
    with pytest.raises(TargetUnavailable, match="did not allow"):
        desktop.activate_target()
    assert activated == [42]
    activated.clear()
    del desktop.geometry
    desktop.identify = lambda _: Target(42, 200, "other-start", "kakao.exe", "chat", "other chat")
    with pytest.raises(ReselectionRequired):
        desktop.activate_target()
    assert not activated


def test_reply_never_clicks_an_obscured_message_box(config, monkeypatch):
    import threading

    from app.models import AgentError, Cancelled

    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(failSafeCheck=lambda: None))
    desktop = adapter(config)
    desktop.gui.IsChild = lambda parent, child: parent == 42 and child == 43
    desktop.gui.GetWindowRect = lambda _: (-490, 150, -410, 200)
    desktop.gui.WindowFromPoint = lambda _: 99
    moves = []
    desktop.api = SimpleNamespace(SetCursorPos=moves.append)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        desktop.focus_reply_control(43, cancel)
    assert not moves
    cancel.clear()
    # No user32 object: reaching SendInput would fail this test instead of passing.
    with pytest.raises(AgentError, match="covered"):
        desktop.focus_reply_control(43, cancel)


@pytest.mark.parametrize("inserted", [0, 1, 2])
def test_reply_click_pair_and_partial_press_release(config, monkeypatch, inserted):
    import threading

    from app.models import AgentError

    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(failSafeCheck=lambda: None))
    desktop = adapter(config)
    desktop.gui.IsChild = lambda parent, child: parent == 42 and child == 43
    desktop.gui.GetWindowRect = lambda _: (-490, 150, -410, 200)
    desktop.gui.WindowFromPoint = lambda _: 43
    moves, inputs = [], []
    desktop.api = SimpleNamespace(SetCursorPos=moves.append, GetAsyncKeyState=lambda _: 0)

    class SendInput:
        def __call__(self, count, events, size):
            flags = [e.mi.dwFlags for e in events] if count == 2 else [events._obj.mi.dwFlags]
            inputs.append(flags)
            return inserted if count == 2 else 1

    desktop.user = SimpleNamespace(SendInput=SendInput())
    if inserted == 2:
        desktop.focus_reply_control(43, threading.Event())
    else:
        with pytest.raises(AgentError, match="rejected"):
            desktop.focus_reply_control(43, threading.Event())
    assert moves == [(-450, 175)]
    assert inputs == ([[2, 4], [4]] if inserted == 1 else [[2, 4]])


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows ACL APIs")
def test_private_data_directory_acl(tmp_path):
    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    from app.utils.windows import secure_directory

    folder = tmp_path / "private-data"
    secure_directory(folder)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    descriptor = win32security.GetNamedSecurityInfo(
        str(folder), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    acl = descriptor.GetSecurityDescriptorDacl()
    assert acl.GetAceCount() == 2
    entries = [acl.GetAce(index) for index in range(acl.GetAceCount())]
    assert {str(ace[2]) for ace in entries} == {str(user), str(system)}
    assert all(ace[1] == ntsecuritycon.FILE_ALL_ACCESS for ace in entries)
    assert all(ace[0][1] & 3 == 3 for ace in entries)
    (folder / "check.txt").write_text("synthetic data", encoding="utf-8")
