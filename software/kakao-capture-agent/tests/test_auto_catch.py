from types import SimpleNamespace

import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.automation.monitoring_service import MonitoringService
from app.capture.screen_capture import encode_png
from app.config import Config, load, save
from app.models import AgentError, Selection, State, TargetUnavailable
from tests.test_automation import Capture, Desktop


@pytest.fixture
def watching(config, queue, frame, region):
    config.selection = None
    config.chat_id = ""
    desktop = Desktop(region)
    desktop.activate_target = lambda cancel=None: desktop.validate()
    selections = []

    def suggest():
        selections.append(True)
        return Selection(region, 300, 300, 96)

    desktop.suggest_chat_region = suggest
    capture = Capture(desktop, frame)
    logs, sent, comparisons = [], [], []
    now = [0]
    service = MonitoringService(
        desktop, capture, queue, config, lambda *a: None, lambda *a: None, logs.append
    )
    workflow = service.auto_catch
    workflow.clock = lambda: now[0]

    class LLM:
        outcome = IncomingMessage("incoming", "질문", "Tester")

        def classify(self, before, after, cancel, *, batch=False):
            assert batch
            comparisons.append((before, after))
            return self.outcome

        def answer(self, incoming, cancel):
            return "[AI] 답변"

    llm = LLM()
    workflow.llm_factory = lambda _: llm
    workflow.sender = SimpleNamespace(
        send=lambda text: sent.append(text) or "send requested", composer_cleared=True
    )
    service.dispatch("auto_catch")
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
        selections=selections,
    )


def changed(w):
    w.capture.frame = 255 - w.capture.frame
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()


def test_window_only_setup_and_continuous_replies(watching):
    w = watching
    assert w.selections == [True]
    assert w.service.config.selection and w.service.config.chat_id.startswith("chat-")
    assert w.service.state == State.AUTO_CATCHING
    w.now[0] = 3600  # No five-minute one-shot waiting deadline.
    w.service.poll_auto_catch()
    assert not w.comparisons and not w.sent
    changed(w)
    assert w.sent == ["[AI] 답변 (자동 응답)"]
    assert w.service.state == State.AUTO_CATCHING and w.workflow.active
    assert w.workflow.reply_count == 1 and not w.service.stop_input.is_set()
    assert not w.service.want_live and not w.desktop.calls
    w.llm.outcome = IncomingMessage("incoming", "Another question", "Other participant")
    w.now[0] += 4
    changed(w)
    assert len(w.sent) == 2 and w.workflow.reply_count == 2
    files = list(w.queue.images.glob("*.png"))
    assert len(files) == 2 and w.queue.claim(w.service.config.api_url) is None
    assert any(str(files[0]) in line for line in w.logs)
    assert w.service.state == State.AUTO_CATCHING


def test_messages_arriving_during_inference_remain_comparable(watching):
    w = watching

    def send(text):
        w.sent.append(text)
        w.capture.frame = (
            255 - w.capture.frame
        )  # Another arrival while handling the previous frame.
        return "send requested"

    w.workflow.sender.send = send
    changed(w)
    assert w.workflow.baseline == w.comparisons[0][1]
    assert w.workflow.baseline != encode_png(w.capture.frame)
    w.llm.outcome = IncomingMessage("incoming", "Arrived during inference", "Tester")
    w.now[0] += 4
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()
    assert len(w.sent) == 2
    assert w.comparisons[1][0] == w.comparisons[0][1]


@pytest.mark.parametrize(
    "kind,text",
    [
        ("outgoing", "reply"),
        ("none", ""),
        ("incoming", "[AI] answer"),
        ("incoming", "[test] result"),
    ],
)
def test_outgoing_and_generated_messages_do_not_loop(watching, kind, text):
    w = watching
    w.llm.outcome = IncomingMessage(kind, text)
    changed(w)
    assert not w.sent and len(w.comparisons) == 1
    w.service.poll_auto_catch()
    assert len(w.comparisons) == 1 and w.workflow.active


def test_duplicate_guard_and_cooldown(watching):
    w = watching
    changed(w)
    w.capture.frame = 255 - w.capture.frame
    w.service.poll_auto_catch()
    assert len(w.comparisons) == 1  # Cooldown does not advance the baseline.
    w.now[0] += 4
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()
    assert len(w.comparisons) == 2 and len(w.sent) == 1  # Same OCR ignored within 60 seconds.
    w.now[0] += 61
    changed(w)
    assert len(w.sent) == 2  # A later repeated question is allowed.


def test_duplicate_cache_expires_and_is_bounded(watching):
    w = watching
    for index in range(260):
        w.llm.outcome = IncomingMessage("incoming", f"question {index}")
        # Exercise the real insert/eviction path without waiting or capturing 260 PNGs.
        w.now[0] += 0.01
        w.workflow.next_reply_at = 0
        w.workflow.detector.ready = lambda *a: True
        w.queue.enqueue = lambda *a, **kw: "synthetic"
        w.service.poll_auto_catch()
    assert len(w.workflow.recent) == 256
    w.now[0] += 61
    assert not w.workflow.seen_recently("missing")
    assert not w.workflow.recent


@pytest.mark.parametrize(
    "failure",
    [
        "cancel",
        "retarget",
        "hidden",
        "network",
        "storage",
        "answer_cancel",
        "send",
        "submission_uncertain",
    ],
)
def test_interruptions_pause_without_rearming(watching, failure, monkeypatch):
    w = watching
    if failure == "cancel":
        w.service.command("stop")
    elif failure == "retarget":
        w.service.config.chat_id = "other"
    elif failure == "hidden":
        w.desktop.valid = False
    elif failure == "submission_uncertain":
        w.workflow.sender.composer_cleared = False
    elif failure == "answer_cancel":

        def answer(*a):
            w.service.command("stop")
            return "[AI] cancelled"

        w.llm.answer = answer
    else:

        def fail(*a, **kw):
            raise AgentError("Simulated failure")

        target, method = {
            "network": (w.llm, "classify"),
            "storage": (w.queue, "enqueue"),
            "send": (w.workflow.sender, "send"),
        }[failure]
        monkeypatch.setattr(target, method, fail)
    with pytest.raises(AgentError) as error:
        changed(w)
    w.service.pause(error.value)
    assert len(w.sent) == (1 if failure == "submission_uncertain" else 0)
    assert w.service.state == State.PAUSED
    assert not w.workflow.active and not w.service.recoverable and not w.service.want_live
    assert w.service.stop_input.is_set()


def test_target_lost_during_model_call_blocks_reply(watching):
    w = watching

    def classify(*args, **kw):
        w.desktop.valid = False
        return IncomingMessage("incoming", "new text")

    w.llm.classify = classify
    with pytest.raises(TargetUnavailable):
        changed(w)
    assert not w.sent


@pytest.mark.parametrize("kind", ["invalid_format", "uncertain"])
def test_analysis_retry_keeps_baseline_and_later_replies_without_rearming(watching, kind):
    w = watching
    baseline = w.workflow.baseline
    original = w.llm.classify

    def incomplete(*a, **kw):
        if kind == "uncertain":
            return IncomingMessage("uncertain")
        raise IncomingAnalysisError("Synthetic invalid JSON")

    w.llm.classify = incomplete
    changed(w)
    assert w.workflow.active and w.service.state == State.AUTO_CATCHING
    assert w.workflow.baseline == baseline and not w.sent and not w.workflow.recent
    assert "checking again in 2s" in w.service.reason
    assert not list(w.queue.images.glob("*.png"))
    w.llm.classify = original
    w.service.poll_auto_catch()
    assert not w.comparisons  # Backoff, no repeated LLM request at the poll interval.
    w.now[0] += 2
    w.service.poll_auto_catch()  # Same pixels must still be eligible, without a new message.
    assert w.comparisons[0][0] == baseline
    assert w.sent == ["[AI] 답변 (자동 응답)"] and w.workflow.reply_count == 1
    assert w.workflow.analysis_failures == 0 and not w.workflow.waiting_reason


def test_repeated_analysis_failure_is_rate_limited_and_stop_cancels(watching):
    w = watching
    baseline = w.workflow.baseline
    w.llm.outcome = IncomingMessage("uncertain")
    changed(w)
    for delay in [4, 8, 16, 30, 30]:
        w.now[0] = w.workflow.next_analysis_at
        w.service.poll_auto_catch()
        assert w.workflow.next_analysis_at - w.now[0] == delay
        assert w.workflow.baseline == baseline and not w.sent
    w.service.command("stop")
    with pytest.raises(AgentError):
        w.service.poll_auto_catch()
    assert not w.sent


@pytest.mark.parametrize("failure", ["cancel", "retarget", "hidden"])
def test_failed_analysis_does_not_bypass_target_and_cancel_checks(watching, failure):
    w = watching

    def classify(*a, **kw):
        if failure == "cancel":
            w.service.command("stop")
        elif failure == "retarget":
            w.service.config.chat_id = "other"
        else:
            w.desktop.valid = False
        raise IncomingAnalysisError("Invalid analysis")

    w.llm.classify = classify
    with pytest.raises(AgentError):
        changed(w)
    assert not w.sent and w.workflow.analysis_failures == 0


def test_typing_then_bad_analysis_then_incoming_plain_reply(watching):
    import base64
    import json

    import httpx

    from app.api.incoming_llm import IncomingLLM
    from app.api.workflow_llm import LLMSettings

    w = watching
    requests, before_images = [], []
    outcomes = [
        '{"kind":"none","text":"","sender":"","is_ai":false}',
        "unusable analysis",
        '{"kind":"incoming","text":"2 더하기 2는?","sender":"테스트","is_ai":false}',
        "4입니다.",
        '{"kind":"outgoing","text":"[AI] 4입니다.","sender":"","is_ai":true}',
    ]

    def api(request):
        body = json.loads(request.content)
        requests.append(body)
        if "response_format" in body:
            image = body["messages"][1]["content"][1]["image_url"]["url"]
            before_images.append(base64.b64decode(image.split(",")[1]))
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": outcomes.pop(0)}}]},
        )

    w.workflow.llm = IncomingLLM(
        LLMSettings("https://llm.test", "vision", 5), "synthetic-key", httpx.MockTransport(api)
    )
    changed(w)  # Only typing dots: no answer, continue watching.
    typing_baseline = w.workflow.baseline
    assert not w.sent and any("typing/UI" in line for line in w.logs)
    changed(w)  # Actual text arrives, but the first analysis is malformed.
    assert not w.sent and w.workflow.baseline == typing_baseline
    w.now[0] += 2
    w.service.poll_auto_catch()  # No new frame needed for recovery.
    assert before_images[1] == before_images[2] == typing_baseline
    assert w.sent == ["[AI] 4입니다. (자동 응답)"]
    w.now[0] += 4
    changed(w)  # Our outgoing reply is visible: do not answer it.
    assert len(w.sent) == 1 and not outcomes and len(requests) == 5
    assert w.workflow.active and w.service.state == State.AUTO_CATCHING
    assert len(list(w.queue.images.glob("*.png"))) == 1


def test_stop_then_rearm_keeps_selected_region_and_ignores_existing(watching):
    w = watching
    changed(w)
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    assert not w.workflow.active and not w.workflow.recent
    assert w.service.state == State.STOPPED
    w.service.dispatch("auto_catch")
    w.service.poll_auto_catch()
    assert w.selections == [True]  # Saved/manual selection is respected.
    assert len(w.sent) == 1 and len(w.comparisons) == 1


@pytest.mark.parametrize("suffix", ["", "(Auto reply)", "(자동 응답)"])
def test_reply_suffix(watching, suffix):
    w = watching
    w.service.config.auto_reply_suffix = suffix
    changed(w)
    assert w.sent == ["[AI] 답변" + (" " + suffix if suffix else "")]


def test_new_config_defaults_and_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"version":1,"chat_id":"old"}')
    config = load(path)
    assert config.auto_reply_suffix == "(자동 응답)" and config.auto_catch_interval_seconds == 0.5
    config.auto_reply_suffix = "(Auto reply)"
    config.auto_catch_interval_seconds = 0.25
    save(path, config)
    assert load(path).auto_reply_suffix == "(Auto reply)"
    assert load(path).auto_catch_interval_seconds == 0.25


@pytest.mark.parametrize(
    "field,value",
    [
        ("auto_reply_suffix", "x" * 101),
        ("auto_reply_suffix", "a\nb"),
        ("auto_catch_interval_seconds", 0),
        ("auto_catch_interval_seconds", float("nan")),
        ("auto_reply_cooldown_seconds", 0),
    ],
)
def test_auto_config_rejects_invalid_values(field, value):
    config = Config()
    setattr(config, field, value)
    with pytest.raises(ValueError):
        config.validate()


def lose_focus(w, *, denied=False):
    from app.models import Cancelled, ForegroundLost

    focus = {"foreground": False, "denied": denied, "attempts": 0}
    original_validate = w.desktop.validate

    def validate():
        region = original_validate()
        if not focus["foreground"]:
            raise ForegroundLost("Bring the selected conversation to the foreground")
        return region

    def activate(cancel):
        if cancel.is_set():
            raise Cancelled("Stopped")
        original_validate()
        focus["attempts"] += 1
        if focus["denied"]:
            raise ForegroundLost("Windows denied focus")
        focus["foreground"] = True

    w.desktop.validate = validate
    w.desktop.activate_target = activate
    return focus


def test_auto_catch_restores_focus_and_processes_incoming_without_rearming(watching):
    w = watching
    baseline = w.workflow.baseline
    focus = lose_focus(w)
    changed(w)
    assert focus["attempts"] == 1
    assert w.comparisons[0][0] == baseline
    assert len(w.sent) == 1 and w.service.state == State.AUTO_CATCHING
    assert w.workflow.reply_count == 1


def test_focus_lost_during_classification_is_restored_before_reply(watching):
    w = watching
    focus = lose_focus(w)
    focus["foreground"] = True
    original = w.llm.classify

    def classify(*args, **kwargs):
        focus["foreground"] = False
        return original(*args, **kwargs)

    w.llm.classify = classify
    changed(w)
    assert focus["attempts"] == 1 and len(w.sent) == 1


def test_denied_focus_retries_preserve_baseline_and_duplicate_guard(watching):
    from app.models import ForegroundLost

    w = watching
    changed(w)
    baseline, recent = w.workflow.baseline, dict(w.workflow.recent)
    focus = lose_focus(w, denied=True)
    w.now[0] += 4
    w.capture.frame = 255 - w.capture.frame
    with pytest.raises(ForegroundLost) as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    assert w.service.auto_focus_recovery and w.workflow.active
    assert w.service.state == State.PAUSED and not w.service.stop_input.is_set()
    assert not w.service.recoverable  # This must never start normal live scrolling.
    log_count = len(w.logs)
    for _ in range(2):
        with pytest.raises(ForegroundLost) as error:
            w.service.try_recover_auto_focus()
        w.service.pause(error.value)
    assert len(w.logs) == log_count  # Quiet waiting, not repeated state churn.
    assert w.workflow.baseline == baseline and dict(w.workflow.recent) == recent
    assert len(w.sent) == 1 and not w.desktop.calls
    focus["denied"] = False
    w.service.try_recover_auto_focus()
    assert w.service.state == State.AUTO_CATCHING and not w.service.auto_focus_recovery
    assert w.workflow.baseline == baseline and dict(w.workflow.recent) == recent
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()
    assert len(w.sent) == 1  # Previously handled text cannot replay after focus recovery.


@pytest.mark.parametrize("action", ["stop", "reserve_other_action", "shutdown"])
def test_stop_or_new_action_cancels_pending_focus_recovery(watching, action):
    from app.models import ForegroundLost

    w = watching
    focus = lose_focus(w, denied=True)
    with pytest.raises(ForegroundLost) as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    attempts = focus["attempts"]
    if action == "stop":
        w.service.command("stop")
    elif action == "reserve_other_action":
        w.service.suspend_recovery()
    else:
        w.service.shutdown.set()
    focus["denied"] = False
    w.service.try_recover_auto_focus()
    assert focus["attempts"] == attempts and not w.sent
    if action != "shutdown":
        assert w.service.stop_input.is_set() and not w.service.auto_focus_recovery


@pytest.mark.parametrize("reason", ["locked", "minimized", "covered", "retargeted"])
def test_non_focus_failure_during_recovery_stops_auto_catch(watching, reason):
    from app.models import ForegroundLost, ReselectionRequired

    w = watching
    lose_focus(w, denied=True)
    with pytest.raises(ForegroundLost) as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)

    def invalid(cancel):
        if reason == "retargeted":
            raise ReselectionRequired("Changed window identity")
        raise TargetUnavailable(reason)

    w.desktop.activate_target = invalid
    with pytest.raises(AgentError) as error:
        w.service.try_recover_auto_focus()
    w.service.pause(error.value)
    assert not w.service.auto_focus_recovery and not w.workflow.active
    assert w.service.stop_input.is_set() and not w.sent


def test_focus_failure_inside_send_never_retries_submission(watching):
    from app.models import ForegroundLost

    w = watching
    attempts = []

    def send(text):
        attempts.append(text)
        raise ForegroundLost("Focus lost during sending")

    w.workflow.sender.send = send
    with pytest.raises(ForegroundLost) as error:
        changed(w)
    w.service.pause(error.value)
    assert len(attempts) == 1 and not w.service.auto_focus_recovery
    w.service.try_recover_auto_focus()
    assert len(attempts) == 1 and w.service.stop_input.is_set()


def test_real_worker_recovers_focus_then_answers_and_stops(config, queue, frame, region):
    import threading

    import numpy as np

    from app.models import ForegroundLost, Selection

    desktop = Desktop(region)
    config.selection = Selection(region, 300, 300, 96)
    config.auto_catch_interval_seconds = 0.25
    foreground = [True]
    attempts = []

    def validate():
        if not foreground[0]:
            raise ForegroundLost("Foreground lost")
        return region

    def activate(cancel):
        attempts.append(True)
        foreground[0] = True

    desktop.validate, desktop.activate_target = validate, activate
    capture = Capture(desktop, frame)
    started, sent = threading.Event(), threading.Event()

    def status(state, reason):
        if state == State.AUTO_CATCHING.value:
            started.set()

    service = MonitoringService(
        desktop, capture, queue, config, status, lambda _: None, lambda _: None
    )
    service.auto_catch.llm_factory = lambda _: SimpleNamespace(
        classify=lambda *a, **kw: IncomingMessage("incoming", "New text"),
        answer=lambda *a: "[AI] Reply",
    )

    def send(text):
        sent.set()
        return "send requested"

    service.auto_catch.sender = SimpleNamespace(send=send, composer_cleared=True)
    service.start()
    try:
        service.command("auto_catch")
        assert started.wait(2)
        foreground[0] = False
        capture.frame = np.zeros_like(frame)
        assert sent.wait(3)
        assert len(attempts) >= 2  # Startup and automatic focus recovery.
        service.command("stop")
    finally:
        service.shutdown.set()
        service.command("stop")
        service.join(3)
    assert not service.is_alive()
