import asyncio
import base64
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.api.incoming_llm import (
    RUN_AGENT_GREETING,
    IncomingAnalysisError,
    IncomingLLM,
    IncomingMessage,
    parse_incoming,
)
from app.api.workflow_llm import LLMSettings
from app.automation.monitoring_service import MonitoringService
from app.capture.screen_capture import encode_png
from app.models import AgentError, Cancelled, State, TargetUnavailable
from tests.test_automation import Capture, Desktop


def completion(body):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(body, ensure_ascii=False)},
                }
            ]
        },
    )


@pytest.mark.parametrize("kind,is_ai,expected", [
    ("incoming", False, "incoming"), ("outgoing", False, "outgoing"),
    ("incoming", True, "outgoing"), ("uncertain", False, "uncertain"),
])
def test_startup_uses_one_snapshot_and_validates_direction(frame, kind, is_ai, expected):
    png = encode_png(frame)

    def api(request):
        data = json.loads(request.content)
        images = [part["image_url"]["url"] for part in data["messages"][1]["content"]
                  if part["type"] == "image_url"]
        assert [base64.b64decode(url.split(",")[1]) for url in images] == [png]
        assert data["response_format"] == {"type": "json_object"}
        return completion(dict(kind=kind, text="위치조정/이은경/헌릉로8길58", sender="", is_ai=is_ai))

    llm = IncomingLLM(LLMSettings("https://llm.test", "vision", 5), "key", httpx.MockTransport(api))
    assert llm.classify_latest(png, threading.Event()).kind == expected


@pytest.mark.parametrize("batch", [False, True])
def test_two_images_then_one_prefixed_answer(frame, batch):
    before, after = encode_png(frame), encode_png(255 - frame)
    requests = []

    def api(request):
        assert request.headers["authorization"] == "Bearer synthetic-key"
        data = json.loads(request.content)
        requests.append(data)
        if len(requests) == 1:
            assert data["response_format"] == {"type": "json_object"}
            system = data["messages"][0]["content"]
            assert ("include all new readable incoming" in system) == batch
            images = [
                part["image_url"]["url"]
                for part in data["messages"][1]["content"]
                if part["type"] == "image_url"
            ]
            assert [base64.b64decode(url.split(",")[1]) for url in images] == [before, after]
            return completion(
                dict(kind="incoming", text="2 더하기 2는?", sender="테스트", is_ai=False)
            )
        assert json.loads(data["messages"][1]["content"])["message"] == "2 더하기 2는?"
        assert "response_format" not in data
        return completion({"reply": "[AI] [AI] 4입니다."})

    llm = IncomingLLM(
        LLMSettings("https://llm.test/v1/chat/completions", "vision", 5),
        "synthetic-key",
        httpx.MockTransport(api),
    )
    incoming = llm.classify(before, after, threading.Event(), batch=batch)
    assert incoming.kind == "incoming"
    assert llm.answer(incoming, threading.Event()) == "[AI] 4입니다."
    assert len(requests) == 2


@pytest.mark.parametrize(
    "text",
    [
        "[AI] answer",
        "[test]\nsummary",
        "[AI가 답장드렸습니다]",
        "  [ai] reply",
        "[자동 확인]\n이은경님 기기 위치변경 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)",
        RUN_AGENT_GREETING,
    ],
)
def test_generated_messages_are_ignored_even_if_model_misclassifies(text):
    assert (
        parse_incoming(json.dumps(dict(kind="incoming", text=text, sender="", is_ai=False))).kind
        == "outgoing"
    )


@pytest.mark.parametrize(
    "body",
    [
        [],
        None,
        {},
        {"kind": "incoming"},
        dict(kind="incoming", text="", sender="", is_ai=False),
        dict(kind="incoming", text="hi", sender="", is_ai="false"),
        dict(kind="unexpected", text="hi", sender="", is_ai=False),
        dict(kind="incoming", text="x" * 1201, sender="", is_ai=False),
    ],
)
def test_bad_analysis_never_generates_reply(body):
    with pytest.raises(AgentError, match="invalid JSON"):
        parse_incoming(json.dumps(body))


@pytest.mark.parametrize("fence", ["json\n", "JSON\r\n", "\n", "json \n"])
def test_single_json_fence_variants(fence):
    content = json.dumps(dict(kind="incoming", text='질문 "안녕"\n두 줄', sender="", is_ai=False))
    assert parse_incoming("```" + fence + content + "\n```").text == '질문 "안녕"\n두 줄'


@pytest.mark.parametrize(
    "content,reason",
    [
        ('{"kind":"incoming","kind":"none"}', "duplicate fields"),
        ("private chat contents", "syntax"),
        ('{"kind":"incoming"}', "missing fields"),
        (
            '{"kind":"incoming","text":"secret","sender":"","is_ai":"false"}',
            "invalid classification fields",
        ),
        ('{"kind":"none","text":"","sender":"","is_ai":false} trailing', "syntax"),
    ],
)
def test_analysis_errors_have_safe_specific_diagnostics(content, reason):
    with pytest.raises(IncomingAnalysisError, match=reason) as error:
        parse_incoming(content)
    assert "private" not in str(error.value) and "secret" not in str(error.value)


@pytest.mark.parametrize("reply", ["4입니다.", "[AI] 4입니다.", "첫째 줄\n둘째 줄"])
def test_reply_accepts_plain_text(reply):
    def api(request):
        body = json.loads(request.content)
        assert "response_format" not in body
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": reply}}]}
        )

    llm = IncomingLLM(LLMSettings("https://llm.test", "vision", 5), "key", httpx.MockTransport(api))
    result = llm.answer(IncomingMessage("incoming", "질문"), threading.Event())
    assert result == (reply if reply.startswith("[AI]") else "[AI] " + reply)


def test_structured_output_falls_back_only_once_when_explicitly_unsupported():
    requests = []

    def api(request):
        body = json.loads(request.content)
        requests.append(body)
        if "response_format" in body:
            return httpx.Response(422, json={"error": "response_format is unsupported"})
        return completion(dict(kind="incoming", text="Hello", sender="", is_ai=False))

    llm = IncomingLLM(LLMSettings("https://llm.test", "vision", 5), "key", httpx.MockTransport(api))
    for _ in range(2):
        assert llm.classify(b"before", b"after", threading.Event()).kind == "incoming"
    assert len(requests) == 3
    assert ["response_format" in r for r in requests] == [True, False, False]


@pytest.mark.parametrize(
    "status,body", [(401, "response_format"), (500, "response_format"), (400, "model not found")]
)
def test_other_api_errors_do_not_trigger_format_fallback(status, body):
    calls = []

    def api(request):
        calls.append(request)
        return httpx.Response(status, text=body)

    llm = IncomingLLM(LLMSettings("https://llm.test", "vision", 5), "key", httpx.MockTransport(api))
    with pytest.raises(AgentError, match=f"HTTP {status}"):
        llm.classify(b"before", b"after", threading.Event())
    assert len(calls) == 1


def test_stop_prevents_structured_output_fallback_request():
    cancel, calls = threading.Event(), []

    def api(request):
        calls.append(request)
        cancel.set()
        return httpx.Response(400, text="response_format unsupported")

    llm = IncomingLLM(LLMSettings("https://llm.test", "vision", 5), "key", httpx.MockTransport(api))
    with pytest.raises(Cancelled):
        llm.classify(b"before", b"after", cancel)
    assert len(calls) == 1


def test_cancel_active_comparison_request():
    cancel = threading.Event()
    ended = []

    async def api(request):
        cancel.set()
        try:
            await asyncio.sleep(10)
        finally:
            ended.append(True)

    llm = IncomingLLM(
        LLMSettings("https://llm.test/v1/chat/completions", "vision", 5),
        "synthetic-key",
        httpx.MockTransport(api),
    )
    with pytest.raises(Cancelled):
        llm.classify(b"before", b"after", cancel)
    assert ended == [True]


@pytest.fixture
def watching(config, queue, frame, region):
    desktop = Desktop(region)
    desktop.activate_target = lambda cancel=None: desktop.validate()
    capture = Capture(desktop, frame)
    logs, sent, comparisons = [], [], []
    now = [0]
    service = MonitoringService(
        desktop, capture, queue, config, lambda *a: None, lambda *a: None, logs.append
    )
    workflow = service.incoming_workflow
    workflow.clock = lambda: now[0]

    class LLM:
        outcome = IncomingMessage("incoming", "2 + 2?", "Tester")

        def classify(self, before, after, cancel):
            comparisons.append((before, after))
            return self.outcome

        def answer(self, incoming, cancel):
            return "[AI] 4"

    llm = LLM()
    workflow.llm_factory = lambda _: llm
    workflow.sender = SimpleNamespace(send=lambda text: sent.append(text) or "send requested")
    service.dispatch("incoming_test")
    return SimpleNamespace(
        service=service,
        workflow=workflow,
        desktop=desktop,
        capture=capture,
        llm=llm,
        now=now,
        logs=logs,
        sent=sent,
        comparisons=comparisons,
        queue=queue,
    )


def changed(w):
    w.capture.frame = 255 - w.capture.frame
    w.service.poll_incoming()  # Start debounce; no API request yet.
    w.now[0] += 2
    w.service.poll_incoming()


def test_waits_for_new_frame_replies_once_and_stops(watching):
    w = watching
    assert w.service.state == State.WAITING_FOR_MESSAGE
    for _ in range(3):
        w.service.poll_incoming()
    assert not w.comparisons and not w.sent and not list(w.queue.images.glob("*.png"))
    changed(w)
    assert w.sent == ["[AI] 4"] and len(w.comparisons) == 1
    assert w.service.state == State.STOPPED and w.service.stop_input.is_set()
    assert not w.service.want_live and not w.workflow.active
    assert not w.desktop.calls  # No scrolling / bottom calibration / Bizgo.
    files = list(w.queue.images.glob("*.png"))
    assert len(files) == 1 and files[0].read_bytes() == w.comparisons[0][1]
    assert any(str(files[0]) in message for message in w.logs)
    assert w.queue.claim(w.service.config.api_url) is None
    with pytest.raises(AgentError):
        w.workflow.tick()  # No self-reply or replay after completion.
    assert w.sent == ["[AI] 4"]


@pytest.mark.parametrize("kind", ["none", "outgoing"])
def test_ignored_change_updates_baseline_without_reply(watching, kind):
    w = watching
    w.llm.outcome = IncomingMessage(kind)
    changed(w)
    assert not w.sent and w.service.state == State.WAITING_FOR_MESSAGE
    w.service.poll_incoming()
    assert len(w.comparisons) == 1
    first_after = w.comparisons[0][1]
    w.llm.outcome = IncomingMessage("incoming", "Hello")
    changed(w)
    assert w.comparisons[1][0] == first_after
    assert w.sent == ["[AI] 4"]


@pytest.mark.parametrize(
    "failure",
    ["stop", "target", "hidden", "uncertain", "network", "storage", "answer_cancel", "send"],
)
def test_interrupted_watch_never_retries_or_resumes(watching, failure, monkeypatch):
    w = watching
    if failure == "stop":
        w.service.command("stop")
    elif failure == "target":
        w.service.config.chat_id = "changed"
    elif failure == "hidden":
        w.desktop.valid = False
    elif failure == "uncertain":
        w.llm.outcome = IncomingMessage("uncertain")
    elif failure in ("network", "storage", "send"):

        def fail(*a, **kw):
            raise AgentError("Simulated failure")

        target, method = {
            "network": (w.llm, "classify"),
            "storage": (w.queue, "enqueue"),
            "send": (w.workflow.sender, "send"),
        }[failure]
        monkeypatch.setattr(target, method, fail)
    elif failure == "answer_cancel":

        def answer(*args):
            w.service.command("stop")
            return "[AI] Do not send"

        w.llm.answer = answer
    with pytest.raises(AgentError) as error:
        changed(w)
    w.service.pause(error.value)
    assert not w.sent and not w.workflow.active
    assert not w.service.want_live and not w.service.recoverable
    assert w.service.stop_input.is_set()


def test_target_lost_during_analysis_pauses(watching):
    w = watching
    original = w.llm.classify

    def classify(*args):
        w.desktop.valid = False
        return original(*args)

    w.llm.classify = classify
    with pytest.raises(TargetUnavailable):
        changed(w)
    assert not w.sent


@pytest.mark.parametrize("phase", ["waiting", "analysis", "answer"])
def test_wait_deadline_prevents_late_reply(watching, phase):
    w = watching
    if phase == "waiting":
        w.now[0] = 301
        w.service.poll_incoming()
    else:
        original = getattr(w.llm, "classify" if phase == "analysis" else "answer")

        def expire(*args):
            w.now[0] = 301
            return original(*args)

        setattr(w.llm, "classify" if phase == "analysis" else "answer", expire)
        changed(w)
    assert not w.sent and w.service.state == State.STOPPED
    assert "limit reached" in w.service.reason


def test_rearming_uses_new_baseline(watching):
    w = watching
    changed(w)
    w.service.dispatch("incoming_test")
    w.service.poll_incoming()
    assert len(w.comparisons) == 1 and w.sent == ["[AI] 4"]
    assert w.service.state == State.WAITING_FOR_MESSAGE
