import hashlib
import json
import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.api.workflow_llm import check_cancel
from app.automation.monitoring_service import MonitoringService
from app.capture.screen_capture import encode_png
from app.models import AgentError, ForegroundLost, Selection, State, StorageFull
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.text_queue import TextQueue
from tests.test_automation import Capture, Desktop


@pytest.fixture
def watching(config, queue, region):
    desktop = Desktop(region)
    desktop.activate_target = lambda cancel: desktop.validate()
    desktop.suggest_chat_region = lambda: Selection(region, 300, 300, 96)
    config.selection = None
    frame = np.zeros((100, 80, 3), dtype=np.uint8)
    capture = Capture(desktop, frame)
    sent, comparisons, logs, extracted, stages = [], [], [], [], []
    now = [0]
    service = MonitoringService(
        desktop, capture, queue, config, lambda *a: None, lambda png: None, logs.append
    )
    workflow = service.auto_catch
    workflow.text_preview = extracted.append
    workflow.clock = lambda: now[0]
    workflow.text_reader.read = lambda *a: (_ for _ in ()).throw(
        AssertionError("Native text must not be used")
    )

    class LLM:
        def classify(self, before, after, cancel, *, batch):
            assert batch
            check_cancel(cancel)
            comparisons.append((before, after))
            marker = int(cv2.imdecode(np.frombuffer(after, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0])
            stages.append(("extract", marker))
            if marker == 10:
                return IncomingMessage("none")
            if marker == 220:
                return IncomingMessage("outgoing", "[AI] own reply")
            return IncomingMessage("incoming", f"Question {marker}", "Tester")

        def answer(self, incoming, cancel):
            check_cancel(cancel)
            stages.append(("process", incoming.text))
            return "[AI] " + incoming.text

    llm = LLM()
    workflow.llm_factory = lambda _: llm

    def send(text, **kwargs):
        stages.append(("reply", text))
        sent.append(text)
        return "composer cleared"

    workflow.sender = SimpleNamespace(send=send, composer_cleared=True)
    service.dispatch("auto_catch")
    yield SimpleNamespace(
        service=service,
        workflow=workflow,
        queue=queue,
        capture=capture,
        desktop=desktop,
        llm=llm,
        sent=sent,
        comparisons=comparisons,
        now=now,
        logs=logs,
        extracted=extracted,
        stages=stages,
    )
    service.command("stop")
    workflow.reset()


def changed(w, marker):
    w.capture.frame = np.full_like(w.capture.frame, marker)
    w.service.poll_auto_catch()
    w.now[0] += 0.5
    w.service.poll_auto_catch()


def finish(w):
    if w.workflow.worker:
        w.workflow.worker.join(2)
        assert not w.workflow.worker.is_alive()
    w.service.poll_auto_catch()


def test_continues_after_first_reply_and_ignores_typing_and_own_reply(watching):
    w = watching
    assert w.service.config.selection and not w.comparisons
    changed(w, 10)  # Typing indicator only.
    finish(w)
    assert not w.sent
    changed(w, 30)
    finish(w)
    assert w.sent == ["[AI] Question 30 (자동 응답)"]
    # Collection continues during reply cooldown.
    changed(w, 220)
    assert w.workflow.jobs.count(w.workflow.chat_key) == 1
    w.now[0] += 4
    w.service.poll_auto_catch()
    finish(w)
    assert len(w.sent) == 1
    changed(w, 50)
    finish(w)
    assert len(w.sent) == 2 and w.workflow.reply_count == 2
    assert w.service.state == State.AUTO_CATCHING and w.workflow.active
    assert w.workflow.jobs.count(w.workflow.chat_key) == 0
    assert list(w.workflow.jobs.images.glob("*.png"))
    assert w.queue.claim(w.service.config.api_url) is None  # Never ordinary upload jobs.
    assert any(str(w.workflow.jobs.images) in line for line in w.logs)


@pytest.mark.parametrize("blocked_stage", ["extraction", "processing"])
def test_capture_and_durable_fifo_continue_during_slow_llm(watching, blocked_stage):
    w = watching
    entered, release = threading.Event(), threading.Event()
    original_extract, original_answer = w.llm.classify, w.llm.answer

    def wait_for_release(incoming, cancel):
        if incoming.text == "Question 30":
            entered.set()
            while not release.wait(0.01):
                check_cancel(cancel)

    def slow_extract(before, after, cancel, *, batch):
        incoming = original_extract(before, after, cancel, batch=batch)
        wait_for_release(incoming, cancel)
        return incoming

    def slow_answer(incoming, cancel):
        wait_for_release(incoming, cancel)
        return original_answer(incoming, cancel)

    if blocked_stage == "extraction":
        w.llm.classify = slow_extract
    else:
        w.llm.answer = slow_answer
    changed(w, 30)
    assert entered.wait(1)
    changed(w, 60)
    changed(w, 90)
    assert len(w.comparisons) == 1 and not w.sent
    assert w.workflow.jobs.count(w.workflow.chat_key) == 3
    assert len(list(w.workflow.jobs.images.glob("*.png"))) == 4  # Shared adjacent baselines.
    with w.queue.connect() as db:
        rows = db.execute("SELECT text,status FROM image_reply_queue ORDER BY id").fetchall()
    assert [r["status"] for r in rows] == ["processing", "pending", "pending"]
    release.set()
    finish(w)
    for _ in range(2):
        w.now[0] += 4
        w.service.poll_auto_catch()
        finish(w)
    assert w.sent == [f"[AI] Question {m} (자동 응답)" for m in (30, 60, 90)]
    assert w.comparisons[1][0] == w.comparisons[0][1]
    assert w.comparisons[2][0] == w.comparisons[1][1]
    assert w.extracted == ["", "Question 30", "Question 60", "Question 90"]
    assert w.stages == [
        stage
        for marker in (30, 60, 90)
        for stage in (
            ("extract", marker),
            ("process", f"Question {marker}"),
            ("reply", f"[AI] Question {marker} (자동 응답)"),
        )
    ]
    assert sum("Extracting new message text" in line for line in w.logs) == 3
    assert sum("Text extracted; processing with the LLM" in line for line in w.logs) == 3
    assert sum("LLM reply ready" in line for line in w.logs) == 3
    assert w.workflow.jobs.count(w.workflow.chat_key) == 0
    assert w.service.state == State.AUTO_CATCHING


def test_stop_retains_images_and_pending_work_for_explicit_rearm(watching):
    w = watching
    entered = threading.Event()
    original = w.llm.answer

    def slow(incoming, cancel):
        entered.set()
        cancel.wait(2)
        check_cancel(cancel)
        raise AssertionError("Stop must interrupt generation")

    w.llm.answer = slow
    changed(w, 30)
    assert entered.wait(1)
    changed(w, 60)
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    assert not w.sent and len(list(w.workflow.jobs.images.glob("*.png"))) == 3
    with w.queue.connect() as db:
        assert [r[0] for r in db.execute("SELECT status FROM image_reply_queue")] == [
            "pending",
            "pending",
        ]
    w.llm.answer = original
    w.service.dispatch("auto_catch")
    w.service.poll_auto_catch()
    finish(w)
    w.now[0] += 4
    w.service.poll_auto_catch()
    finish(w)
    assert w.sent == ["[AI] Question 30 (자동 응답)", "[AI] Question 60 (자동 응답)"]


def test_sustained_arrivals_all_reply_while_queue_drains(watching):
    w = watching
    entered, release = threading.Event(), threading.Event()
    original = w.llm.answer

    def first_answer_waits(incoming, cancel):
        if not entered.is_set():
            entered.set()
            while not release.wait(0.01):
                check_cancel(cancel)
        return original(incoming, cancel)

    w.llm.answer = first_answer_waits
    # Repeated question text is intentional: distinct later captures must still
    # receive replies. The running agent has no message-count stopping condition.
    markers = [30, 60, 90, 120, 150, 180, 210, 240] * 4
    changed(w, markers[0])
    assert entered.wait(1)
    for marker in markers[1:8]:
        changed(w, marker)
    assert not w.sent and w.workflow.jobs.count(w.workflow.chat_key) == 8
    release.set()
    finish(w)

    # Keep receiving new changes while earlier queued jobs are replying.
    for marker in markers[8:]:
        w.now[0] += 4
        changed(w, marker)
        finish(w)
        assert w.workflow.jobs.count(w.workflow.chat_key) > 0
        assert w.service.state == State.AUTO_CATCHING

    # Bounded test loop only; the production watcher runs until Stop.
    for _ in markers:
        if w.workflow.jobs.count(w.workflow.chat_key) == 0:
            break
        w.now[0] += 4
        w.service.poll_auto_catch()
        finish(w)
    assert w.sent == [f"[AI] Question {marker} (자동 응답)" for marker in markers]
    assert len(w.comparisons) == w.workflow.reply_count == len(markers)
    assert w.workflow.jobs.count(w.workflow.chat_key) == 0
    assert w.workflow.active and w.service.state == State.AUTO_CATCHING
    with w.queue.connect() as db:
        assert db.execute("SELECT count(*) FROM image_reply_queue WHERE status='sent'").fetchone()[
            0
        ] == len(markers)


def test_uncertain_send_never_replays_and_later_captures_remain(watching):
    w = watching
    changed(w, 30)
    w.workflow.worker.join(2)
    # Collect a later change without finishing the prepared send.
    w.capture.frame[:] = 60
    w.workflow.collect()
    w.now[0] += 0.5
    w.workflow.collect()

    def partial_send(text, **kwargs):
        w.sent.append(text)
        raise AgentError("Input insertion uncertain")

    w.workflow.sender.send = partial_send
    with pytest.raises(AgentError, match="uncertain") as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    jobs = ImageReplyQueue(w.queue)
    with pytest.raises(AgentError, match="uncertain"):
        jobs.claim(w.workflow.chat_key)
    assert len(w.sent) == 1 and jobs.count(w.workflow.chat_key) == 2
    w.service.dispatch("stop")
    w.service.dispatch("auto_catch")
    with pytest.raises(AgentError, match="click Review Replies") as blocked:
        w.service.poll_auto_catch()
    w.service.pause(blocked.value)
    assert w.service.state == State.PAUSED and len(w.sent) == 1
    jobs.resolve_review(w.workflow.chat_key)
    w.workflow.sender.send = lambda text, **kw: w.sent.append(text) or "composer cleared"
    w.service.dispatch("stop")
    w.service.dispatch("auto_catch")
    w.service.poll_auto_catch()
    finish(w)
    assert w.sent == ["[AI] Question 30 (자동 응답)", "[AI] Question 60 (자동 응답)"]
    assert w.service.state == State.AUTO_CATCHING


def test_bad_analysis_retries_same_pair_while_new_frames_queue(watching):
    w = watching
    original = w.llm.classify
    w.llm.classify = lambda *a, **kw: (_ for _ in ()).throw(IncomingAnalysisError("invalid"))
    changed(w, 30)
    finish(w)
    changed(w, 60)
    assert not w.sent and w.workflow.jobs.count(w.workflow.chat_key) == 2
    with w.queue.connect() as db:
        db.execute("UPDATE image_reply_queue SET next_attempt=0")
    w.llm.classify = original
    w.service.poll_auto_catch()
    finish(w)
    assert w.sent == ["[AI] Question 30 (자동 응답)"]


def test_focus_recovery_retains_prepared_vision_reply(watching):
    w = watching
    changed(w, 30)
    w.workflow.worker.join(2)
    original = w.workflow.ensure_foreground
    calls = [0]

    def denied():
        calls[0] += 1
        if calls[0] == 2:
            raise ForegroundLost("temporarily denied")
        original()

    w.workflow.ensure_foreground = denied
    with pytest.raises(ForegroundLost) as error:
        w.service.poll_auto_catch()
    w.service.pause(error.value)
    w.workflow.ensure_foreground = original
    w.service.try_recover_auto_focus()
    finish(w)
    assert len(w.sent) == 1 and len(w.comparisons) == 1


def test_storage_failure_does_not_advance_baseline(watching):
    w = watching
    before = w.workflow.baseline
    w.service.config.storage_limit_bytes = 1
    with pytest.raises(StorageFull):
        changed(w, 30)
    assert w.workflow.baseline == before and not w.sent and not w.comparisons


def test_images_survive_restart_and_are_isolated_from_text_queue(queue, frame):
    jobs = ImageReplyQueue(queue)
    before, after = encode_png(frame), encode_png(255 - frame)
    first, _ = jobs.enqueue_pair("chat", before, after)
    jobs.claim("chat")
    TextQueue(queue).enqueue("chat", "Old native text must not be replayed")
    jobs = ImageReplyQueue(queue)
    row = jobs.claim("chat")
    assert row["job_id"] == first and jobs.load_images(row) == [before, after]
    assert jobs.claim("different chat") is None
    jobs.finish(first, "sending")
    jobs = ImageReplyQueue(queue)
    with pytest.raises(AgentError, match="uncertain"):
        jobs.claim("chat")


@pytest.mark.parametrize("failure", ["missing", "modified", "metadata"])
def test_invalid_image_job_requires_review_before_any_llm_call(queue, frame, failure):
    jobs = ImageReplyQueue(queue)
    job_id, path = jobs.enqueue_pair("chat", encode_png(frame), encode_png(255 - frame))
    if failure == "missing":
        path.unlink()
    elif failure == "modified":
        path.write_bytes(b"changed")
    else:
        with queue.connect() as db:
            db.execute(
                "UPDATE image_reply_queue SET text=? WHERE job_id=?",
                (
                    json.dumps(
                        {"before": "../../private", "after": hashlib.sha256(b"x").hexdigest()}
                    ),
                    job_id,
                ),
            )
    row = jobs.claim("chat")
    with pytest.raises(AgentError, match="review"):
        jobs.load_images(row)
    with pytest.raises(AgentError, match="Review Replies"):
        jobs.claim("chat")


def test_retention_preserves_pending_pair_when_completed_pair_expires(queue, frame):
    import os
    import time

    jobs = ImageReplyQueue(queue)
    before, shared, latest = encode_png(frame), encode_png(255 - frame), encode_png(frame // 2)
    first, _ = jobs.enqueue_pair("chat", before, shared)
    second, _ = jobs.enqueue_pair("chat", shared, latest)
    jobs.finish(first, "sent")
    old = time.time() - (queue.config.metadata_retention_days + 1) * 86400
    with queue.connect() as db:
        db.execute("UPDATE image_reply_queue SET created_at=?", (old,))
    for path in jobs.images.glob("*.png"):
        os.utime(path, (old, old))
    jobs = ImageReplyQueue(queue)
    row = jobs.claim("chat")
    assert row["job_id"] == second
    assert jobs.load_images(row) == [shared, latest]
    assert len(list(jobs.images.glob("*.png"))) == 2


def test_atomic_image_write_failure_creates_no_queue_job(queue, frame, monkeypatch):
    jobs = ImageReplyQueue(queue)
    monkeypatch.setattr(
        "app.storage.image_reply_queue.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("disk write failed")),
    )
    with pytest.raises(OSError, match="disk write failed"):
        jobs.enqueue_pair("chat", encode_png(frame), encode_png(255 - frame))
    assert jobs.count("chat") == 0
    assert list(jobs.images.iterdir()) == []


@pytest.mark.parametrize("clears", [True, False])
def test_unobserved_submission_continues_but_next_send_requires_empty_composer(watching, clears):
    from app.automation.reply_service import TestReplySender as ReplySender
    from app.models import SubmissionObservation
    from tests.test_replies import Composer

    w = watching
    composer = Composer()

    def submit(handle):
        composer.submits.append(handle)
        if clears:
            composer.text = ""

    composer.submit = submit
    composer.observe_submission = lambda *a: SubmissionObservation("Synthetic readback unavailable")
    w.workflow.sender = ReplySender(composer, w.queue.event, w.service.stop_input)
    changed(w, 30)
    finish(w)
    assert w.service.state == State.AUTO_CATCHING
    assert w.workflow.reply_count == 1 and len(composer.submits) == 1
    assert any("Watching continues; this reply will not be resent" in line for line in w.logs)
    with w.queue.connect() as db:
        assert db.execute("SELECT status FROM image_reply_queue").fetchone()[0] == "submitted"
    # A subsequent incoming change queues normally even if observation failed.
    w.now[0] += 4
    changed(w, 60)
    if clears:
        finish(w)
        assert w.workflow.reply_count == 2 and len(composer.submits) == 2
        assert [text for _, text in composer.writes] == [
            "[AI] Question 30 (자동 응답)",
            "[AI] Question 60 (자동 응답)",
        ]
        jobs = ImageReplyQueue(w.queue)
        assert jobs.claim(w.workflow.chat_key) is None  # No replay, including after restart.
    else:
        with pytest.raises(AgentError, match="not empty") as blocked:
            finish(w)
        w.service.pause(blocked.value)
        assert len(composer.submits) == 1 and len(composer.writes) == 1
        assert composer.text == "[AI] Question 30 (자동 응답)"
        with w.queue.connect() as db:
            assert [
                r[0] for r in db.execute("SELECT status FROM image_reply_queue ORDER BY id")
            ] == ["submitted", "pending"]
        # Clearing the draft and explicitly restarting must process the untouched
        # job without forcing review or replaying the previous submission.
        composer.text = ""
        w.service.dispatch("stop")
        w.service.dispatch("auto_catch")
        w.service.poll_auto_catch()
        finish(w)
        assert w.service.state == State.AUTO_CATCHING
        assert len(composer.submits) == 2
        assert composer.writes[-1][1] == "[AI] Question 60 (자동 응답)"


def test_partial_draft_write_still_requires_review(watching):
    from app.automation.reply_service import TestReplySender as ReplySender
    from tests.test_replies import Composer

    w = watching
    composer = Composer()

    def partial_write(handle, text):
        composer.text = text[:5]
        raise AgentError("Draft write interrupted")

    composer.write = partial_write
    w.workflow.sender = ReplySender(composer, w.queue.event, w.service.stop_input)
    changed(w, 30)
    with pytest.raises(AgentError, match="interrupted") as blocked:
        finish(w)
    w.service.pause(blocked.value)
    assert composer.text and not composer.submits
    with pytest.raises(AgentError, match="Review Replies"):
        w.workflow.jobs.claim(w.workflow.chat_key)
