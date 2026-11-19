"""Conservative Windows desktop validation and input to the verified target."""

import ctypes
import threading
import time
from ctypes import wintypes
from pathlib import Path

from app.models import (
    AgentError,
    Cancelled,
    ForegroundLost,
    Region,
    ReselectionRequired,
    Selection,
    Target,
    TargetUnavailable,
)


def enable_dpi_awareness():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    # Must precede Qt, MSS and PyAutoGUI initialization. Manifest sets the same context.
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


class WindowsDesktop:
    def __init__(self, config):
        import win32api
        import win32con
        import win32gui
        import win32process

        self.api, self.con, self.gui, self.process = win32api, win32con, win32gui, win32process
        self.config = config
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user.GetDpiForWindow.restype = wintypes.UINT
        self.user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.user.OpenInputDesktop.restype = wintypes.HANDLE
        self.user.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.user.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]

    def identify(self, hwnd):
        _, pid = self.process.GetWindowThreadProcessId(hwnd)
        handle = self.api.OpenProcess(0x1000, False, pid)
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if not self.kernel.QueryFullProcessImageNameW(int(handle), 0, path, ctypes.byref(size)):
                raise TargetUnavailable("Cannot verify target executable")
            started = str(self.process.GetProcessTimes(handle)["CreationTime"])
            return Target(
                hwnd,
                pid,
                started,
                str(Path(path.value)),
                self.gui.GetClassName(hwnd),
                self.gui.GetWindowText(hwnd),
            )
        finally:
            handle.Close()

    def candidates(self):
        result = []

        def visit(hwnd, _):
            if self.gui.IsWindowVisible(hwnd) and self.gui.GetWindowText(hwnd):
                try:
                    result.append(self.identify(hwnd))
                except Exception:
                    pass

        self.gui.EnumWindows(visit, None)
        return sorted(
            result, key=lambda t: ("kakao" not in t.executable.lower(), t.executable.lower())
        )

    def monitors(self):
        result = []
        for _, _, rectangle in self.api.EnumDisplayMonitors():
            left, top, right, bottom = rectangle
            result.append(Region(left, top, right - left, bottom - top))
        return result

    def session_available(self):
        desktop = self.user.OpenInputDesktop(0, False, 0x0001)
        if not desktop:
            return False
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            if not self.user.GetUserObjectInformationW(
                desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed)
            ):
                return False
            if name.value.lower() != "default":
                return False
            import win32ts

            session = wintypes.DWORD()
            if not self.kernel.ProcessIdToSessionId(
                self.api.GetCurrentProcessId(), ctypes.byref(session)
            ):
                return False
            return (
                win32ts.WTSQuerySessionInformation(None, session.value, win32ts.WTSConnectState)
                == win32ts.WTSActive
            )
        except Exception:
            return False
        finally:
            self.user.CloseDesktop(desktop)

    def geometry(self):
        target = self.config.target
        if target is None:
            raise ReselectionRequired("Select and confirm the target conversation window")
        try:
            current = self.identify(target.hwnd)
        except Exception:
            raise ReselectionRequired(
                "Target closed or inaccessible; select the window again"
            ) from None
        if current != target:
            raise ReselectionRequired("Target identity or title changed; select the window again")
        if not self.gui.IsWindowVisible(target.hwnd) or self.gui.IsIconic(target.hwnd):
            raise TargetUnavailable("Target window is hidden or minimized")
        left, top, right, bottom = self.gui.GetClientRect(target.hwnd)
        x, y = self.gui.ClientToScreen(target.hwnd, (0, 0))
        return Region(x, y, right - left, bottom - top), self.user.GetDpiForWindow(target.hwnd)

    def validate(self):
        if not self.session_available():
            raise TargetUnavailable("Interactive desktop is locked or unavailable")
        client, dpi = self.geometry()
        if self.config.selection is None:
            raise ReselectionRequired("Restart the action to detect the conversation area")
        region = self.config.selection.resolve(client, dpi, self.monitors())
        hwnd = self.config.target.hwnd
        if self.gui.GetForegroundWindow() != hwnd:
            raise ForegroundLost("Bring the selected conversation to the foreground")
        # Walk every window ABOVE the target, including same-process dialogs.
        other = self.gui.GetWindow(hwnd, self.con.GW_HWNDPREV)
        while other:
            if self.gui.IsWindowVisible(other) and not self.gui.IsIconic(other):
                left, top, right, bottom = self.gui.GetWindowRect(other)
                if region.intersects(Region(left, top, right - left, bottom - top)):
                    raise TargetUnavailable("Another window overlaps the selected region")
            other = self.gui.GetWindow(other, self.con.GW_HWNDPREV)
        return region

    def suggest_chat_region(self):
        """Derive a capture area above one native composer without capturing or clicking."""
        if not self.session_available():
            raise TargetUnavailable("Interactive desktop is locked or unavailable")
        target = self.config.target
        client, dpi = self.geometry()
        composers = []

        def visit(handle, _):
            if not self.gui.IsChild(target.hwnd, handle):
                return
            name = self.gui.GetClassName(handle).lower()
            style = self.gui.GetWindowLong(handle, -16)
            if not (name == "edit" or name.startswith("richedit")):
                return
            if not style & 0x0004 or style & (0x0020 | 0x0800):
                return
            if not self.gui.IsWindowVisible(handle) or not self.gui.IsWindowEnabled(handle):
                return
            left, top, right, bottom = self.gui.GetWindowRect(handle)
            bounds = Region(left, top, right - left, bottom - top)
            if bounds.width >= 32 and bounds.height > 0 and client.contains(bounds):
                composers.append(bounds)

        self.gui.EnumChildWindows(target.hwnd, visit, None)
        if len(composers) != 1 or composers[0].top < client.top + client.height // 2:
            raise AgentError(
                "Cannot identify one message box below the conversation. "
                "Select the actual chat window and close search panels so its message box is visible."
            )
        region = Region(0, 0, client.width, composers[0].top - client.top)
        selection = Selection(region, client.width, client.height, dpi)
        selection.resolve(client, dpi, self.monitors())
        if self.config.target != target or self.geometry() != (client, dpi):
            raise ReselectionRequired("Chat moved or changed while detecting its message area")
        return selection

    def request_target_activation(self):
        """Request activation from the Send button while the agent owns foreground."""
        if not self.session_available():
            raise TargetUnavailable("Interactive desktop is locked or unavailable")
        self.geometry()  # Verify identity, process lifetime, visibility, and title first.
        hwnd = self.config.target.hwnd
        if self.gui.GetForegroundWindow() != hwnd:
            try:
                self.gui.SetForegroundWindow(hwnd)
            except Exception:
                return False
        return True  # Request issued; the worker verifies the actual foreground later.

    def _activate_with_input_queue(self, hwnd):
        """Temporarily share focus state; detach before waiting or sending input."""
        # AttachThreadInput resets key state. Do not use it while modifiers are held.
        if any(self.api.GetAsyncKeyState(key) & 0x8000 for key in (16, 17, 18, 91, 92)):
            return
        current = self.api.GetCurrentThreadId()
        foreground = self.gui.GetForegroundWindow()
        if not foreground:
            return
        threads = dict.fromkeys(
            self.process.GetWindowThreadProcessId(window)[0] for window in (foreground, hwnd)
        )
        attach = self.user.AttachThreadInput
        attach.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        attach.restype = wintypes.BOOL
        # Ensure this worker has a USER message queue before attaching it.
        self.gui.PeekMessage(None, 0, 0, 0)
        attached = []
        try:
            for thread in threads:
                if thread and thread != current:
                    if not attach(current, thread, True):
                        return
                    attached.append(thread)
            self.geometry()
            self.gui.BringWindowToTop(hwnd)
            self.gui.SetForegroundWindow(hwnd)
        finally:
            for thread in reversed(attached):
                attach(current, thread, False)

    def activate_target(self, cancel=None):
        """Bounded focus recovery for the exact target, including after an LLM wait."""
        cancel = cancel if cancel is not None else threading.Event()
        target = self.config.target
        deadline = time.monotonic() + 1.0
        fallback_at = time.monotonic() + 0.15
        requested = False
        attached_attempt = False
        while True:
            if cancel.is_set():
                raise Cancelled("Reply cancelled while activating the conversation")
            if self.config.target != target:
                raise ReselectionRequired("Target changed during activation; no reply sent")
            if not requested:
                self.request_target_activation()
                requested = True
            else:
                if not self.session_available():
                    raise TargetUnavailable("Interactive desktop is locked or unavailable")
                self.geometry()
            if self.gui.GetForegroundWindow() == target.hwnd:
                self.validate()
                return
            if not attached_attempt and time.monotonic() >= fallback_at:
                attached_attempt = True
                try:
                    self._activate_with_input_queue(target.hwnd)
                except (ReselectionRequired, TargetUnavailable):
                    raise
                except Exception:
                    pass  # A failed native focus request is verified below, never assumed.
            if time.monotonic() >= deadline:
                raise ForegroundLost(
                    "Windows did not allow activating the selected chat after focus recovery; no reply sent"
                )
            cancel.wait(0.05)

    def focus_reply_control(self, handle, cancel):
        """Click the verified edit control once; never guess message-box coordinates."""
        import pyautogui

        from app.models import AgentError, Cancelled

        def check():
            if cancel.is_set():
                raise Cancelled("Test reply cancelled")
            try:
                pyautogui.failSafeCheck()
            except pyautogui.FailSafeException:
                raise Cancelled("Mouse fail-safe activated; test reply stopped") from None
            self.validate()
            if not self.gui.IsChild(self.config.target.hwnd, handle):
                raise AgentError("Message box no longer belongs to the selected chat")

        check()
        left, top, right, bottom = self.gui.GetWindowRect(handle)
        point = ((left + right) // 2, (top + bottom) // 2)
        self.api.SetCursorPos(point)
        check()
        if self.gui.WindowFromPoint(point) != handle:
            raise AgentError("Message box is covered or changed; no reply sent")

        class MouseInput(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("mi", MouseInput)]

        events = (Input * 2)(
            Input(0, MouseInput(0, 0, 0, 0x0002, 0, 0)),  # LEFTDOWN
            Input(0, MouseInput(0, 0, 0, 0x0004, 0, 0)),  # LEFTUP
        )
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT
        check()
        if any(self.api.GetAsyncKeyState(key) & 0x8000 for key in (16, 17, 18, 91, 92)):
            raise AgentError("Release keyboard modifiers before sending; no reply sent")
        inserted = self.user.SendInput(2, events, ctypes.sizeof(Input))
        if inserted != 2:
            if inserted == 1:
                # Release a partially injected mouse press; never leave the button held.
                self.user.SendInput(1, ctypes.byref(events[1]), ctypes.sizeof(Input))
            raise AgentError("Windows rejected message-box focus; no reply sent")

    def scroll(self, direction, cancel):
        import pyautogui

        region = self.validate()
        if cancel.is_set():
            from app.models import Cancelled

            raise Cancelled("Scrolling stopped")
        # Win32 supports negative coordinates on secondary displays.
        try:
            pyautogui.failSafeCheck()
        except pyautogui.FailSafeException:
            cancel.set()
            from app.models import Cancelled

            raise Cancelled("Mouse fail-safe activated") from None
        self.api.SetCursorPos(region.center)
        self.validate()
        point_window = self.gui.WindowFromPoint(region.center)
        if point_window != self.config.target.hwnd and not self.gui.IsChild(
            self.config.target.hwnd, point_window
        ):
            raise TargetUnavailable("Pointer is not over the verified conversation")
        if cancel.is_set():
            from app.models import Cancelled

            raise Cancelled("Scrolling stopped")
        # Send a native WHEEL_DELTA (120). PyAutoGUI 0.9.54 passes raw wheel data
        # and suppresses some OS input errors; retain its fail-safe but verify SendInput.
        try:
            pyautogui.failSafeCheck()

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            class INPUT(ctypes.Structure):
                _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

            event = INPUT(0, MOUSEINPUT(0, 0, (direction * 120) & 0xFFFFFFFF, 0x0800, 0, 0))
            self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
            self.user.SendInput.restype = wintypes.UINT
            if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
                raise TargetUnavailable("Windows rejected wheel input; check target permissions")
        except pyautogui.FailSafeException:
            cancel.set()
            from app.models import Cancelled

            raise Cancelled("Mouse fail-safe activated") from None
        self.validate()

    def at_bottom(self):
        """Only trust a standard scrollbar on the child under the capture center."""
        region = self.validate()
        hwnd = self.gui.WindowFromPoint(region.center)
        if hwnd != self.config.target.hwnd and not self.gui.IsChild(self.config.target.hwnd, hwnd):
            return None

        class SCROLLINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("fMask", wintypes.UINT),
                ("nMin", ctypes.c_int),
                ("nMax", ctypes.c_int),
                ("nPage", wintypes.UINT),
                ("nPos", ctypes.c_int),
                ("nTrackPos", ctypes.c_int),
            ]

        info = SCROLLINFO()
        info.cbSize, info.fMask = ctypes.sizeof(info), 7
        self.user.GetScrollInfo.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.POINTER(SCROLLINFO)]
        if self.user.GetScrollInfo(hwnd, 1, ctypes.byref(info)) and info.nMax > info.nMin:
            return info.nPos >= info.nMax - max(info.nPage - 1, 0)
        return None
