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


def test_focus_waits_for_delayed_activation(config):
    import threading

    desktop = adapter(config)
    foreground = [99]
    desktop.gui.GetForegroundWindow = lambda: foreground[0]
    desktop.gui.SetForegroundWindow = lambda _: None
    timer = threading.Timer(0.05, lambda: foreground.__setitem__(0, 42))
    timer.start()
    try:
        desktop.activate_target()
    finally:
        timer.join()
    assert desktop.validate()


def test_focus_cancellation_prevents_fallback(config):
    import threading

    from app.models import Cancelled

    desktop = adapter(config)
    cancel = threading.Event()
    attempts = []
    desktop.gui.GetForegroundWindow = lambda: 99
    desktop.gui.SetForegroundWindow = lambda _: cancel.set()
    desktop._activate_with_input_queue = attempts.append
    with pytest.raises(Cancelled):
        desktop.activate_target(cancel)
    assert not attempts


@pytest.mark.parametrize(
    "outcome", ["success", "attach_failure", "activation_error", "modifier", "retarget"]
)
def test_temporary_focus_queue_is_always_detached(config, outcome):
    desktop = adapter(config)
    calls = []
    desktop.api = SimpleNamespace(
        GetCurrentThreadId=lambda: 1,
        GetAsyncKeyState=lambda _: 0x8000 if outcome == "modifier" else 0,
    )
    desktop.gui.GetForegroundWindow = lambda: 99
    desktop.process = SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd: (2 if hwnd == 99 else 3, 100)
    )
    desktop.gui.PeekMessage = lambda *a: calls.append("queue")
    desktop.gui.BringWindowToTop = lambda hwnd: calls.append(("top", hwnd))

    def activate(hwnd):
        calls.append(("activate", hwnd))
        if outcome == "activation_error":
            raise RuntimeError("Denied")

    desktop.gui.SetForegroundWindow = activate

    class Attach:
        def __call__(self, source, destination, attach):
            calls.append((source, destination, attach))
            return not (outcome == "attach_failure" and destination == 3 and attach)

    desktop.user = SimpleNamespace(AttachThreadInput=Attach())
    if outcome == "retarget":

        def geometry():
            raise ReselectionRequired("Target changed")

        desktop.geometry = geometry
    if outcome in ("activation_error", "retarget"):
        with pytest.raises((RuntimeError, ReselectionRequired)):
            desktop._activate_with_input_queue(42)
    else:
        desktop._activate_with_input_queue(42)
    if outcome == "modifier":
        assert not calls
    elif outcome == "attach_failure":
        assert calls == ["queue", (1, 2, True), (1, 3, True), (1, 2, False)]
    else:
        assert calls[-2:] == [(1, 3, False), (1, 2, False)]
        assert (("activate", 42) in calls) == (outcome != "retarget")


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows USER APIs")
def test_native_focus_helper_apis_available(config):
    desktop = WindowsDesktop(config)
    # Create only this thread's queue; do not attach to or activate any real window.
    assert desktop.api.GetCurrentThreadId() > 0
    desktop.gui.PeekMessage(None, 0, 0, 0)
    assert desktop.user.AttachThreadInput


def region_adapter(config, editors):
    desktop = adapter(config)
    desktop.config.selection = None
    desktop.gui.IsChild = lambda parent, child: parent == 42 and child in editors
    desktop.gui.EnumChildWindows = lambda hwnd, visit, arg: [visit(h, arg) for h in editors]
    desktop.gui.GetClassName = lambda h: editors[h].get("name", "RichEdit50W")
    desktop.gui.GetWindowLong = lambda h, _: editors[h].get("style", 4)
    desktop.gui.IsWindowVisible = lambda h: editors[h].get("visible", True)
    desktop.gui.IsWindowEnabled = lambda h: editors[h].get("enabled", True)
    desktop.gui.GetWindowRect = lambda h: editors[h]["rect"]
    return desktop


def test_auto_region_uses_native_composer_and_physical_client_coordinates(config):
    desktop = region_adapter(
        config,
        {
            43: {"rect": (-490, 200, -210, 280)},
            44: {"rect": (-490, 10, -210, 40), "style": 0},  # Search box.
            45: {"rect": (-490, 50, -210, 195), "style": 4 | 0x800},  # Read-only history.
        },
    )
    selection = desktop.suggest_chat_region()
    assert selection == Selection(Region(0, 0, 300, 200), 300, 300, 144)
    assert selection.resolve(*desktop.geometry(), desktop.monitors()) == Region(-500, 0, 300, 200)
    assert config.selection is None  # Suggesting layout never changes config or sends input.


@pytest.mark.parametrize(
    "editors",
    [
        {},
        {43: {"rect": (-490, 200, -210, 280)}, 44: {"rect": (-490, 220, -210, 280)}},
        {43: {"rect": (-490, 200, -210, 280), "style": 4 | 0x20}},
        {43: {"rect": (-490, 200, -210, 280), "enabled": False}},
        {43: {"rect": (-490, 200, -210, 280), "visible": False}},
        {43: {"rect": (-490, 200, -210, 280), "name": "UnknownCustomControl"}},
        {43: {"rect": (-490, 10, -210, 70)}},
        {43: {"rect": (-510, 200, -210, 280)}},
    ],
)
def test_auto_region_refuses_ambiguous_or_unsupported_composers(config, editors):
    from app.models import AgentError

    desktop = region_adapter(config, editors)
    with pytest.raises(AgentError, match="Select Region"):
        desktop.suggest_chat_region()


def test_auto_region_refuses_locked_moved_and_offscreen_desktops(config):
    desktop = region_adapter(config, {43: {"rect": (-490, 200, -210, 280)}})
    desktop.session_available = lambda: False
    with pytest.raises(TargetUnavailable):
        desktop.suggest_chat_region()
    desktop.session_available = lambda: True
    desktop.monitors = lambda: [Region(0, 0, 1920, 1080)]
    with pytest.raises(ReselectionRequired):
        desktop.suggest_chat_region()
    desktop.monitors = lambda: [Region(-1920, 0, 3840, 1080)]
    geometry = iter([(Region(-500, 0, 300, 300), 144), (Region(-501, 0, 300, 300), 144)])
    desktop.geometry = lambda: next(geometry)
    with pytest.raises(ReselectionRequired, match="moved"):
        desktop.suggest_chat_region()
