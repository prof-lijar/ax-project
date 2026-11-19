"""Continuously capture changed frames while one queued vision/reply job runs."""

import time
from dataclasses import replace
from uuid import uuid4

from app.api.incoming_llm import create_incoming_llm
from app.api.workflow_llm import check_cancel
from app.automation.text_auto_catch import TextAutoCatchWorkflow, chat_queue_key
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import AgentError
from app.storage.image_reply_queue import ImageReplyQueue


class QueuedVisualCatchWorkflow(TextAutoCatchWorkflow):
    continue_after_submission = True
    extraction_progress = "Extracting new message text from queued capture; watching continues"

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
        llm_factory=create_incoming_llm,
        clock=time.monotonic,
        text_preview=lambda _: None,
    ):
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
            text_preview=text_preview,
            jobs_factory=ImageReplyQueue,
        )

    def arm(self):
        self.reset()
        check_cancel(self.cancel)
        self.llm = self.llm_factory(self.config)
        if self.config.selection is None:
            self.config.selection = self.desktop.suggest_chat_region()
            self.progress("Run Agent (auto) detected the message area above the typing box")
        if not self.config.chat_id:
            self.config.chat_id = "chat-" + uuid4().hex[:12]
        self.original_identity = self.identity()
        self.desktop.activate_target(self.cancel)
        self.check()
        self.chat_key = chat_queue_key(self.config)
        frame, _ = self.capture.grab()
        self.check()
        self.detector = ChangeDetector(
            replace(
                self.config,
                change_detection=True,
                difference_threshold=self.config.incoming_difference_threshold,
                debounce_seconds=0.3,
                max_debounce_seconds=1,
            )
        )
        self.accept(frame, encode_png(frame))
        self.preview(self.baseline)
        self.text_preview("")
        self.queue.event(
            "auto_visual_armed", "Initial screen ignored; existing queued screenshot pairs retained"
        )
        self.progress(f"Watching display changes continuously; local captures: {self.jobs.images}")
        self.active = True

    def collect(self):
        frame, _ = self.capture.grab()
        self.check()
        if not self.detector.ready(frame, self.clock()):
            return
        png = encode_png(frame)
        job_id, path = self.jobs.enqueue_pair(self.chat_key, self.baseline, png)
        self.check()
        self.accept(frame, png)
        self.preview(png)
        self.queue.event("auto_visual_queued", job_id)
        self.progress(f"Display change captured and queued: {path}")
        self.progress(
            f"{self.jobs.count(self.chat_key)} capture(s) queued or processing; watching continues"
        )

    def begin_job(self, job):
        # Read/verify files before assigning the active job, so a missing image stays
        # marked for review rather than being reset to pending by Stop.
        before, after = self.jobs.load_images(job)
        super().begin_job(dict(job, before_png=before, after_png=after))

    def send_queued_reply(self, reply):
        return self.sender.send(reply, require_empty=True)

    def analyze_job(self, llm, job, cancel):
        return llm.classify(job["before_png"], job["after_png"], cancel, batch=True)

    def tick(self):
        self.check()
        if not self.active:
            raise AgentError("Run Agent (auto) is not armed")
        self.ensure_foreground()
        # Capture is independent of inference and reply cooldown. Sending is still
        # serialized on this thread; no keyboard/mouse actions run concurrently.
        self.collect()
        self.finish_job()
        if self.worker is None and self.job is None and self.clock() >= self.next_reply_at:
            job = self.jobs.claim(self.chat_key)
            if job is not None:
                self.begin_job(job)
        self.waiting_reason = f"Watching screenshots; {self.jobs.count(self.chat_key)} queued; {self.reply_count} replies submitted"
        return None
