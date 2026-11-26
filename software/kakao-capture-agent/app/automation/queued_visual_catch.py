"""Continuously capture changed frames while one queued vision/reply job runs."""

import time
from dataclasses import replace
from uuid import uuid4

from app.api.incoming_llm import RUN_AGENT_GREETING, create_incoming_llm
from app.api.workflow_llm import check_cancel
from app.automation.text_auto_catch import TextAutoCatchWorkflow
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import AgentError
from app.storage.chat_paths import chat_directory, chat_folder_name, chat_queue_key
from app.storage.image_reply_queue import CaptureReviewRequired, ImageReplyQueue


class QueuedVisualCatchWorkflow(TextAutoCatchWorkflow):
    greeting = RUN_AGENT_GREETING
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
        jobs_factory=ImageReplyQueue,
        rotating_windows=False,
    ):
        self.rotating_windows = rotating_windows
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
            jobs_factory=jobs_factory,
        )

    def reset(self):
        super().reset()
        self.reported_review_count = None

    def report_review(self):
        count = self.jobs.review_count(self.chat_key)
        if count != self.reported_review_count:
            self.reported_review_count = count
            if count:
                self.progress(
                    f"{count} capture(s) set aside for review; no automatic resend. "
                    "Watching and processing other captures continues"
                )
        return count

    def queue_key(self):
        return chat_queue_key(self.config)

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
        self.chat_key = self.queue_key()
        frame, _ = self.capture.grab()
        self.check()
        self.detector = ChangeDetector(
            replace(
                self.config,
                change_detection=True,
                difference_threshold=self.config.incoming_difference_threshold,
                # In a rotation the next visit can be several messages later.
                debounce_seconds=0 if self.rotating_windows else 0.3,
                max_debounce_seconds=1,
            )
        )
        self.accept(frame, encode_png(frame))
        self.preview(self.baseline)
        self.text_preview("")
        if self.greeting:
            # Preserve the baseline if a participant responds during a greeting.
            self.progress("Sending the startup message once; replacing message-box contents")
            self.check()
            observation = self.sender.send(self.greeting, require_empty=False)
            self.check()
            self.queue.event("auto_agent_greeting", observation)
            self.progress("Startup message submitted once; " + observation)
        self.queue_initial_capture()
        self.report_review()
        directory = chat_directory(self.jobs.images, chat_folder_name(self.config))
        self.progress(f"Watching display changes continuously; local captures: {directory}")
        self.active = True

    def enqueue_capture(self, before, after, *, mode="changes"):
        return self.jobs.enqueue_pair(
            self.chat_key, before, after, mode=mode, folder=chat_folder_name(self.config)
        )

    def queue_initial_capture(self):
        self.queue.event(
            "auto_visual_armed", "Initial screen ignored; existing queued screenshot pairs retained"
        )

    def collect(self):
        frame, _ = self.capture.grab()
        self.check()
        if not self.detector.ready(frame, self.clock()):
            return
        png = encode_png(frame)
        self.observe_change(self.baseline, png)
        self.check()
        self.accept(frame, png)
        self.preview(png)

    def observe_change(self, before, after):
        job_id, path = self.enqueue_capture(before, after)
        self.queue.event("auto_visual_queued", job_id)
        self.progress(f"Display change captured and queued: {path}")
        self.progress(
            f"{self.jobs.count(self.chat_key)} capture(s) queued or processing; watching continues"
        )

    def begin_job(self, job):
        if job["chat_key"] != self.chat_key:
            raise AgentError("Queued capture belongs to another chat; stopped without replying")
        # Read/verify files before assigning the active job, so a missing image stays
        # marked for review rather than being reset to pending by Stop.
        try:
            before, after = self.jobs.load_images(job)
        except CaptureReviewRequired as error:
            self.queue.event("auto_visual_review", job["job_id"] + ": " + str(error))
            self.progress(str(error) + "; watching continues")
            return
        super().begin_job(dict(job, before_png=before, after_png=after))

    def send_queued_reply(self, reply):
        return self.sender.send(reply, require_empty=False)

    def analyze_job(self, llm, job, cancel):
        return llm.classify(job["before_png"], job["after_png"], cancel, batch=True)

    def capture_changes(self):
        self.check()
        if not self.active:
            raise AgentError("Run Agent (auto) is not armed")
        self.ensure_foreground()
        # Capture is independent of inference and reply cooldown. Sending is still
        # serialized on this thread; no keyboard/mouse actions run concurrently.
        self.collect()

    def process_queue(self):
        self.check()
        self.finish_job()
        if self.worker is None and self.job is None and self.clock() >= self.next_reply_at:
            job = self.jobs.claim(self.chat_key)
            if job is not None:
                self.begin_job(job)
        reviews = self.report_review()
        self.waiting_reason = (
            f"Watching screenshots; {self.jobs.count(self.chat_key)} queued; "
            f"{reviews} set aside for review; {self.reply_count} replies submitted"
        )

    def tick(self):
        self.capture_changes()
        self.process_queue()
