import asyncio
import base64
import json
import threading

import httpx
import pytest

from app.api.workflow_llm import (
    LLMSettings,
    WorkflowLLM,
    completions_url,
    credential_destination,
    parse_field,
    validate_llm_url,
)
from app.automation.monitoring_service import MonitoringService
from app.automation.reply_service import TestReplySender as ReplySender
from app.config import load, save
from app.models import AgentError, Cancelled, State
from tests.test_automation import Capture, Desktop
from tests.test_replies import Composer


def response(field, text, finish="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"content": json.dumps({field: text}, ensure_ascii=False)},
                }
            ]
        },
    )


def llm(transport):
    return WorkflowLLM(
        LLMSettings("https://llm.test/v1/chat/completions", "vision", 5),
        "synthetic-key",
        httpx.MockTransport(transport),
    )


def test_capture_extract_summarize_send_one_cycle(config, queue, frame, region):
    requests, progress = [], []

    def api(request):
        assert request.headers["authorization"] == "Bearer synthetic-key"
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            url = body["messages"][1]["content"][1]["image_url"]["url"]
            png = base64.b64decode(url.split(",")[1])
            assert png.startswith(b"\x89PNG")
            assert png == next(queue.images.glob("*.png")).read_bytes()
            return response("extracted_text", "회의 자료를 준비해 주세요.\n내일까지 부탁합니다.")
        assert len(requests) == 2
        assert "회의 자료" in body["messages"][1]["content"]
        return response("simulated_done", "회의 자료 준비를 완료했다고 가정합니다.")

    desktop = Desktop(region)
    desktop.activate_target = lambda: desktop.validate()
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        progress.append,
    )
    composer = Composer()
    service.test_workflow.sender = ReplySender(composer, queue.event, service.stop_input)
    service.test_workflow.llm_factory = lambda _: llm(api)
    service.state = State.LIVE_MONITORING
    service.want_live = True
    service.command("stop")
    service.command("test_workflow")
    service.dispatch(service.commands.get_nowait())
    service.dispatch(service.commands.get_nowait())
    assert service.state == State.STOPPED and service.stop_input.is_set()
    assert not service.want_live and not desktop.calls  # No scrolling or monitoring restart.
    assert len(requests) == 2 and composer.submits == [10]
    sent = composer.text.replace("\r\n", "\n")
    assert sent == (
        "[test]\n-- What is done (simulation): 회의 자료 준비를 완료했다고 가정합니다."
        "\n-- User request (extracted text): 회의 자료를 준비해 주세요.\n내일까지 부탁합니다."
    )
    assert queue.stats()["unassigned"] == 1
    assert queue.claim(config.api_url) is None  # Local capture cannot enter the upload worker.
    with queue.connect() as db:
        audit = str(db.execute("SELECT kind,detail FROM events").fetchall())
        assert "synthetic-key" not in audit and "회의 자료" not in audit
    assert any("Workflow capture saved locally:" in item for item in progress)


@pytest.mark.parametrize("failure", ["cancel", "retarget", "invalid_target", "network", "storage"])
def test_workflow_failures_never_send(config, queue, frame, region, failure, monkeypatch):
    desktop = Desktop(region)
    desktop.activate_target = lambda: desktop.validate()
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    composer = Composer()
    service.test_workflow.sender = ReplySender(composer, queue.event, service.stop_input)
    original_prepare = composer.prepare

    def prepare(cancel):
        desktop.validate()
        original_prepare(cancel)

    composer.prepare = prepare

    class FakeLLM:
        def run(self, *args):
            if failure == "cancel":
                service.command("stop")
            elif failure == "retarget":
                config.chat_id = "other"
            elif failure == "invalid_target":
                desktop.valid = False
            elif failure == "network":
                raise AgentError("LLM connection failed")
            return "[test]\n-- What is done (simulation): reviewed\n-- User request: example"

    service.test_workflow.llm_factory = lambda _: FakeLLM()
    if failure == "storage":
        monkeypatch.setattr(queue, "enqueue", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    with pytest.raises((AgentError, OSError)):
        service.dispatch("test_workflow")
    assert not composer.writes and not composer.submits
    assert service.stop_input.is_set() and not service.recoverable and not service.want_live


@pytest.mark.parametrize(
    "kind",
    ["401", "429", "500", "redirect", "timeout", "json", "length", "empty", "large", "summary"],
)
def test_llm_failure_is_bounded_and_not_retried(kind):
    calls = []

    def api(request):
        calls.append(request)
        if kind.isdigit():
            return httpx.Response(int(kind), text="private body synthetic-key")
        if kind == "redirect":
            return httpx.Response(307, headers={"location": "https://other.test"})
        if kind == "timeout":
            raise httpx.ReadTimeout("private exception synthetic-key")
        if kind == "json":
            return httpx.Response(200, text="not json synthetic-key")
        if kind == "large":
            return httpx.Response(200, content=b"x" * (128 * 1024 + 1))
        if kind == "summary" and len(calls) == 2:
            return response("simulated_done", "")
        return response(
            "extracted_text",
            "" if kind == "empty" else "request",
            "length" if kind == "length" else "stop",
        )

    with pytest.raises(AgentError) as error:
        llm(api).run(b"png", threading.Event(), lambda _: None)
    assert len(calls) == (2 if kind == "summary" else 1)
    assert "synthetic-key" not in str(error.value) and "private" not in str(error.value)


def test_stop_cancels_pending_llm_request_without_waiting_for_timeout():
    async def exercise():
        cancel = threading.Event()
        finalized = []

        async def api(request):
            try:
                cancel.set()
                await asyncio.sleep(30)
            finally:
                finalized.append(True)

        with pytest.raises(Cancelled):
            await asyncio.wait_for(llm(api).run_async(b"png", cancel, lambda _: None), 1)
        assert finalized == [True]

    asyncio.run(exercise())


@pytest.mark.parametrize("text", ["x" * 1201, "bad\x00text", 123])
def test_invalid_extraction_rejected(text):
    with pytest.raises(AgentError):
        parse_field(json.dumps({"extracted_text": text}), "extracted_text", 1200)


def test_configuration_environment_and_credential_isolation(config, tmp_path):
    config.llm_url = "http://192.168.0.17:8000"
    config.llm_model = "local-vision"
    config.llm_supports_vision = config.llm_allow_http = True
    path = tmp_path / "config.json"
    save(path, config)
    restored = load(path)
    settings = LLMSettings.resolve(restored, {})
    assert settings.url == "http://192.168.0.17:8000/v1/chat/completions"
    assert settings.model == "local-vision"
    settings = LLMSettings.resolve(
        restored,
        {
            "URL": "https://old.test",
            "OPENAI_BASE_URL": "https://new.test/v1",
            "MODEL": "old",
            "OPENAI_MODEL": "new",
            "OPENAI_SUPPORTS_VISION": "true",
        },
    )
    assert settings.model == "new" and settings.url == "https://new.test/v1/chat/completions"
    assert credential_destination("https://new.test") == "llm:" + settings.url
    with pytest.raises(AgentError, match="vision"):
        LLMSettings.resolve(config, {"OPENAI_SUPPORTS_VISION": "false"})
    assert completions_url(settings.url) == settings.url


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://server.test/v1", False),
        ("http://192.168.0.17:8000", True),
        ("http://127.0.0.1:8000", True),
        ("http://localhost:8000", True),
    ],
)
def test_llm_urls(url, allowed):
    validate_llm_url(url, allowed)


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("http://192.168.0.17:8000", False),
        ("http://8.8.8.8", True),
        ("https://user:secret@server.test", False),
        ("https://server.test?key=secret", False),
    ],
)
def test_invalid_llm_urls(url, allowed):
    with pytest.raises(ValueError):
        validate_llm_url(url, allowed)


def test_multiline_reply_accepts_native_line_endings():
    composer = Composer()
    sender = ReplySender(composer, lambda *a: None, threading.Event())
    sender.send("[test]\n-- 완료 (테스트)\n-- 요청")
    assert composer.submits == [10] and "\r\n" in composer.text


@pytest.mark.parametrize("text", ["", "a" * 2001, "bad\0text"])
def test_invalid_generated_reply_does_not_touch_composer(text):
    composer = Composer()
    with pytest.raises(AgentError):
        ReplySender(composer, lambda *a: None, threading.Event()).send(text)
    assert not composer.writes and not composer.submits
