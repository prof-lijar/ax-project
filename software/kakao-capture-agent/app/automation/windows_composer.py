"""Targeted standard Win32 edit-control messages; no clipboard or global keystrokes."""

import ctypes
import time
from ctypes import wintypes

from app.models import AgentError, Cancelled, Region, covered_by_monitors


class WindowsComposer:
    def __init__(self, desktop, report=lambda _: None):
        self.desktop = desktop
        self.report = report

    def prepare(self, cancel):
        """Find one unambiguous composer in the selected window and focus it."""
        if cancel.is_set():
            raise Cancelled("Test reply cancelled")
        d = self.desktop
        self.report("Activating the selected conversation for the test reply")
        d.activate_target()
        region = d.validate()
        candidates = []

        def visit(handle, _):
            try:
                self.validate_control(handle, region)
            except AgentError:
                return
            candidates.append(handle)

        d.gui.EnumChildWindows(d.config.target.hwnd, visit, None)
        if len(candidates) != 1:
            raise AgentError(
                f"Found {len(candidates)} supported message boxes below the capture region. "
                "Keep the capture region above the composer and close search panels; no reply sent"
            )
        handle = candidates[0]
        if cancel.is_set():
            raise Cancelled("Test reply cancelled")
        self.validate_control(handle, d.validate())
        self.report("Message box identified; focusing it automatically")
        d.focus_reply_control(handle, cancel)
        deadline = time.monotonic() + 1
        while True:
            if cancel.is_set():
                raise Cancelled("Test reply cancelled")
            # Validate focus after the OS has processed the click, without sending another click.
            try:
                if self.focused() == handle:
                    return
            except Cancelled:
                raise
            except AgentError:
                if time.monotonic() >= deadline:
                    raise
            if time.monotonic() >= deadline:
                raise AgentError("Message-box focus did not settle; no reply sent")
            cancel.wait(0.05)

    def focused(self):
        import pyautogui

        try:
            pyautogui.failSafeCheck()
        except pyautogui.FailSafeException:
            raise Cancelled("Mouse fail-safe activated; test reply stopped") from None
        d = self.desktop
        capture_region = d.validate()
        target = d.config.target
        thread, pid = d.process.GetWindowThreadProcessId(target.hwnd)
        if pid != target.pid:
            raise AgentError("Target process changed; select the conversation again")

        class GUIThreadInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT),
            ]

        info = GUIThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        d.user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUIThreadInfo)]
        d.user.GetGUIThreadInfo.restype = wintypes.BOOL
        if not d.user.GetGUIThreadInfo(thread, ctypes.byref(info)):
            raise AgentError("Cannot verify message-box focus")
        handle = info.hwndFocus
        if info.hwndActive != target.hwnd or not handle or not d.gui.IsChild(target.hwnd, handle):
            raise AgentError("The selected chat's message box does not have focus; no reply sent")
        self.validate_control(handle, capture_region)
        # Check modifiers so Enter cannot become a newline/shortcut in the chat client.
        if any(d.api.GetAsyncKeyState(key) & 0x8000 for key in (16, 17, 18, 91, 92)):
            raise AgentError("Release Shift, Ctrl, Alt, and Windows keys before sending")
        return handle

    def validate_control(self, handle, capture_region):
        d = self.desktop
        name = d.gui.GetClassName(handle).lower()
        style = d.gui.GetWindowLong(handle, -16)  # GWL_STYLE
        if (
            not (name == "edit" or name.startswith("richedit"))
            or not style & 0x0004  # ES_MULTILINE: reject search fields/single-line edits
            or style & (0x0020 | 0x0800)  # ES_PASSWORD / ES_READONLY
            or not d.gui.IsWindowEnabled(handle)
            or not d.gui.IsWindowVisible(handle)
        ):
            raise AgentError(
                "Focused control is not a supported writable message box; nothing sent"
            )
        left, top, right, bottom = d.gui.GetWindowRect(handle)
        region = Region(left, top, right - left, bottom - top)
        client, _ = d.geometry()
        if (
            region.width <= 0
            or region.height <= 0
            or not client.contains(region)
            or top < capture_region.top + capture_region.height
            or not covered_by_monitors(region, d.monitors())
        ):
            raise AgentError("Message box must be visible below the selected capture region")
        other = d.gui.GetWindow(d.config.target.hwnd, d.con.GW_HWNDPREV)
        while other:
            if d.gui.IsWindowVisible(other) and not d.gui.IsIconic(other):
                x0, y0, x1, y1 = d.gui.GetWindowRect(other)
                if region.intersects(Region(x0, y0, x1 - x0, y1 - y0)):
                    raise AgentError("Another window overlaps the message box; nothing sent")
            other = d.gui.GetWindow(other, d.con.GW_HWNDPREV)

    def guard(self, handle):
        if self.focused() != handle:
            raise AgentError("Message-box focus changed; inspect the draft before trying again")

    def message(self, handle, message, wparam=0, lparam=0):
        user = self.desktop.user
        user.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        result = ctypes.c_size_t()
        # SMTO_BLOCK | SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT. Never wait indefinitely.
        if not user.SendMessageTimeoutW(
            handle, message, wparam, lparam, 0x23, 1000, ctypes.byref(result)
        ):
            raise AgentError("Message box did not respond; inspect the chat before trying again")
        return result.value

    def read(self, handle):
        self.guard(handle)
        text = ctypes.create_unicode_buffer(1024)
        self.message(handle, 0x000D, len(text), ctypes.addressof(text))  # WM_GETTEXT
        return text.value

    def write(self, handle, text):
        self.guard(handle)
        # Recheck immediately before replacing text; never erase a pre-existing draft.
        if self.read(handle):
            raise AgentError("Message box now contains a draft; nothing was overwritten")
        self.guard(handle)
        buffer = ctypes.create_unicode_buffer(text)
        if not self.message(handle, 0x000C, 0, ctypes.addressof(buffer)):  # WM_SETTEXT
            raise AgentError("Windows rejected the test text; Enter was not sent")

    def submit(self, handle):
        self.guard(handle)
        user = self.desktop.user
        user.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user.PostMessageW.restype = wintypes.BOOL
        # Target only the verified edit HWND, not whichever application gains focus next.
        if not user.PostMessageW(handle, 0x0100, 13, 0x001C0001):  # WM_KEYDOWN, Return
            raise AgentError("Windows rejected Enter; inspect the draft before trying again")
        if not user.PostMessageW(handle, 0x0101, 13, 0xC01C0001):  # WM_KEYUP, Return
            raise AgentError("Send result uncertain; inspect KakaoTalk before trying again")
