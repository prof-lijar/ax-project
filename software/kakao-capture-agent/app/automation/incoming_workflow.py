"""An explicitly armed, one-shot visual incoming-message test."""

import time
from dataclasses import replace

from app.api.incoming_llm import create_incoming_llm
from app.api.workflow_llm import check_cancel
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import AgentError


class IncomingReplyWorkflow:
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
    ):
        self.desktop, self.capture, self.queue, self.config = desktop, capture, queue, config
        self.sender, self.cancel, self.preview, self.progress = sender, cancel, preview, progress
        self.llm_factory, self.clock = llm_factory, clock
        self.reset()

    def reset(self):
        self.active = False
        self.baseline = self.detector = self.llm = None

    def identity(self):
        return self.config.target, self.config.selection, self.config.chat_id

    def check(self):
        check_cancel(self.cancel)
        if self.identity() != self.original_identity:
            raise AgentError("Workflow 2 target changed; no reply sent")

    def arm(self):
        self.reset()
        check_cancel(self.cancel)
        self.llm = self.llm_factory(self.config)
        self.original_identity = self.identity()
        self.desktop.activate_target(self.cancel)
        self.check()
        frame, _ = self.capture.grab()
        self.check()
        self.baseline = encode_png(frame)
        self.preview(self.baseline)
        self.detector = ChangeDetector(
            replace(
                self.config,
                change_detection=True,
                difference_threshold=self.config.incoming_difference_threshold,
                debounce_seconds=1,
                max_debounce_seconds=3,
            )
        )
        self.detector.accept(frame)
        self.deadline = self.clock() + self.config.incoming_wait_timeout_seconds
        self.queue.event(
            "incoming_armed", "Baseline recorded; waiting for one new incoming message"
        )
        self.active = True

    def tick(self):
        self.check()
        if not self.active:
            raise AgentError("Workflow 2 is not armed; no automatic retry")
        if self.clock() >= self.deadline:
            self.active = False
            return "Workflow 2 waiting limit reached; no reply sent"
        frame, region = self.capture.grab()
        self.check()
        if not self.detector.ready(frame, self.clock()):
            return None
        png = encode_png(frame)
        self.preview(png)
        self.progress("Workflow 2: checking whether changed pixels contain a new incoming message")
        incoming = self.llm.classify(self.baseline, png, self.cancel)
        self.check()
        self.desktop.validate()
        if self.clock() >= self.deadline:
            self.active = False
            return "Workflow 2 waiting limit reached during analysis; no reply sent"
        if incoming.kind == "uncertain":
            raise AgentError(
                "Workflow 2 could not verify a new incoming message; stopped without replying"
            )
        if incoming.kind != "incoming":
            self.baseline = png
            self.detector.accept(frame)
            self.queue.event("incoming_ignored", incoming.kind)
            return None
        # Consume the one-shot before generation or sending: neither may be retried.
        self.active = False
        capture_id = self.queue.enqueue(png, region, "live", local_only=True)
        self.progress(
            f"Incoming capture saved locally: {self.queue.images / (capture_id + '.png')}"
        )
        self.queue.event("incoming_capture", capture_id)
        self.progress("Workflow 2: generating one [AI] reply")
        reply = self.llm.answer(incoming, self.cancel)
        self.check()
        if self.clock() >= self.deadline:
            return "Workflow 2 waiting limit reached during reply generation; no reply sent"
        # The sender independently reactivates and verifies the exact target/composer.
        result = self.sender.send(reply)
        self.queue.event("incoming_finished", capture_id + ": " + result)
        return "Workflow 2: " + result
