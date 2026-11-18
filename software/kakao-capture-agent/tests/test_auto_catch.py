from types import SimpleNamespace

import pytest

from app.api.incoming_llm import IncomingMessage
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
        "uncertain",
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
    elif failure == "uncertain":
        w.llm.outcome = IncomingMessage("uncertain")
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
