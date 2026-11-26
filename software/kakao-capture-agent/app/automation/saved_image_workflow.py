"""One saved capture → the existing AX768 workflow → output, without desktop input."""

import hashlib
import json
from dataclasses import replace

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage, create_incoming_llm
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import installation_header, kakao_command, plan_texts
from app.automation.unified_workflow import UnifiedProcessor
from app.capture.saved_image import normalize_capture_image
from app.models import AgentError

NO_ACTION = "No workflow executed: no complete supported incoming request was found."


class SavedImageWorkflow:
    def __init__(
        self,
        config,
        queue,
        jobs,
        journal,
        cancel,
        progress,
        text_preview,
        llm_factory=create_incoming_llm,
        operations_factory=create_unified_operations,
    ):
        self.config, self.queue, self.jobs, self.journal = config, queue, jobs, journal
        self.cancel, self.progress, self.text_preview = cancel, progress, text_preview
        self.llm_factory, self.operations_factory = llm_factory, operations_factory

    def queue_key(self):
        destination = [
            "saved-image-unified-v1",
            self.config.operations_url.rstrip("/"),
            self.config.operations_username,
        ]
        return "image-test:" + hashlib.sha256(json.dumps(destination).encode()).hexdigest()

    def run(self, image):
        check_cancel(self.cancel)
        png = normalize_capture_image(image)
        check_cancel(self.cancel)
        destination = self.queue_key()
        # Each explicitly selected image has its own test queue. A prior test of
        # a different file must never be claimed when the user presses Run.
        key = destination + ":" + hashlib.sha256(png).hexdigest()
        job_id, path = self.jobs.enqueue_pair(
            key,
            png,
            png,
            mode="latest",
            folder="Image tests--" + destination[-12:],
        )
        self.queue.event("image_test", job_id)
        self.progress(f"Saved-image test capture: {path}")
        result_key = job_id + ":image-test-result"
        saved = self.journal.get(result_key)
        # Old builds cached a negative decision for installations in image tests.
        legacy_skip = (
            saved is not None and "kind" not in saved and saved["output"] == NO_ACTION
            and installation_header(saved["incoming"])
        )
        if (saved and saved["output"] == NO_ACTION and "chat_commands" not in saved
                and kakao_command(saved["incoming"])):
            legacy_skip = True
        if saved is None:
            plan = self.journal.get(job_id + ":plan")
            legacy_skip = plan and any(
                isinstance(part, str) and (installation_header(part) or kakao_command(part))
                and self.journal.get(f"{job_id}-{i}:analysis") == {"request": None}
                for i, part in enumerate(plan)
            )
        if legacy_skip and self.journal.reopen_skipped_image(job_id, result_key, saved):
            saved = None
        if saved is not None:
            check_cancel(self.cancel)
            self.text_preview(saved["incoming"])
            self.jobs.finish(job_id, "ignored")
            raise AgentError("This image was already processed; check its operation history before submitting a new request")
        try:
            claimed = self.jobs.claim(key)
            if claimed is None or claimed["job_id"] != job_id:
                raise AgentError("This image test is not ready; stop and restart the application")
            llm = self.llm_factory(self.config)
            processor = UnifiedProcessor(
                self.journal, self.operations_factory(self.config), self.progress
            )
            plan = self.journal.get(job_id + ":plan")
            if plan and any(self.journal.get(f"{job_id}-{i}:api") is not None for i in range(len(plan))):
                raise AgentError("This image already has an API attempt; check its operation history before resubmitting")
            if plan and len(plan) > 1 and any(installation_header(part) for part in plan):
                raise IncomingAnalysisError("Saved installation form has unclear message boundaries")
            if plan is not None:
                incoming = IncomingMessage("incoming", "\n".join(plan_texts(plan)))
            else:
                self.progress("Extracting the latest visible message from the selected image")
                incoming = llm.classify_latest(png, self.cancel)
                # The latest-message classifier already selected one complete bubble.
                incoming = replace(incoming, bubbles=(incoming.text,))
            check_cancel(self.cancel)
            self.text_preview(incoming.text)
            if incoming.kind == "uncertain":
                raise IncomingAnalysisError(
                    "Latest message is unclear; choose a clearer capture and try again"
                )
            self.progress("Running the unified API workflow; response will appear in Output")
            reply = processor.answer(llm, incoming, job_id, self.cancel)
            check_cancel(self.cancel)
            output = (
                reply
                if reply is not None
                else (
                    "No workflow executed: the latest message is outgoing or automated."
                    if incoming.kind == "outgoing"
                    else NO_ACTION
                )
            )
            # Reopening the same image must not repeat external operations. Keep
            # test jobs in a namespace that no live chat can claim or send.
            self.journal.claim(result_key, job_id, {
                "output": output, "incoming": incoming.text, "kind": incoming.kind, "chat_commands": True,
            })
            self.jobs.finish(job_id, "ignored")
            self.queue.event("image_test_complete", job_id)
            return output
        except Exception:
            self.jobs.finish(job_id, "pending")
            raise
