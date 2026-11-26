import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.api.operations_client import OperationsResult
from app.automation.unified_workflow import UnifiedProcessor, UnifiedWorkflow
from app.models import AgentError, ForegroundLost, State, StorageFull
from tests.test_queued_visual_catch import changed, finish, watching  # noqa: F401

MESSAGE = "위치조정/이영희/광명시 OO동 OO로 56"


@pytest.fixture
def agent(watching):  # noqa: F811
    w = watching
    w.service.dispatch("stop")
    workflow = UnifiedWorkflow(
        w.desktop, w.capture, w.queue, w.service.config, w.sender, w.service.stop_input,
        lambda _: None, w.service.primary_progress, llm_factory=lambda _: w.llm,
        clock=lambda: w.now[0],
    )
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult("completed", "API reply", True)))
    workflow.processor_factory = lambda: UnifiedProcessor(workflow.journal, operations)
    w.llm.classify_latest = Mock(return_value=IncomingMessage("none"))
    w.llm.classify = Mock(return_value=IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,)))
    w.service.auto_catch = w.service.general_auto_catch = w.workflow = workflow
    w.operations = operations
    w.service.dispatch("auto_catch")
    finish(w)
    yield w
    w.service.dispatch("stop")


def test_restart_archives_two_reviews_then_checks_same_latest_frame(agent):
    w = agent
    w.service.dispatch("stop")
    for marker in (b"old1", b"old2"):
        job, _ = w.workflow.jobs.enqueue_pair(w.workflow.chat_key, marker, marker)
        w.workflow.jobs.finish(job, "review")
    w.llm.classify_latest.return_value = IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,))
    w.service.dispatch("auto_catch")
    finish(w)
    assert w.sent == ["API reply"]
    assert w.workflow.jobs.review_count(w.workflow.chat_key) == 0
    assert any("archived 2 old review capture(s)" in line for line in w.logs)
    assert not any("2 capture(s) set aside" in line for line in w.logs)


def test_failed_screen_after_first_reply_preserves_unprocessed_message_for_next_change(agent):
    w = agent
    changed(w, 30)
    finish(w)
    assert w.sent == ["API reply"]
    verified = w.workflow.verified_baseline
    # Exercise exhausted screening without spending six seconds in retry backoff.
    w.workflow.screen = w.workflow.read_action
    w.llm.classify.side_effect = IncomingAnalysisError("unclear", category="ambiguous direction")
    w.now[0] += 4
    w.capture.frame[:] = 60
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()
    if w.workflow.screening is not None:
        with pytest.raises(IncomingAnalysisError):
            w.workflow.screening.result(timeout=2)
    w.service.poll_auto_catch()
    assert w.workflow.verified_baseline == verified
    assert w.workflow.screening is None
    assert any("keeping the previous message baseline" in line for line in w.logs)
    # An unchanged failed image must not create an endless OCR loop.
    attempts = w.llm.classify.call_count
    w.service.poll_auto_catch()
    assert w.llm.classify.call_count == attempts
    w.llm.classify.side_effect = None
    changed(w, 90)
    finish(w)
    assert w.llm.classify.call_args.args[0] == verified
    assert w.sent == ["API reply", "API reply"]
    assert w.operations.run.call_count == 2
    assert w.service.state == State.AUTO_CATCHING


def test_outgoing_reply_then_identical_followup_request_still_runs(agent):
    w = agent
    changed(w, 30)
    finish(w)
    w.llm.classify.return_value = IncomingMessage("outgoing", "API reply")
    changed(w, 60)
    finish(w)
    w.now[0] += 4
    w.llm.classify.return_value = IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,))
    changed(w, 90)
    finish(w)
    assert w.sent == ["API reply", "API reply"]
    assert w.service.state == State.AUTO_CATCHING
    assert any("no incoming action keyword found" in line for line in w.logs)


def test_failed_startup_rechecks_latest_message_on_next_display_change(agent):
    w = agent
    w.service.dispatch("stop")
    w.workflow.screen = w.workflow.read_action
    w.llm.classify_latest.side_effect = IncomingAnalysisError("unclear")
    w.service.dispatch("auto_catch")
    if w.workflow.screening is not None:
        with pytest.raises(IncomingAnalysisError):
            w.workflow.screening.result(timeout=2)
    w.service.poll_auto_catch()
    assert w.workflow.retry_startup
    w.llm.classify_latest.side_effect = None
    w.llm.classify_latest.return_value = IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,))
    changed(w, 30)
    finish(w)
    assert w.sent == ["API reply"]
    assert not w.workflow.retry_startup
    w.llm.classify.assert_not_called()


def test_screening_status_updates_while_waiting_without_log_spam(agent):
    import threading

    w = agent
    entered, release = threading.Event(), threading.Event()
    statuses = []
    w.service.status = lambda state, reason: statuses.append((state, reason))

    def classify(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return IncomingMessage("none")

    w.llm.classify.side_effect = classify
    try:
        w.capture.frame[:] = 30
        w.service.poll_auto_catch()
        w.now[0] += 0.5
        w.service.poll_auto_catch()
        assert entered.wait(1)
        w.service.poll_auto_catch()
        assert "Checking incoming action keywords" in w.service.reason
        count = len(w.logs)
        w.workflow.screen_snapshot = (
            w.workflow.screen_snapshot[0], False, w.workflow.screen_snapshot[2] - 10
        )
        w.service.poll_auto_catch()
        assert "(10s)" in statuses[-1][1]
        assert len(w.logs) == count
    finally:
        release.set()
        finish(w)


@pytest.mark.parametrize("first_api_fails", [False, True])
def test_burst_during_slow_screening_and_api_only_queues_keyword_requests(agent, first_api_fails):
    w = agent
    reading, release_read = threading.Event(), threading.Event()
    executing, release_api = threading.Event(), threading.Event()
    comparisons = []
    messages = [f"위치조정/이영희/광명시 OO동 OO로 {i}" for i in range(10, 201, 10)]

    def classify(before, after, *args, **kwargs):
        markers = [int(cv2.imdecode(np.frombuffer(p, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0])
                   for p in (before, after)]
        comparisons.append(markers)
        marker = markers[1]
        if marker == 5:
            reading.set()
            assert release_read.wait(5)
        text = messages[marker // 10 - 1] if marker % 10 == 0 else "감사합니다. 좋은 하루 보내세요."
        return IncomingMessage("incoming", text, bubbles=(text,))

    def run(request, cancel):
        if request["message"] == messages[0]:
            executing.set()
            assert release_api.wait(5)
            if first_api_fails:
                raise AgentError("API request timed out; outcome uncertain")
        return OperationsResult("completed", request["message"], True)

    w.llm.classify.side_effect = classify
    w.operations.run.side_effect = run
    try:
        for marker in range(5, 201, 5):
            w.capture.frame = np.full_like(w.capture.frame, 255 if marker % 10 else 0)
            w.capture.frame[0, 0] = marker
            w.service.poll_auto_catch()
            w.now[0] += 0.5
            w.service.poll_auto_catch()
        assert reading.wait(1)
        assert len(w.workflow.pending_screens) == 39
        assert w.workflow.jobs.count(w.workflow.chat_key) == 0
        assert not list(w.workflow.jobs.images.rglob("*.png"))
        release_read.set()
        for _ in range(45):
            if w.workflow.screening is not None:
                w.workflow.screening.result(timeout=2)
            w.service.poll_auto_catch()
            if w.workflow.screening is None:
                break
        assert executing.wait(1)
        assert comparisons == [[i - 5, i] for i in range(5, 201, 5)]
        assert w.workflow.jobs.count(w.workflow.chat_key) == 20
        assert not w.sent
        with w.queue.connect() as db:
            rows = db.execute("SELECT incoming FROM image_reply_queue WHERE chat_key=? ORDER BY id",
                              (w.workflow.chat_key,)).fetchall()
        assert [json.loads(row[0])["text"] for row in rows] == messages
        assert len(list(w.workflow.jobs.images.rglob("*.png"))) == 20
        release_api.set()
        for _ in range(45):
            w.now[0] += 4
            finish(w)
            if w.workflow.jobs.count(w.workflow.chat_key) == 0:
                break
        assert w.sent == messages[int(first_api_fails):]
        assert w.operations.run.call_count == 20
        assert w.workflow.jobs.count(w.workflow.chat_key) == 0
        assert not w.workflow.pending_screens and w.workflow.pending_screen_bytes == 0
        assert w.service.state == State.AUTO_CATCHING
    finally:
        release_read.set()
        release_api.set()


def test_temporary_frame_limit_does_not_consume_unstored_change_and_stop_clears_frames(agent):
    w = agent
    release = threading.Event()
    w.workflow.max_screen_frames = 2

    def classify(*args, **kwargs):
        assert release.wait(3)
        return IncomingMessage("none")

    w.llm.classify.side_effect = classify
    try:
        for marker in (30, 60):
            w.capture.frame = np.full_like(w.capture.frame, marker)
            w.service.poll_auto_catch()
            w.now[0] += 0.5
            w.service.poll_auto_catch()
        baseline = w.workflow.baseline
        w.capture.frame[:] = 90
        w.service.poll_auto_catch()
        w.now[0] += 0.5
        with pytest.raises(StorageFull, match="temporary frame limit"):
            w.service.poll_auto_catch()
        assert w.workflow.baseline == baseline
        assert w.workflow.jobs.count(w.workflow.chat_key) == 0
        w.service.dispatch("stop")
        assert not w.workflow.pending_screens and w.workflow.pending_screen_bytes == 0
        assert w.workflow.screening is None
    finally:
        release.set()


def test_focus_loss_during_send_preparation_keeps_reply_without_repeating_api(agent):
    w = agent
    original = w.workflow.sender.send
    attempts = []

    def send(text, **kwargs):
        attempts.append(text)
        w.workflow.sender.input_started = False
        if len(attempts) == 1:
            raise ForegroundLost("Activation temporarily denied before typing")
        w.workflow.sender.input_started = True
        return original(text, **kwargs)

    w.workflow.sender.send = send
    with pytest.raises(ForegroundLost) as error:
        changed(w, 30)
        finish(w)
    w.service.pause(error.value)
    assert w.service.auto_focus_recovery and w.workflow.active
    assert not w.sent
    w.service.try_recover_auto_focus()
    finish(w)
    assert w.sent == ["API reply"]
    assert w.operations.run.call_count == 1
    assert w.workflow.jobs.review_count(w.workflow.chat_key) == 0
    assert w.service.state == State.AUTO_CATCHING
