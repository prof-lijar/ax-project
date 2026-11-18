"""Continuous visual incoming-message replies, explicitly armed by the operator."""

import hashlib
import unicodedata
from collections import OrderedDict
from dataclasses import replace
from uuid import uuid4

from app.api.incoming_llm import automated_text
from app.api.workflow_llm import check_cancel
from app.automation.incoming_workflow import IncomingReplyWorkflow
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import AgentError, ForegroundLost


class AutoCatchWorkflow(IncomingReplyWorkflow):
    def reset(self):
        super().reset()
        self.recent = OrderedDict()
        self.reply_count = 0
        self.next_reply_at = 0

    def check(self):
        check_cancel(self.cancel)
        if self.identity() != self.original_identity:
            raise AgentError("Auto Catch target changed; stopped without replying")

    def ensure_foreground(self):
        """Recover focus only, without resetting the incoming-message baseline."""
        self.check()
        try:
            self.desktop.validate()
        except ForegroundLost:
            self.progress("Auto Catch: activating the selected chat to continue watching")
            self.check()
            self.desktop.activate_target(self.cancel)
            self.check()
            self.desktop.validate()

    def arm(self):
        self.reset()
        check_cancel(self.cancel)
        self.llm = self.llm_factory(self.config)
        if self.config.selection is None:
            self.config.selection = self.desktop.suggest_chat_region()
            self.progress("Auto Catch detected the area above the message box")
        if not self.config.chat_id:
            self.config.chat_id = "chat-" + uuid4().hex[:12]
        self.original_identity = self.identity()
        self.desktop.activate_target(self.cancel)
        self.check()
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
        self.queue.event(
            "auto_catch_armed", "Continuous replies explicitly armed; initial text ignored"
        )
        self.active = True

    def accept(self, frame, png):
        self.baseline = png
        self.detector.accept(frame)

    def fingerprint(self, incoming):
        # Bounded, short-lived guard against repeat OCR of the same visible message.
        normalized = [
            " ".join(unicodedata.normalize("NFKC", s).split())
            for s in (incoming.sender, incoming.text)
        ]
        return hashlib.sha256("\0".join(normalized).encode("utf-8")).hexdigest()

    def seen_recently(self, fingerprint):
        now = self.clock()
        while self.recent and next(iter(self.recent.values())) <= now:
            self.recent.popitem(last=False)
        return fingerprint in self.recent

    def tick(self):
        self.check()
        if not self.active:
            raise AgentError("Auto Catch is not armed; no automatic retry")
        self.ensure_foreground()
        if self.clock() < self.next_reply_at:
            return None
        frame, region = self.capture.grab()
        self.check()
        if not self.detector.ready(frame, self.clock()):
            return None
        png = encode_png(frame)
        self.preview(png)
        self.progress("Auto Catch: identifying new incoming text")
        incoming = self.llm.classify(self.baseline, png, self.cancel, batch=True)
        self.check()
        self.ensure_foreground()
        if incoming.kind == "uncertain":
            raise AgentError("Auto Catch could not verify incoming text; stopped without replying")
        fingerprint = self.fingerprint(incoming)
        if (
            incoming.kind != "incoming"
            or automated_text(incoming.text)
            or self.seen_recently(fingerprint)
        ):
            self.accept(frame, png)
            self.queue.event("auto_catch_ignored", "Outgoing, cosmetic, or recently handled change")
            return None
        # Mark this attempt BEFORE inference/input. Errors require explicit rearming.
        self.active = False
        self.recent[fingerprint] = self.clock() + 60
        while len(self.recent) > 256:
            self.recent.popitem(last=False)
        capture_id = self.queue.enqueue(png, region, "live", local_only=True)
        self.progress(f"Auto Catch saved locally: {self.queue.images / (capture_id + '.png')}")
        self.progress("Auto Catch: generating an [AI] reply")
        reply = self.llm.answer(incoming, self.cancel)
        self.check()
        suffix = self.config.auto_reply_suffix.strip()
        if suffix:
            reply += " " + suffix
        result = self.sender.send(reply)
        self.check()
        self.queue.event("auto_catch_reply", capture_id + ": " + result)
        if not self.sender.composer_cleared:
            raise AgentError(
                "Auto Catch reply submission is uncertain; stopped to prevent duplicate replies. "
                "Inspect the chat before restarting."
            )
        # Keep the PRE-REPLY frame as baseline. A post-send reset would swallow incoming
        # messages that arrived during inference. The next comparison ignores our [AI] bubble.
        self.accept(frame, png)
        self.reply_count += 1
        self.next_reply_at = self.clock() + self.config.auto_reply_cooldown_seconds
        self.active = True
        return None
