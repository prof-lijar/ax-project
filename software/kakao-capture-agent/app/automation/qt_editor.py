"""Bounded Windows accessibility session for a KakaoTalkUI Qt Quick message editor."""

import json
import os
import queue
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from app.models import AgentError, Cancelled, Region


def uses_qt_editor(target):
    return (
        target is not None and PureWindowsPath(target.executable).name.lower() == "kakaotalkui.exe"
    )


@contextmanager
def qt_editor_session(target, cancel=None):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Chat action cancelled")
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = Path(__file__).with_name("qt_editor.ps1").read_text(encoding="utf-8")
    with subprocess.Popen(
        [str(shell), "-NoProfile", "-NoLogo", "-NonInteractive", "-Command", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as process:
        responses = queue.Queue()

        def receive():
            try:
                for line in process.stdout:
                    responses.put(line)
            finally:
                responses.put(None)

        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        try:
            yield QtEditor(process, responses, target, cancel)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join()


class QtEditor:
    def __init__(self, process, responses, target, cancel):
        self.process, self.responses, self.target, self.cancel = process, responses, target, cancel
        self.bounds = None
        self.key = None

    def request(self, op, **values):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled("Chat action cancelled")
        request = {"op": op, "hwnd": self.target.hwnd, "pid": self.target.pid, **values}
        try:
            self.process.stdin.write(json.dumps(request).encode("ascii") + b"\n")
            self.process.stdin.flush()
        except OSError:
            raise AgentError("Windows accessibility helper closed") from None
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.cancel is not None and self.cancel.is_set():
                raise Cancelled("Chat action cancelled")
            try:
                line = self.responses.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                result = json.loads(line) if line else None
            except ValueError:
                result = None
            if not isinstance(result, dict):
                raise AgentError("Windows accessibility helper returned no usable result")
            if result.get("ok") is True:
                return result
            reasons = {
                "missing": "No writable KakaoTalkUI message box in the selected window. Select the chat by clicking its typing area",
                "ambiguous": "Multiple KakaoTalkUI message boxes in the selected window. Open the conversation in its own window",
                "focus": "The KakaoTalkUI message box lost keyboard focus",
                "window": "The selected KakaoTalkUI window is no longer in front",
                "moved": "The KakaoTalkUI editor moved during the action",
                "length": "KakaoTalkUI editor text exceeds the readback limit",
            }
            reason = reasons.get(result.get("reason"))
            if not reason:
                reason = (
                    "Windows could not access the KakaoTalkUI editor "
                    f"(helper line {result.get('line')}, {result.get('kind')})"
                )
            raise AgentError(reason)
        self.process.kill()  # A late response cannot be reused by a subsequent request.
        raise AgentError("Windows accessibility timed out while checking the KakaoTalkUI editor")

    def locate(self):
        result = self.request("locate")
        self.key = result["id"]
        return self.set_bounds(result["bounds"])

    def refresh_bounds(self):
        return self.set_bounds(self.request("bounds")["bounds"])

    def set_bounds(self, bounds):
        self.bounds = bounds
        left, top, right, bottom = self.bounds
        return Region(left, top, right - left, bottom - top)

    def action(self, op, **values):
        return self.request(op, bounds=self.bounds, **values)
