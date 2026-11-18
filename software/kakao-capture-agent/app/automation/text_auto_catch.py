"""Continuous native-text collection with a durable FIFO and one background LLM job."""

import hashlib
import json
import queue as queues
import threading
import time
from uuid import uuid4

from app.api.incoming_llm import IncomingAnalysisError, automated_text, create_text_llm
from app.api.workflow_llm import check_cancel
from app.automation.auto_catch import AutoCatchWorkflow
from app.automation.text_changes import appended_text
from app.automation.windows_chat_text import WindowsChatText
from app.models import AgentError
from app.storage.text_queue import TextQueue


def chat_queue_key(config):
    target = config.target
    identity = {
        "chat_id": config.chat_id,
        "title": getattr(target, "title", ""),
        "executable": getattr(target, "executable", ""),
        "class_name": getattr(target, "window_class", ""),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class TextAutoCatchWorkflow(AutoCatchWorkflow):
    def __init__(
        self,
        desktop,
        capture,
        queue,
        config,
        sender,
        cancel,
        preview,
        progress,
        llm_factory=create_text_llm,
        clock=time.monotonic,
        text_reader=None,
        text_preview=lambda _: None,
        jobs_factory=TextQueue,
    ):
        self.jobs = jobs_factory(queue)
        self.text_reader = text_reader or WindowsChatText(desktop, progress)
        self.text_preview = text_preview
        super().__init__(
            desktop,
            capture,
            queue,
            config,
            sender,
            cancel,
            preview,
            progress,
            llm_factory=llm_factory,
            clock=clock,
        )

    def reset(self):
        if getattr(self, "work_cancel", None) is not None:
            self.work_cancel.set()
        worker = getattr(self, "worker", None)
        if worker is not None:
            worker.join(timeout=0.3)
        job = getattr(self, "job", None)
        if job is not None and not getattr(self, "sending", False):
            self.jobs.finish(job["job_id"], "pending")
        self.worker = self.job = self.results = self.work_cancel = self.outcome = None
        self.sending = False
        self.pending_text = None
        self.text_key = None
        super().reset()

    def arm(self):
        self.reset()
        check_cancel(self.cancel)
        self.llm = self.llm_factory(self.config)
        if self.config.selection is None:
            # Geometry only. No screenshot capture is invoked.
            self.config.selection = self.desktop.suggest_chat_region()
        if not self.config.chat_id:
            self.config.chat_id = "chat-" + uuid4().hex[:12]
        self.original_identity = self.identity()
        self.desktop.activate_target(self.cancel)
        self.check()
        self.chat_key = chat_queue_key(self.config)
        snapshot = self.text_reader.read(self.cancel)
        self.check()
        self.baseline, self.text_key = snapshot.text, snapshot.key
        self.text_preview(snapshot.text[-4000:])
        self.progress(
            f"Text source ready: {snapshot.source}; {len(snapshot.text)} characters; no screenshots"
        )
        self.queue.event("auto_text_armed", "Existing text ignored; pending text jobs retained")
        self.active = True

    def collect(self):
        snapshot = self.text_reader.read(self.cancel)
        self.check()
        if snapshot.key != self.text_key:
            raise AgentError("Accessible conversation control changed; reselect the chat")
        if snapshot.text == self.baseline:
            self.pending_text = None
            return
        now = self.clock()
        if self.pending_text is None:
            self.pending_since = now
        if self.pending_text != snapshot.text:
            self.pending_text, self.stable_since = snapshot.text, now
        if now - self.stable_since < 0.3 and now - self.pending_since < 1:
            return
        added = appended_text(self.baseline, snapshot.text)
        if added:
            job_id = self.jobs.enqueue(self.chat_key, added)
            self.queue.event("auto_text_queued", job_id)
            self.progress(
                f"Incoming text queued: {self.jobs.count(self.chat_key)} batch(es) awaiting completion"
            )
        self.baseline = snapshot.text
        self.pending_text = None
        self.text_preview(snapshot.text[-4000:])

    def analyze_job(self, llm, job, cancel):
        return llm.classify_text(job["text"], cancel)

    def begin_job(self, job):
        self.job = job
        self.work_cancel = threading.Event()
        self.results = queues.Queue(maxsize=1)
        # Capture immutable references so Stop/rearming cannot redirect an old worker.
        llm, cancel, results = self.llm, self.work_cancel, self.results
        analyze = self.analyze_job

        def process():
            try:
                incoming = analyze(llm, job, cancel)
                check_cancel(cancel)
                if incoming.kind == "uncertain":
                    raise IncomingAnalysisError(
                        "Incoming message cannot yet be separated from UI/outgoing activity"
                    )
                reply = None
                if incoming.kind == "incoming" and not automated_text(incoming.text):
                    reply = llm.answer(incoming, cancel)
                check_cancel(cancel)
                results.put((reply, None))
            except Exception as error:
                results.put((None, error))

        self.worker = threading.Thread(target=process, name="auto-text-llm", daemon=False)
        self.worker.start()
        self.progress("Processing queued messages with the LLM; collection continues")

    def finish_job(self):
        if self.outcome is None and (self.worker is None or self.worker.is_alive()):
            return
        if self.outcome is None:
            self.outcome = self.results.get_nowait()
            self.worker = None
        reply, error = self.outcome
        self.check()
        if isinstance(error, IncomingAnalysisError):
            delay = self.jobs.retry(self.job["job_id"])
            self.job = self.outcome = None
            self.progress(f"Message analysis needs another check in {delay}s; collection continues")
            return
        if error is not None:
            if isinstance(error, AgentError):
                raise error
            raise AgentError("LLM processing failed; queued work retained") from None
        if reply is None:
            self.jobs.finish(self.job["job_id"], "ignored")
            self.job = self.outcome = None
            self.progress("UI activity or outgoing/AI text ignored; watching for incoming text")
            return
        self.ensure_foreground()
        suffix = self.config.auto_reply_suffix.strip()
        if suffix:
            reply += " " + suffix
        self.jobs.finish(self.job["job_id"], "sending")  # Durable BEFORE touching the composer.
        self.sending, self.active = True, False
        try:
            observation = self.sender.send(reply)
            self.check()
            if not self.sender.composer_cleared:
                raise AgentError(
                    "Reply send is uncertain; inspect the chat and use Review Replies. Queued messages retained"
                )
            self.jobs.finish(self.job["job_id"], "sent")
        except Exception:
            self.jobs.finish(self.job["job_id"], "review")
            raise
        self.queue.event("auto_reply", self.job["job_id"] + ": " + observation)
        self.job = self.outcome = None
        self.sending, self.active = False, True
        self.reply_count += 1
        self.next_reply_at = self.clock() + self.config.auto_reply_cooldown_seconds
        self.progress(f"Reply submitted; {self.jobs.count(self.chat_key)} job(s) remain queued")

    def tick(self):
        self.check()
        if not self.active:
            raise AgentError("Auto Catch is not armed")
        self.ensure_foreground()
        # Always collect first, even during LLM inference and reply cooldown.
        self.collect()
        self.finish_job()
        if self.worker is None and self.job is None and self.clock() >= self.next_reply_at:
            job = self.jobs.claim(self.chat_key)
            if job is not None:
                self.begin_job(job)
        self.waiting_reason = f"Reading chat text; {self.jobs.count(self.chat_key)} queued; {self.reply_count} replies submitted"
        return None
