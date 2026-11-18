import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingLLM, IncomingMessage
from app.api.workflow_llm import LLMSettings, check_cancel
from app.automation.monitoring_service import MonitoringService
from app.automation.text_auto_catch import TextAutoCatchWorkflow
from app.automation.text_changes import appended_text
from app.automation.windows_chat_text import ChatText
from app.models import AgentError, ForegroundLost, Selection, State, TargetUnavailable
from app.storage.text_queue import TextQueue
from tests.test_automation import Desktop


@pytest.fixture
def watching(config, queue, region):
    config.selection = Selection(region, 300, 300, 96)
    desktop = Desktop(region)
    desktop.activate_target = lambda cancel: desktop.validate()
    config.target = None
    source = SimpleNamespace(text="Old message", key="transcript")
    sent, classified, preview, logs = [], [], [], []
    now = [0]

    def no_pixels():
        raise AssertionError("Auto Catch must never capture a screenshot")

    service = MonitoringService(
        desktop,
        SimpleNamespace(grab=no_pixels),
        queue,
        config,
        lambda *a: None,
        no_pixels,
        logs.append,
        text_preview=preview.append,
    )
    # Retain regression coverage for the previous optional text workflow.
    service.auto_catch = TextAutoCatchWorkflow(
        desktop,
        service.capture,
        queue,
        config,
        service.reply_sender,
        service.stop_input,
        no_pixels,
        lambda message: service.transition(State.INITIALIZING, message),
        text_preview=preview.append,
    )
    w = service.auto_catch
    w.clock = lambda: now[0]
    w.text_reader = SimpleNamespace(
        read=lambda cancel: ChatText(source.text, "Synthetic native text", source.key)
    )

    class LLM:
        def classify_text(self, text, cancel):
            classified.append(text)
            check_cancel(cancel)
            return IncomingMessage("outgoing" if "[AI]" in text else "incoming", text)

        def answer(self, incoming, cancel):
            check_cancel(cancel)
            return "[AI] " + incoming.text + " answer"

    llm = LLM()
    w.llm_factory = lambda config: llm
    w.sender = SimpleNamespace(
        send=lambda text: sent.append(text) or "cleared", composer_cleared=True
    )
    service.dispatch("auto_catch")
    yield SimpleNamespace(
        service=service,
        workflow=w,
        source=source,
        desktop=desktop,
        queue=queue,
        sent=sent,
        classified=classified,
        llm=llm,
        now=now,
        preview=preview,
        logs=logs,
    )
    service.command("stop")
    w.reset()


def append(w, text):
    w.source.text += "\n" + text
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()


def finish(w):
    if w.workflow.worker:
        w.workflow.worker.join(2)
        assert not w.workflow.worker.is_alive()
    w.service.poll_auto_catch()


def test_native_text_two_replies_without_pixels_or_vision(watching):
    w = watching
    assert w.preview == ["Old message"] and not w.classified
    append(w, "First question")
    finish(w)
    assert w.sent == ["[AI] First question answer (자동 응답)"]
    w.now[0] += 4
    append(w, "Second question")
    finish(w)
    assert w.classified == ["First question", "Second question"]
    assert len(w.sent) == 2 and w.workflow.reply_count == 2
    assert w.workflow.active and w.service.state == State.AUTO_CATCHING
    assert not list(w.queue.images.glob("*.png"))


def test_arrivals_queue_during_slow_inference_and_reply_in_fifo_order(watching):
    w = watching
    started, release = threading.Event(), threading.Event()
    original = w.llm.answer

    def answer(incoming, cancel):
        if incoming.text == "First":
            started.set()
            while not release.wait(0.01):
                check_cancel(cancel)
        return original(incoming, cancel)

    w.llm.answer = answer
    append(w, "First")
    assert started.wait(1)
    append(w, "Second")
    append(w, "Third")
    assert w.workflow.jobs.count(w.workflow.chat_key) == 3
    assert w.classified == ["First"] and not w.sent
    release.set()
    finish(w)
    for _ in range(2):
        w.now[0] += 4
        w.service.poll_auto_catch()
        finish(w)
    assert w.classified == ["First", "Second", "Third"]
    assert w.sent == [f"[AI] {text} answer (자동 응답)" for text in ["First", "Second", "Third"]]
    assert w.workflow.jobs.count(w.workflow.chat_key) == 0


def test_stop_cancels_inference_and_retains_pending_jobs(watching):
    w = watching
    started = threading.Event()

    def answer(incoming, cancel):
        started.set()
        cancel.wait(2)
        check_cancel(cancel)
        raise AssertionError("Cancellation must interrupt inference")

    w.llm.answer = answer
    append(w, "First")
    assert started.wait(1)
    append(w, "Second")
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    assert not w.sent and w.workflow.worker is None
    with w.queue.connect() as db:
        assert [r[0] for r in db.execute("SELECT status FROM text_reply_queue ORDER BY id")] == [
            "pending",
            "pending",
        ]


def test_malformed_analysis_retains_fifo_and_does_not_send(watching):
    w = watching
    w.llm.classify_text = lambda *a: (_ for _ in ()).throw(IncomingAnalysisError("invalid"))
    append(w, "First")
    finish(w)
    append(w, "Second")
    assert not w.sent and w.workflow.active
    with w.queue.connect() as db:
        rows = db.execute(
            "SELECT text,status,attempts FROM text_reply_queue ORDER BY id"
        ).fetchall()
    assert [r["text"] for r in rows] == ["First", "Second"]
    assert rows[0]["status"] == "pending" and rows[0]["attempts"] == 1


def test_uncertain_send_retains_later_jobs_and_never_replays(watching):
    w = watching
    append(w, "First")
    # Finish LLM without submitting, then queue a later arrival.
    w.workflow.worker.join(2)
    w.workflow.sender.composer_cleared = False
    w.source.text += "\nSecond"
    # Ensure Second is durably collected before the first send attempt.
    w.workflow.collect()
    w.now[0] += 0.5
    w.workflow.collect()
    with pytest.raises(AgentError, match="uncertain") as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    assert len(w.sent) == 1
    recovered = TextQueue(w.queue)
    with pytest.raises(AgentError, match="uncertain"):
        recovered.claim(w.workflow.chat_key)
    recovered.resolve_review(w.workflow.chat_key)
    assert recovered.claim(w.workflow.chat_key)["text"] == "Second"
    assert len(w.sent) == 1


def test_focus_recovery_preserves_prepared_answer(watching):
    w = watching
    append(w, "First")
    w.workflow.worker.join(2)
    original = w.workflow.ensure_foreground
    attempts = [0]

    def focus():
        attempts[0] += 1
        if attempts[0] == 2:  # After collection, before sending the ready answer.
            raise ForegroundLost("temporarily denied")
        original()

    w.workflow.ensure_foreground = focus
    with pytest.raises(ForegroundLost) as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    w.workflow.ensure_foreground = original
    w.service.try_recover_auto_focus()
    finish(w)
    assert w.classified == ["First"] and len(w.sent) == 1


@pytest.mark.parametrize("failure", ["hidden", "changed_control"])
def test_read_failure_never_falls_back_to_screenshots(watching, failure):
    w = watching
    if failure == "hidden":
        w.desktop.valid = False
    else:
        w.source.key = "different"
    with pytest.raises((AgentError, TargetUnavailable)):
        append(w, "New")
    assert not w.sent and not w.classified


def test_own_reply_does_not_create_reply_loop(watching):
    w = watching
    append(w, "Question")
    finish(w)
    w.now[0] += 4
    append(w, w.sent[0])
    finish(w)
    assert len(w.sent) == 1 and w.workflow.jobs.count(w.workflow.chat_key) == 0


@pytest.mark.parametrize(
    "before,after,delta",
    [
        ("one", "one\ntwo", "two"),
        ("one\ntwo", "two\nthree", "three"),
        ("one\ntwo", "two", ""),
        ("", "hello", "hello"),
        ("one", "one", ""),
        ("one", "one\none", "one"),
    ],
)
def test_append_only_transcript_changes(before, after, delta):
    assert appended_text(before, after) == delta


def test_unrelated_replacement_does_not_replay_old_history():
    with pytest.raises(AgentError):
        appended_text("current history", "different history")


def test_queue_restart_recovers_inference_but_quarantines_sends(queue):
    jobs = TextQueue(queue)
    first = jobs.enqueue("chat", "First")
    jobs.claim("chat")
    jobs = TextQueue(queue)
    assert jobs.claim("chat")["job_id"] == first
    jobs.finish(first, "sending")
    jobs = TextQueue(queue)
    with pytest.raises(AgentError, match="uncertain"):
        jobs.claim("chat")
    assert jobs.claim("other chat") is None


def test_text_llm_request_has_no_images_and_vision_is_not_required(config):
    config.llm_url, config.llm_model = "https://llm.test", "text-model"
    config.llm_supports_vision = False
    settings = LLMSettings.resolve(config, {}, require_vision=False)
    calls = []

    def api(request):
        body = json.loads(request.content)
        calls.append(body)
        assert (
            "image_url" not in request.content.decode() and "base64" not in request.content.decode()
        )
        assert isinstance(body["messages"][1]["content"], str)
        content = (
            json.dumps(dict(kind="incoming", text="안녕하세요", sender="", is_ai=False))
            if len(calls) == 1
            else "안녕하세요!"
        )
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        )

    llm = IncomingLLM(settings, "synthetic-key", httpx.MockTransport(api))
    incoming = llm.classify_text("테스터: 안녕하세요", threading.Event())
    assert llm.answer(incoming, threading.Event()) == "[AI] 안녕하세요!"
    assert len(calls) == 2
