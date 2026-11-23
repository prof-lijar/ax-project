import json
import threading
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
import pytest

from app.api.incoming_llm import IncomingLLM
from app.api.operations_client import OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient
from app.api.workflow_llm import LLMSettings
from app.automation.monitoring_service import MonitoringService
from app.automation.saved_image_workflow import SavedImageWorkflow
from app.capture.saved_image import MAX_IMAGE_BYTES, load_capture_image, normalize_capture_image
from app.capture.screen_capture import encode_png
from app.models import AgentError, Cancelled, State
from app.storage.capture_queue import CaptureQueue
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_device_workflow import receipt

MESSAGE = "위치조정/이영희/광명시 OO동 OO로 56"
RESPONSE = "[자동 확인]\n기기 신호 확인 완료입니다.\n내용 기재해두었습니다."


@pytest.fixture
def image_test(config, queue, frame, monkeypatch):
    config.target = None
    config.llm_url, config.llm_model, config.llm_supports_vision = (
        "https://llm.test/v1",
        "vision",
        True,
    )
    config.operations_url, config.operations_username = "https://nexgent.test", "admin"
    config.bizgo_enabled = True  # This test must never enter the SMS path.
    state = SimpleNamespace(kind="incoming", actionable=True, cancel_at=None, api_result=None)
    llm_calls, api_calls, output, extracted, progress = [], [], [], [], []

    def forbidden(*args, **kwargs):
        pytest.fail("Saved-image tests must not capture, activate, type, or send SMS")

    monkeypatch.setattr("app.automation.reply_service.TestReplySender.send", forbidden)
    monkeypatch.setattr("app.api.bizgo_client.create_bizgo", forbidden)
    monkeypatch.setattr("app.api.bizgo_client.BizgoClient.send", forbidden)
    desktop = SimpleNamespace(
        validate=forbidden,
        activate_target=forbidden,
        suggest_chat_region=forbidden,
        request_target_activation=forbidden,
    )
    service = MonitoringService(
        desktop,
        SimpleNamespace(grab=forbidden),
        queue,
        config,
        lambda *a: None,
        forbidden,
        progress.append,
        image_test_output=output.append,
        image_test_text=extracted.append,
    )

    def model_server(request):
        body = json.loads(request.content)
        llm_calls.append(body)
        user = body["messages"][-1]["content"]
        if isinstance(user, list):
            assert len([part for part in user if part["type"] == "image_url"]) == 1
            if state.cancel_at == "extraction":
                service.command("stop")
            content = {"kind": state.kind, "text": MESSAGE, "sender": "Tester", "is_ai": False}
        else:
            source = json.loads(user)
            content = (
                {"requests": [source["text"]]}
                if "text" in source
                else {
                    "action": "기기위치조정",
                    "action_text": "위치조정",
                    "name": "이영희",
                    "address": "광명시 OO동 OO로 56",
                }
                if state.actionable
                else {
                    "action": None,
                    "action_text": None,
                    "name": None,
                    "address": None,
                }
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}, "finish_reason": "stop"}]
            },
        )

    def api_server(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={}, headers={"set-cookie": "session=test; Path=/"})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path == "/api/ax768/runs"
        assert request.headers["x-csrf-token"] == "csrf"
        api_calls.append(json.loads(request.content))
        if state.cancel_at == "api":
            service.command("stop")
        return httpx.Response(
            200,
            json=state.api_result or {
                **receipt(),
                "api_version": "1",
                "verified": True,
                "response": RESPONSE,
            },
        )

    llm = IncomingLLM(
        LLMSettings("https://llm.test/v1/chat/completions", "vision", 30),
        "synthetic-key",
        httpx.MockTransport(model_server),
    )
    operations = UnifiedOperationsClient(
        OperationsSettings(config.operations_url, config.operations_username),
        "synthetic-password",
        httpx.MockTransport(api_server),
    )
    workflow = service.saved_image_workflow
    workflow.llm_factory = lambda _: llm
    workflow.operations_factory = lambda _: operations
    yield SimpleNamespace(
        config=config,
        queue=queue,
        service=service,
        workflow=workflow,
        png=encode_png(frame),
        state=state,
        llm_calls=llm_calls,
        api_calls=api_calls,
        output=output,
        extracted=extracted,
        progress=progress,
        forbidden=forbidden,
    )
    service.command("stop")
    service.shutdown.set()
    if service.is_alive():
        service.join(3)
        assert not service.is_alive()


@pytest.mark.parametrize("extension", [".png", ".jpg", ".bmp"])
def test_imports_supported_images_without_modifying_original(tmp_path, frame, extension):
    ok, encoded = cv2.imencode(extension, frame)
    assert ok
    path = tmp_path / ("한글 캡처" + extension)
    original = encoded.tobytes()
    path.write_bytes(original)
    png = load_capture_image(path)
    assert png.startswith(b"\x89PNG") and path.read_bytes() == original
    assert normalize_capture_image(png) == png
    assert cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR).shape == frame.shape


@pytest.mark.parametrize("data", [b"", b"not an image", b"x" * (MAX_IMAGE_BYTES + 1)])
def test_invalid_import_never_calls_models_or_api(image_test, data):
    t = image_test
    with pytest.raises(AgentError):
        t.service.dispatch(("image_test", data))
    assert not t.llm_calls and not t.api_calls
    assert t.output and t.service.stop_input.is_set()


def test_image_dimensions_checked_before_workflow(frame, monkeypatch):
    monkeypatch.setattr("app.capture.saved_image.MAX_IMAGE_PIXELS", 100)
    with pytest.raises(AgentError, match="megapixels"):
        normalize_capture_image(encode_png(frame))


def test_missing_image_is_a_clear_error(tmp_path):
    with pytest.raises(AgentError, match="Cannot read"):
        load_capture_image(tmp_path / "missing.png")


def test_image_test_uses_unified_api_and_only_displays_exact_response(image_test):
    t = image_test
    t.service.dispatch(("image_test", t.png))
    assert t.output == [RESPONSE] and t.extracted == [MESSAGE]
    assert t.api_calls == [
        {
            "workflow_id": "device_adjustment_power",
            "message": MESSAGE,
            "confirmed_name": None,
            "action": "기기위치조정",
            "action_text": "위치조정",
            "name": "이영희",
            "address": "광명시 OO동 OO로 56",
        }
    ]
    assert len(t.llm_calls) == 3  # Latest-message extraction, source split, grounded action.
    assert t.service.state == State.STOPPED and t.service.stop_input.is_set()
    assert t.config.target is None and t.config.selection is None
    with t.queue.connect() as db:
        job = dict(db.execute("SELECT * FROM image_reply_queue").fetchone())
    assert job["chat_key"].startswith("image-test:") and job["status"] == "ignored"
    assert t.workflow.jobs.claim(t.service.general_auto_catch.queue_key()) is None
    assert t.queue.claim(t.config.api_url) is None  # No ordinary image upload either.


def test_missing_roster_reply_is_displayed_unchanged_and_cached(image_test):
    t = image_test
    response = (
        "[자동 확인]\n이영희님 신규설치 기기신호가 아직 확인되지 않습니다.\n"
        "기기 전원 및 설치 위치 확인 부탁드립니다. "
    )
    t.state.api_result = {
        "workflow_id": "device_adjustment_power",
        "api_version": "1",
        "status": "not_found",
        "verified": False,
        "response": response,
        "roster": {"status": "not_found"},
        "signal": {"status": "skipped"},
        "as_lookup": {"status": "skipped"},
        "as_update": {"status": "skipped", "verified": False},
        "member_note": None,
    }
    for _ in range(2):
        t.service.dispatch(("image_test", t.png))
    assert t.output == [response, response]
    assert len(t.api_calls) == 1
    assert t.service.state == State.STOPPED


@pytest.mark.parametrize("kind", ["outgoing", "none", "uncertain"])
def test_ineligible_images_do_not_run_api(image_test, kind):
    t = image_test
    t.state.kind = kind
    if kind == "uncertain":
        with pytest.raises(AgentError, match="unclear"):
            t.service.dispatch(("image_test", t.png))
    else:
        t.service.dispatch(("image_test", t.png))
        assert "No workflow executed" in t.output[-1]
    assert not t.api_calls and len(t.llm_calls) == 1


def test_unsupported_incoming_message_displays_no_action(image_test):
    t = image_test
    t.state.actionable = False
    t.service.dispatch(("image_test", t.png))
    assert not t.api_calls
    assert "No workflow executed" in t.output[-1]


def test_repeating_image_after_restart_reuses_result_and_never_claims_live_job(image_test):
    t = image_test
    # An existing live-chat job must not be processed by this test.
    live_id, _ = t.workflow.jobs.enqueue_pair("live-chat", t.png, t.png)
    t.service.dispatch(("image_test", t.png))
    reopened = CaptureQueue(t.queue.root, t.config)
    jobs = ImageReplyQueue(reopened)
    restarted = SavedImageWorkflow(
        t.config,
        reopened,
        jobs,
        OperationJournal(reopened),
        threading.Event(),
        t.progress.append,
        t.extracted.append,
        llm_factory=t.forbidden,
        operations_factory=t.forbidden,
    )
    assert restarted.run(t.png) == RESPONSE
    assert len(t.api_calls) == 1 and len(t.llm_calls) == 3
    assert jobs.claim("live-chat")["job_id"] == live_id


@pytest.mark.parametrize("stage", ["extraction", "api"])
def test_cancel_then_explicit_retry_does_not_repeat_submitted_api(image_test, stage):
    t = image_test
    t.state.cancel_at = stage
    with pytest.raises(Cancelled):
        t.service.dispatch(("image_test", t.png))
    assert "cancelled" in t.output[-1] and t.service.stop_input.is_set()
    assert len(t.api_calls) == (1 if stage == "api" else 0)
    t.service.dispatch("stop")
    t.state.cancel_at = None
    t.service.dispatch(("image_test", t.png))
    assert len(t.api_calls) == 1


def test_queued_image_test_is_removed_by_stop(image_test):
    t = image_test
    t.service.command("image_test", t.png)
    t.service.command("stop")
    assert t.service.commands.get_nowait() == "stop" and t.service.commands.empty()
    assert not t.api_calls and not t.llm_calls


def test_selecting_another_image_does_not_process_a_previous_failed_test(image_test):
    t = image_test
    t.state.kind = "uncertain"
    with pytest.raises(AgentError):
        t.service.dispatch(("image_test", t.png))
    t.service.dispatch("stop")
    t.state.kind = "incoming"
    different = encode_png(255 - cv2.imdecode(np.frombuffer(t.png, np.uint8), cv2.IMREAD_COLOR))
    t.service.dispatch(("image_test", different))
    assert t.output[-1] == RESPONSE and len(t.api_calls) == 1
    with t.queue.connect() as db:
        rows = db.execute("SELECT status,chat_key FROM image_reply_queue ORDER BY id").fetchall()
    assert [row["status"] for row in rows] == ["pending", "ignored"]
    assert rows[0]["chat_key"] != rows[1]["chat_key"]


def test_stop_cancels_image_processing_on_monitor_thread(image_test):
    t = image_test
    entered, finished = threading.Event(), threading.Event()

    def block(request, cancel):
        entered.set()
        assert cancel.wait(3)
        raise Cancelled("Cancelled during API call")

    def output(text):
        t.output.append(text)
        finished.set()

    t.workflow.operations_factory = lambda _: SimpleNamespace(run=block)
    t.service.image_test_output = output
    t.service.start()
    t.service.command("image_test", t.png)
    assert entered.wait(3)
    t.service.command("stop")
    assert finished.wait(3)
    assert "cancelled" in t.output[-1]
    assert t.service.stop_input.is_set()


def test_worker_error_is_shown_without_leaking_exception_details(image_test):
    t = image_test
    finished = threading.Event()

    def fail(_):
        raise RuntimeError("synthetic-secret-do-not-display")

    t.workflow.llm_factory = fail
    t.service.status = lambda state, _: finished.set() if state == State.PAUSED.value else None
    t.service.start()
    t.service.command("image_test", t.png)
    assert finished.wait(3)
    assert "RuntimeError" in t.output[-1]
    assert "synthetic-secret" not in t.output[-1]
    assert not t.api_calls and t.service.stop_input.is_set()


def test_test_tools_image_selection_and_output_without_chat(
    image_test, tmp_path, monkeypatch, qt_app
):
    from PySide6.QtCore import QAbstractNativeEventFilter

    from app.gui import main_window

    class Hotkey(QAbstractNativeEventFilter):
        registered = True

        def nativeEventFilter(self, *_):
            return False, 0

        def close(self):
            pass

    monkeypatch.setattr(main_window, "EmergencyHotkey", lambda _: Hotkey())
    monkeypatch.setattr("app.api.unified_operations.create_unified_operations", lambda _: None)
    t = image_test
    signals = main_window.Signals()
    t.service.status = signals.status.emit
    t.service.image_test_output = signals.image_test_output.emit
    t.workflow.text_preview = signals.image_test_text.emit
    window = main_window.MainWindow(
        t.config,
        tmp_path / "config.json",
        t.service.desktop,
        t.service,
        SimpleNamespace(is_alive=lambda: False),
        t.queue,
        signals,
    )
    window.select_window = t.forbidden
    path = tmp_path / "capture.png"
    path.write_bytes(t.png)
    monkeypatch.setattr(main_window.QFileDialog, "getOpenFileName", lambda *a: (str(path), "PNG"))
    try:
        window.show()
        assert not window.image_test_run_button.isEnabled()
        window.choose_test_image()
        assert window.image_test_preview.pixmap() is not None
        assert window.image_test_run_button.isEnabled()
        # The run uses the exact previewed bytes even if the original file changes.
        path.write_bytes(b"changed after choosing")
        window.start_image_test()
        window.start_image_test()  # A double click must not queue another test.
        assert not window.isMinimized()
        assert not window.image_test_run_button.isEnabled()
        assert t.service.commands.get_nowait() == "stop"
        command = t.service.commands.get_nowait()
        assert command == ("image_test", window.image_test_png)
        assert t.service.commands.empty()
        t.service.dispatch(command)
        qt_app.processEvents()
        assert window.image_test_output.toPlainText() == RESPONSE
        assert window.image_test_text.toPlainText() == MESSAGE
        assert window.image_test_output.isReadOnly()
        assert window.pending_action is None and window.image_test_run_button.isEnabled()
    finally:
        window.closing = True
        window.close()
        window.deleteLater()
