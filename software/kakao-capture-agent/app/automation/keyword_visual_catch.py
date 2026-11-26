"""Read changed frames in memory before admitting incoming actions to the reply queue."""

import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage, automated_text
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import extract_sources, installation_header, kakao_command
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import StorageFull
from app.storage.chat_paths import chat_folder_name


class KeywordVisualCatchWorkflow(QueuedVisualCatchWorkflow):
    extraction_progress = "Processing a queued action message; watching continues"
    extracted_progress = "Action text extracted"
    max_screen_frames = 128
    max_screen_bytes = 64 * 1024 * 1024

    def __init__(self, *args, api_response=lambda _: None, **kwargs):
        self.api_response = api_response
        super().__init__(*args, **kwargs)

    def observe_operations(self, operations):
        title = self.config.target.title if self.config.target else ""
        callback = self.api_response
        operations.response_observer = lambda event: callback({"chat": title, **event})
        return operations

    def reset(self):
        if getattr(self, "screen_cancel", None) is not None:
            self.screen_cancel.set()
            self.reader.shutdown(wait=False, cancel_futures=True)
        self.screen_cancel = self.screening = self.screen_snapshot = None
        self.verified_baseline = None
        self.retry_startup = False
        self.pending_screens = deque()
        self.pending_screen_bytes = 0
        super().reset()

    def read_action(self, llm, before, after, startup, cancel):
        check_cancel(cancel)
        if startup:
            incoming = llm.classify_latest(after, cancel)
        else:
            incoming = llm.classify(before, after, cancel, batch="bubbles")
        if incoming.kind == "uncertain":
            raise IncomingAnalysisError("Unclear message", category="ambiguous direction")
        return self.matching_incoming(llm, incoming, startup, cancel)

    def screen(self, llm, before, after, startup, cancel):
        for attempt in range(1, self.jobs.max_analysis_attempts + 1):
            try:
                return self.read_action(llm, before, after, startup, cancel)
            except IncomingAnalysisError:
                if attempt == self.jobs.max_analysis_attempts:
                    raise
                cancel.wait(2 ** attempt)

    def matching_incoming(self, llm, incoming, startup, cancel):
        if incoming.kind != "incoming":
            return None
        sources = incoming.bubbles or (incoming.text,)
        if not incoming.bubbles and not startup and len(incoming.text.strip().splitlines()) > 1:
            if automated_text(incoming.text) or not any(
                self.action_keyword(line) for line in incoming.text.splitlines()
            ):
                return None
            sources = extract_sources(llm, incoming, cancel)
            if list(sources) != [incoming.text] and any(
                installation_header(text) or kakao_command(text) for text in sources
            ):
                raise IncomingAnalysisError("Unclear command boundaries")
        indices = [i for i, text in enumerate(sources)
                   if not automated_text(text) and self.action_keyword(text)]
        if not indices:
            return None
        bubbles = tuple(sources[i] for i in indices)
        senders = tuple(incoming.bubble_senders[i] for i in indices) if incoming.bubble_senders else ()
        return replace(incoming, text="\n\n".join(bubbles), bubbles=bubbles, bubble_senders=senders,
                       sender=incoming.sender if len(sources) == 1 else "")

    def start_screen(self, before, after, *, startup=False, captured_at=None):
        if self.verified_baseline is None:
            self.verified_baseline = before
        if self.screen_cancel is None:
            self.screen_cancel = threading.Event()
            self.reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-keyword")
        self.screen_snapshot = after, startup, time.time() if captured_at is None else captured_at
        self.progress("Checking the latest visible message" if startup else
                      "Display change detected; checking for incoming action keywords")
        self.screening = self.reader.submit(self.screen, self.llm, before, after, startup, self.screen_cancel)

    def observe_change(self, before, after):
        # Continue observing during slow OCR. These bounded, temporary frames
        # are not workflow jobs and are never saved unless an action matches.
        active_bytes = len(self.screen_snapshot[0]) if self.screen_snapshot else 0
        if (len(self.pending_screens) + int(self.screening is not None) >= self.max_screen_frames
                or self.pending_screen_bytes + active_bytes + len(after) > self.max_screen_bytes):
            raise StorageFull("Message screening cannot keep up; temporary frame limit reached; capture paused")
        if self.screening is not None:
            self.pending_screens.append((after, time.time()))
            self.pending_screen_bytes += len(after)
            return
        # The detector tracks observed pixels; OCR comparisons must start at the
        # last successfully screened frame, not a frame whose analysis failed.
        self.start_screen(self.verified_baseline or before, after, startup=self.retry_startup)

    def advance_screen(self):
        self.screening = self.screen_snapshot = None
        if self.pending_screens:
            self.check()
            after, captured_at = self.pending_screens.popleft()
            self.pending_screen_bytes -= len(after)
            self.start_screen(self.verified_baseline, after, startup=self.retry_startup,
                              captured_at=captured_at)

    def finish_screen(self):
        if self.screening is None or not self.screening.done():
            return
        after, startup, captured_at = self.screen_snapshot
        try:
            incoming = self.screening.result()
        except IncomingAnalysisError as error:
            self.progress(
                f"Could not verify an incoming action after three checks ({error.category}); "
                "keeping the previous message baseline for the next display change"
            )
            self.retry_startup = startup
            self.advance_screen()
            return
        self.check()
        if incoming is not None:
            job_id, path = self.jobs.enqueue_pair(
                self.chat_key, after, after, mode="latest" if startup else "changes",
                folder=chat_folder_name(self.config), fresh_start=startup,
                incoming=asdict(incoming), captured_at=captured_at,
            )
            self.on_action_queued(job_id)
            self.queue.event("auto_visual_queued", job_id)
            self.progress(f"Incoming action queued: {path}")
        else:
            self.progress(
                "Latest visible message: no incoming action keyword found; waiting for a new message"
                if startup else
                "Display change: no incoming action keyword found (outgoing, UI, or non-action text); watching continues"
            )
        self.verified_baseline = after
        self.retry_startup = False
        self.advance_screen()

    def on_action_queued(self, job_id):
        pass

    def capture_changes(self):
        self.check()
        self.finish_screen()
        # Desktop observation continues while one frame at a time is screened.
        # Only keyword matches are admitted to the persistent workflow queue.
        super().capture_changes()

    def process_queue(self):
        self.finish_screen()
        super().process_queue()
        if self.screening is not None:
            elapsed = max(0, int(time.time() - self.screen_snapshot[2]))
            self.waiting_reason = (
                f"Checking incoming action keywords ({elapsed}s); "
                f"{len(self.pending_screens)} temporary frame(s) awaiting screening; " + self.waiting_reason
            )

    def analyze_job(self, llm, job, cancel):
        if job.get("incoming"):
            data = json.loads(job["incoming"])
            data["bubbles"] = tuple(data["bubbles"])
            data["bubble_senders"] = tuple(data["bubble_senders"])
            return IncomingMessage(**data)
        # Already-queued captures from earlier builds still pass the same gate.
        startup = json.loads(job["text"]).get("mode") == "latest"
        return self.read_action(
            llm, job["before_png"], job["after_png"], startup, cancel
        ) or IncomingMessage("none")
