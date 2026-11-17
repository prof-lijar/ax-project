"""Targeted Win32 text edits followed by a guarded native Enter keypress."""

import ctypes
import time
from ctypes import wintypes

from app.automation.keyboard_input import press_enter
from app.models import AgentError, Cancelled, Region, covered_by_monitors


class WindowsComposer:
    def __init__(self, desktop, report=lambda _: None):
        self.desktop = desktop
        self.report = report
        self.cancel = None

    def prepare(self, cancel):
        """Find one unambiguous composer in the selected window and focus it."""
        self.cancel = cancel
        if cancel.is_set():
            raise Cancelled("Test reply cancelled")
        d = self.desktop
        self.report("Activating the selected conversation for the test reply")
        d.activate_target()
        region = d.validate()
        candidates = []
        diagnostics = []

        def visit(handle, _):
            description, is_edit = self.control_description(handle)
            try:
                self.validate_control(handle, region)
            except AgentError as error:
                diagnostics.append((is_edit, f"{description}: {error}"))
                return
            candidates.append(handle)
            diagnostics.append((is_edit, f"{description}: eligible"))

        d.gui.EnumChildWindows(d.config.target.hwnd, visit, None)
        if len(candidates) != 1:
            # Control metadata only: never query or log captions, drafts, or chat text.
            diagnostics.sort(key=lambda entry: not entry[0])
            self.report(
                f"Composer scan: {len(diagnostics)} child controls, {len(candidates)} eligible"
            )
            for _, detail in diagnostics[:20]:
                self.report("Composer diagnostic: " + detail)
            if len(diagnostics) > 20:
                self.report(
                    f"Composer diagnostic: {len(diagnostics) - 20} additional controls omitted"
                )
            raise AgentError(
                f"Found {len(candidates)} supported message boxes in the selected chat. "
                "See Composer diagnostic lines; no reply sent"
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

    def control_description(self, handle):
        try:
            name = self.desktop.gui.GetClassName(handle)
            style = self.desktop.gui.GetWindowLong(handle, -16)
            return f"class={name}, style=0x{style & 0xFFFFFFFF:08X}", "edit" in name.lower()
        except Exception:
            return "control metadata unavailable", False

    def validate_control(self, handle, _capture_region):
        d = self.desktop
        name = d.gui.GetClassName(handle).lower()
        style = d.gui.GetWindowLong(handle, -16)  # GWL_STYLE
        if not (name == "edit" or name.startswith("richedit")):
            raise AgentError("Unsupported control class")
        if not style & 0x0004:
            raise AgentError("Unsupported single-line control (not a multiline composer)")
        if style & (0x0020 | 0x0800):
            raise AgentError("Unsupported read-only or password control")
        if not d.gui.IsWindowEnabled(handle) or not d.gui.IsWindowVisible(handle):
            raise AgentError("Control is hidden or disabled")
        left, top, right, bottom = d.gui.GetWindowRect(handle)
        region = Region(left, top, right - left, bottom - top)
        client, _ = d.geometry()
        if (
            region.width <= 0
            or region.height <= 0
            or not client.contains(region)
            or not covered_by_monitors(region, d.monitors())
        ):
            raise AgentError("Message box must be inside the selected window and visible displays")
        other = d.gui.GetWindow(d.config.target.hwnd, d.con.GW_HWNDPREV)
        while other:
            if d.gui.IsWindowVisible(other) and not d.gui.IsIconic(other):
                x0, y0, x1, y1 = d.gui.GetWindowRect(other)
                if region.intersects(Region(x0, y0, x1 - x0, y1 - y0)):
                    raise AgentError("Another window overlaps the message box; nothing sent")
            other = d.gui.GetWindow(other, d.con.GW_HWNDPREV)

    def guard(self, handle):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled("Test reply cancelled")
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
        # Up to 2,000 reply characters, including UTF-16 surrogate pairs and CRLF.
        text = ctypes.create_unicode_buffer(4096)
        self.message(handle, 0x000D, len(text), ctypes.addressof(text))  # WM_GETTEXT
        return text.value

    def write(self, handle, text):
        self.guard(handle)
        # Select all and replace through the edit operation so the parent receives
        # EN_CHANGE. WM_SETTEXT omits that notification for multiline edit controls.
        self.message(handle, 0x00B1, 0, -1)  # EM_SETSEL
        self.guard(handle)
        buffer = ctypes.create_unicode_buffer(text)
        self.message(handle, 0x00C2, 1, ctypes.addressof(buffer))  # EM_REPLACESEL

    def submit(self, handle):
        def check():
            if self.cancel is not None and self.cancel.is_set():
                raise Cancelled("Test reply cancelled before Enter")
            self.guard(handle)
            if self.desktop.api.GetAsyncKeyState(13) & 0x8000:
                raise AgentError("Enter is already held down; no additional keypress sent")

        press_enter(self.desktop.user, check)

    def observe_submission(self, handle, cancel, timeout=2):
        """Observe composer clearing only; this is not a server delivery acknowledgement."""
        deadline = time.monotonic() + timeout
        while True:
            if cancel.is_set():
                return "Observation stopped after Enter; delivery uncertain, no automatic retry"
            try:
                text = self.read(handle)
            except AgentError:
                return "Focus changed after Enter; delivery uncertain, no automatic retry"
            except Exception:
                return (
                    "Cannot inspect message box after Enter; delivery uncertain, no automatic retry"
                )
            if not text.strip():
                return (
                    "Enter keypress sent; message box cleared. Delivery not independently verified"
                )
            if time.monotonic() >= deadline:
                return "Enter keypress sent, but text remains in the message box; send NOT confirmed, no automatic retry"
            cancel.wait(0.1)
