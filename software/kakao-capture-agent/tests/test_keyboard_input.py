import ctypes
import threading
from types import SimpleNamespace

import pytest

from app.automation.keyboard_input import Input, press_enter
from app.automation.reply_service import TEST_REPLY
from app.automation.windows_composer import WindowsComposer
from app.models import AgentError, Cancelled


@pytest.mark.parametrize("inserted", [0, 1, 2])
def test_native_enter_pair_and_partial_key_release(inserted):
    batches, checks = [], []

    class SendInput:
        def __call__(self, count, events, size):
            assert checks == [True]
            assert size == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            values = list(events) if count == 2 else [events._obj]
            batches.append([(event.type, event.ki.wScan, event.ki.dwFlags) for event in values])
            return inserted if count == 2 else 1

    user = SimpleNamespace(SendInput=SendInput())
    if inserted == 2:
        press_enter(user, lambda: checks.append(True))
    else:
        with pytest.raises(AgentError):
            press_enter(user, lambda: checks.append(True))
    expected = [[(1, 0x1C, 8), (1, 0x1C, 10)]]
    if inserted == 1:
        expected.append([(1, 0x1C, 10)])
    assert batches == expected
    assert Input.value.offset == (8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4)


@pytest.mark.parametrize("failure", ["cancel", "focus", "held_enter"])
def test_final_submit_guard_blocks_input(failure, monkeypatch):
    calls = []

    class SendInput:
        def __call__(self, *args):
            calls.append(args)
            return 2

    composer = WindowsComposer(
        SimpleNamespace(
            user=SimpleNamespace(SendInput=SendInput()),
            api=SimpleNamespace(
                GetAsyncKeyState=lambda _: 0x8000 if failure == "held_enter" else 0
            ),
        )
    )
    composer.cancel = threading.Event()
    if failure == "cancel":
        composer.cancel.set()
    monkeypatch.setattr(composer, "focused", lambda: 99 if failure == "focus" else 43)
    with pytest.raises(AgentError):
        composer.submit(43)
    assert not calls


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", "cleared"),
        ("\r\n", "cleared"),
        ("메시지 입력", "cleared"),
        (" \r\n메시지 입력\r\n", "cleared"),
        ("메시지 입력 중인 실제 내용", "NOT confirmed"),
        (TEST_REPLY, "NOT confirmed"),
    ],
)
def test_submission_observation_reports_remaining_text_without_retry(text, expected, monkeypatch):
    composer = WindowsComposer(None)
    monkeypatch.setattr(composer, "read_after_send", lambda _: text)
    result = composer.observe_submission(43, threading.Event(), timeout=0)
    assert expected in result.message
    assert result.composer_cleared == (expected == "cleared")


def test_submission_observation_stops_after_cancellation_or_focus_loss(monkeypatch):
    composer = WindowsComposer(None)
    cancel = threading.Event()
    cancel.set()
    assert "uncertain" in composer.observe_submission(43, cancel, timeout=0).message
    cancel.clear()

    def changed(_):
        raise Cancelled("Focus changed")

    monkeypatch.setattr(composer, "read_after_send", changed)
    observation = composer.observe_submission(43, cancel, timeout=0)
    assert "uncertain" in observation.message and not observation.composer_cleared


@pytest.mark.parametrize("valid", [True, False])
def test_read_after_send_does_not_require_keyboard_focus_but_checks_owner(valid, monkeypatch):
    target = SimpleNamespace(hwnd=42, pid=7)
    desktop = SimpleNamespace(
        config=SimpleNamespace(target=target),
        validate=lambda **kw: None,
        gui=SimpleNamespace(IsChild=lambda parent, child: valid),
        process=SimpleNamespace(GetWindowThreadProcessId=lambda handle: (1, 7)),
    )
    composer = WindowsComposer(desktop)
    monkeypatch.setattr(
        composer,
        "focused",
        lambda: (_ for _ in ()).throw(AssertionError("No keyboard focus required for observation")),
    )
    monkeypatch.setattr(composer, "validate_control", lambda *args: None)
    monkeypatch.setattr(composer, "read_text", lambda handle: "")
    result = composer.observe_submission(43, threading.Event(), timeout=0)
    assert result.composer_cleared == valid


def test_post_send_transient_read_failure_retries_observation_only(monkeypatch):
    reports, reads = [], []
    composer = WindowsComposer(None, reports.append)

    def read(handle):
        reads.append(handle)
        if len(reads) == 1:
            raise AgentError("Transient composer transition")
        return ""

    monkeypatch.setattr(composer, "read_after_send", read)
    result = composer.observe_submission(43, threading.Event(), timeout=1)
    assert result.composer_cleared and reads == [43, 43]
    assert reports == ["Post-send observation: Transient composer transition"]


def test_post_send_unknown_error_does_not_log_private_exception_text(monkeypatch):
    reports = []
    composer = WindowsComposer(None, reports.append)

    def read(handle):
        raise RuntimeError("private draft content")

    monkeypatch.setattr(composer, "read_after_send", read)
    result = composer.observe_submission(43, threading.Event(), timeout=0)
    assert not result.composer_cleared
    assert "RuntimeError" in result.message
    assert "private" not in result.message + " ".join(reports)
