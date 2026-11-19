"""Read a verified conversation through Windows accessibility in a bounded helper process."""

import ctypes
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.api.workflow_llm import check_cancel
from app.models import AgentError


@dataclass(frozen=True)
class ChatText:
    text: str
    source: str
    key: str


class WindowsChatText:
    def __init__(self, desktop, report=lambda _: None):
        self.desktop, self.report = desktop, report
        self.diagnostic = {}

    def native_text(self, region, target, cancel):
        """Standard read-only Win32 editors expose text even without a UIA proxy."""
        d = self.desktop
        if not hasattr(d, "gui"):
            return None
        candidates = []

        def eligible(handle):
            name = d.gui.GetClassName(handle).lower()
            style = d.gui.GetWindowLong(handle, -16)
            if not (name == "edit" or name.startswith("richedit")):
                return False
            if not style & 0x4 or not style & 0x800 or style & 0x20:
                return False
            if not d.gui.IsWindowVisible(handle) or not d.gui.IsChild(target.hwnd, handle):
                return False
            if d.process.GetWindowThreadProcessId(handle)[1] != target.pid:
                return False
            from app.models import Region

            left, top, right, bottom = d.gui.GetWindowRect(handle)
            bounds = Region(left, top, right - left, bottom - top)
            return (
                region.contains(bounds)
                and bounds.width >= region.width * 0.4
                and bounds.height >= region.height * 0.25
            )

        def visit(handle, _):
            if eligible(handle):
                candidates.append(handle)

        d.gui.EnumChildWindows(target.hwnd, visit, None)
        if not candidates:
            return None
        if len(candidates) != 1:
            raise AgentError(
                "Multiple read-only transcript controls found; select only the conversation text area"
            )
        from app.automation.windows_composer import WindowsComposer

        handle = candidates[0]
        message = WindowsComposer(d).message
        check_cancel(cancel)
        if message(handle, 0x000E) > 1_000_000:
            raise AgentError("Native transcript exceeds the text reader limit")
        buffer = ctypes.create_unicode_buffer(1_000_001)
        count = message(handle, 0x000D, len(buffer), ctypes.addressof(buffer))
        check_cancel(cancel)
        d.validate()
        if d.config.target != target or not eligible(handle) or count >= len(buffer) - 1:
            raise AgentError("Native transcript changed or exceeded the read limit")
        text = buffer.value.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > 32000:
            text = text[-32000:]
            if "\n" in text:
                text = text.split("\n", 1)[1]
        return ChatText(text.strip(), "Windows read-only Edit text", f"win32:{handle}")

    def read(self, cancel):
        check_cancel(cancel)
        region = self.desktop.validate()
        target = self.desktop.config.target
        if sys.platform != "win32":
            raise AgentError("Direct chat text requires Windows UI Automation")
        native = self.native_text(region, target, cancel)
        if native is not None:
            return native
        powershell = (
            Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        payload = json.dumps(
            {"hwnd": target.hwnd, "pid": target.pid, "region": asdict(region)}
        ).encode("utf-8")
        script = Path(__file__).with_name("read_chat_text.ps1").read_text(encoding="utf-8")
        process = subprocess.Popen(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + 8
        try:
            while True:
                check_cancel(cancel)
                if time.monotonic() >= deadline:
                    raise AgentError("Windows chat text reader timed out; no screenshot fallback")
                try:
                    output, _ = process.communicate(input=payload, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    payload = None
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        check_cancel(cancel)
        self.desktop.validate()
        if self.desktop.config.target != target:
            raise AgentError("Selected conversation changed while reading text")
        try:
            body = json.loads(output.decode("utf-8-sig"))
            if isinstance(body, dict) and not body.get("ok"):
                self.diagnostic = {
                    key: body.get(key)
                    for key in ("reason", "stage", "error_type", "error_id", "controls")
                }
                self.report(
                    "Text access diagnostic: "
                    + json.dumps(self.diagnostic, ensure_ascii=True)[:1500]
                )
            if not isinstance(body, dict) or not body.get("ok"):
                raise ValueError()
            text, source, key = (body[k] for k in ("text", "source", "key"))
            if not all(isinstance(v, str) for v in (text, source, key)) or len(text) > 32000:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise AgentError(
                "KakaoTalk did not expose a readable conversation through Windows accessibility. "
                "Run Agent (auto) uses no screenshots. Direct text is unavailable for this window/client."
            ) from None
        return ChatText(text.replace("\r\n", "\n").replace("\r", "\n").strip(), source, key)
