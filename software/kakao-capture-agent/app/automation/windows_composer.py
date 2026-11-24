"""Targeted Win32 text edits followed by a guarded native Enter keypress."""

import ctypes
import time
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import PureWindowsPath

from app.automation.composer_text import composer_is_empty
from app.automation.keyboard_input import press_enter
from app.automation.qt_editor import qt_editor_session, uses_qt_editor
from app.automation.reply_service import TestReplySender
from app.models import AgentError, Cancelled, Region, SubmissionObservation, covered_by_monitors


class WindowsComposer:
    def __init__(self, desktop, report=lambda _: None, *, require_capture=True):
        self.desktop = desktop
        self.require_capture = require_capture
        self.report = report
        self.cancel = None

    def prepare(self, cancel):
        """Find one unambiguous composer in the selected window and focus it."""
        self.cancel = cancel
        if cancel.is_set():
            raise Cancelled("Test reply cancelled")
        d = self.desktop
        self.report("Activating the selected conversation for the test reply")
        d.activate_target(cancel, require_capture=self.require_capture)
        region = d.validate(require_capture=self.require_capture)
        candidates = []
        diagnostics = []
        kakao_fields = set()

        def visit(handle, _):
            description, is_edit = self.control_description(handle)
            if not self.require_capture and is_edit and self.is_kakao_message_box(handle):
                kakao_fields.add(handle)
            try:
                self.validate_control(handle, region)
            except AgentError as error:
                diagnostics.append((is_edit, f"{description}: {error}"))
                return
            candidates.append(handle)
            diagnostics.append((is_edit, f"{description}: eligible"))

        d.gui.EnumChildWindows(d.config.target.hwnd, visit, None)
        if kakao_fields:
            # A blocked native reply field must never redirect input to a search/draft editor.
            candidates = [handle for handle in candidates if handle in kakao_fields]
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
            if not diagnostics:
                self.report(
                    "If the typing area belongs to KakaoTalkUI, pick the chat by clicking it in Select Window or Select Agent Chats"
                )
            raise AgentError(
                f"Found {len(candidates)} supported message boxes in the selected chat. "
                "See Composer diagnostic lines; no reply sent"
            )
        handle = candidates[0]
        if cancel.is_set():
            raise Cancelled("Test reply cancelled")
        self.validate_control(handle, d.validate(require_capture=self.require_capture))
        self.report("Message box identified; focusing it automatically")
        d.focus_reply_control(handle, cancel, require_capture=self.require_capture)
        deadline = time.monotonic() + 1
        while True:
            if cancel.is_set():
                raise Cancelled("Test reply cancelled")
            # Validate focus after the OS has processed the click, without sending another click.
            try:
                if self.focused() == handle:
                    return handle
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
        capture_region = d.validate(require_capture=self.require_capture)
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

    def is_kakao_message_box(self, handle):
        d = self.desktop
        target = d.config.target
        # KakaoTalk exposes its message editor as direct child RichEdit control 1006.
        return (
            PureWindowsPath(target.executable).name.lower() == "kakaotalk.exe"
            and d.gui.GetClassName(handle).lower() == "richedit50w"
            and d.gui.GetParent(handle) == target.hwnd
            and d.gui.GetDlgCtrlID(handle) == 1006
            and d.process.GetWindowThreadProcessId(handle)[1] == target.pid
        )

    def validate_control(self, handle, _region):
        d = self.desktop
        name = d.gui.GetClassName(handle).lower()
        style = d.gui.GetWindowLong(handle, -16)  # GWL_STYLE
        if not (name == "edit" or name.startswith("richedit")):
            raise AgentError("Unsupported control class")
        if not style & 0x0004 and (self.require_capture or not self.is_kakao_message_box(handle)):
            raise AgentError("Unsupported single-line control (not a multiline composer)")
        if style & (0x0020 | 0x0800):
            raise AgentError("Unsupported read-only or password control")
        if not d.gui.IsWindowEnabled(handle) or not d.gui.IsWindowVisible(handle):
            raise AgentError("Control is hidden or disabled")
        left, top, right, bottom = d.gui.GetWindowRect(handle)
        region = Region(left, top, right - left, bottom - top)
        self.validate_bounds(region)

    def validate_bounds(self, region):
        d = self.desktop
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
        return self.read_text(handle)

    def read_text(self, handle):
        # Up to 2,000 reply characters, including UTF-16 surrogate pairs and CRLF.
        text = ctypes.create_unicode_buffer(4096)
        self.message(handle, 0x000D, len(text), ctypes.addressof(text))  # WM_GETTEXT
        return text.value

    def read_after_send(self, handle):
        """Read the original composer without requiring that it still owns keyboard focus."""
        d = self.desktop
        region = d.validate(require_capture=self.require_capture)
        target = d.config.target
        if (
            not d.gui.IsChild(target.hwnd, handle)
            or d.process.GetWindowThreadProcessId(handle)[1] != target.pid
        ):
            raise AgentError("Original message box is no longer in the selected conversation")
        self.validate_control(handle, region)
        text = self.read_text(handle)
        d.validate(require_capture=self.require_capture)
        return text

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
        last_failure = None
        while True:
            if cancel.is_set():
                return SubmissionObservation(
                    "Observation stopped after Enter; delivery uncertain, no automatic retry"
                )
            try:
                text = self.read_after_send(handle)
            except Cancelled:
                return SubmissionObservation(
                    "Observation cancelled after Enter; delivery uncertain, no automatic retry"
                )
            except Exception as error:
                # A transient focus/layout/control transition after Enter is not a
                # failed send. Retry observation only; never type or press Enter here.
                reason = str(error) if isinstance(error, AgentError) else type(error).__name__
                if reason != last_failure:
                    self.report("Post-send observation: " + reason)
                    last_failure = reason
                if time.monotonic() >= deadline:
                    return SubmissionObservation(
                        "Composer clearing unconfirmed after Enter: "
                        + reason
                        + "; no automatic retry"
                    )
                cancel.wait(0.1)
                continue
            if composer_is_empty(text):
                return SubmissionObservation(
                    "Enter keypress sent; message box cleared. Delivery not independently verified",
                    composer_cleared=True,
                )
            if time.monotonic() >= deadline:
                return SubmissionObservation(
                    "Enter keypress sent, but text remains in the message box; send NOT confirmed, no automatic retry"
                )
            cancel.wait(0.1)


class QtWindowsComposer(WindowsComposer):
    def __init__(self, native, editor):
        super().__init__(native.desktop, native.report, require_capture=native.require_capture)
        self.editor = editor

    def prepare(self, cancel):
        self.cancel = cancel
        self.desktop.activate_target(cancel, require_capture=self.require_capture)
        self.report("Locating the KakaoTalkUI editor in the selected conversation")
        self.validate_bounds(self.editor.locate())
        self.verify()
        self.editor.action("focus")
        return self.editor.key

    def verify(self):
        import pyautogui

        if self.desktop.config.target != self.editor.target:
            raise AgentError("Selected KakaoTalkUI conversation changed")
        try:
            pyautogui.failSafeCheck()
        except pyautogui.FailSafeException:
            raise Cancelled("Mouse fail-safe activated") from None
        self.desktop.validate(require_capture=self.require_capture)
        self.validate_bounds(self.editor.refresh_bounds())
        if any(self.desktop.api.GetAsyncKeyState(key) & 0x8000 for key in (16, 17, 18, 91, 92)):
            raise AgentError("Release keyboard modifiers before sending")

    def focused(self):
        self.verify()
        self.editor.action("check")
        return self.editor.key

    def write(self, handle, text):
        self.guard(handle)
        self.editor.action("write", text=text.replace("\r\n", "\n"))

    def read(self, handle):
        self.guard(handle)
        return self.editor.action("read")["text"]

    def read_after_send(self, handle):
        self.verify()
        return self.editor.action("observe")["text"]


class WindowsReplySender(TestReplySender):
    @contextmanager
    def composer_session(self):
        target = self.composer.desktop.config.target
        if uses_qt_editor(target):
            with qt_editor_session(target, self.cancel) as editor:
                yield QtWindowsComposer(self.composer, editor)
        else:
            yield self.composer
