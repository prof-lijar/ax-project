"""Run Agent (auto): queued screenshots → AX768 dispatcher → unchanged API reply."""

import hashlib
import json
from dataclasses import asdict

from app.api.incoming_llm import IncomingMessage, automated_text
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import analyze_request, extract_sources
from app.automation.device_workflow import UNCERTAIN
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


class UnifiedProcessor:
    def __init__(self, journal, operations, activity=lambda _: None):
        self.journal, self.operations, self.activity = journal, operations, activity

    def answer(self, llm, incoming, job_id, cancel, *, startup_chat_key=None):
        check_cancel(cancel)
        if incoming.kind != "incoming" or automated_text(incoming.text):
            return None
        plan_key = job_id + ":plan"
        plan = self.journal.get(plan_key)
        if plan is None:
            plan = extract_sources(llm, incoming, cancel)
            check_cancel(cancel)
            self.journal.claim(plan_key, job_id, plan)
            plan = self.journal.get(plan_key)
        replies = []
        for index, message in enumerate(plan):
            check_cancel(cancel)
            if automated_text(message):
                continue
            key = f"{job_id}-{index}:api"
            # Analyze before claiming an external action. Malformed model output
            # can be retried without implying that the API was already called.
            analysis_key = f"{job_id}-{index}:analysis"
            cached = self.journal.get(analysis_key)
            if cached is None:
                request = analyze_request(llm, message, cancel)
                check_cancel(cancel)
                self.journal.claim(analysis_key, job_id, {"request": request})
                cached = self.journal.get(analysis_key)
            request = cached["request"]
            if request is None:
                self.activity(
                    f"AX768 analysis: model found no complete supported request ({len(message)} characters); "
                    "see Latest extracted incoming text; no API call"
                )
                continue
            if startup_chat_key and self.journal.previously_attempted(startup_chat_key, request, job_id):
                self.activity("Startup request already attempted in this chat; no duplicate API call or reply")
                continue
            action = request["action"]
            uncertain = {
                "status": "uncertain",
                "response": "[자동 확인]\n" + UNCERTAIN,
                "completed": False,
            }
            if self.journal.claim(key, job_id, uncertain):
                self.activity(f"AX768: processing {action} with the 기기위치조정/전원연결 workflow")
                try:
                    result = asdict(self.operations.run(request, cancel))
                except Cancelled:
                    raise
                except AgentError as error:
                    result = uncertain
                    self.activity("AX768 result unavailable; no automatic retry: " + str(error))
                self.journal.complete(key, result)
            replies.append(self.journal.get(key)["response"])
        check_cancel(cancel)
        if not replies:
            return None
        reply = "\n\n".join(replies)
        if len(reply) > 2000:
            raise AgentError(
                "Combined AX768 replies exceed the composer limit; review saved results"
            )
        # Rebuild from per-message receipts so old cached batches cannot replay
        # replies for actions that are no longer enabled. API claims stay intact.
        reply_key = job_id + ":reply"
        self.journal.claim(reply_key, job_id, reply)
        self.journal.complete(reply_key, reply)
        return reply


class UnifiedWorkflow(QueuedVisualCatchWorkflow):
    greeting = None

    def __init__(self, *args, activity=lambda _: None, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = OperationJournal(self.queue)
        self.processor_factory = lambda: UnifiedProcessor(
            self.journal, create_unified_operations(self.config), activity
        )

    def queue_key(self):
        destination = [
            "ax768-unified-v1",
            self.config.operations_url.rstrip("/"),
            self.config.operations_username,
        ]
        return (
            super().queue_key()
            + ":unified:"
            + hashlib.sha256(json.dumps(destination).encode()).hexdigest()
        )

    def arm(self):
        self.processor = self.processor_factory()
        super().arm()

    def queue_initial_capture(self):
        job_id, path = self.jobs.enqueue_pair(
            self.chat_key, self.baseline, self.baseline, mode="latest"
        )
        self.queue.event("auto_visual_startup", job_id)
        self.progress(f"Startup capture: checking the latest visible message once: {path}")

    def begin_job(self, job):
        super().begin_job(dict(job, processor=self.processor))

    def analyze_job(self, llm, job, cancel):
        plan = job["processor"].journal.get(job["job_id"] + ":plan")
        if plan is not None:
            return IncomingMessage("incoming", "\n".join(plan))
        if json.loads(job["text"]).get("mode") == "latest":
            return llm.classify_latest(job["after_png"], cancel)
        return super().analyze_job(llm, job, cancel)

    def answer_job(self, llm, incoming, job, cancel):
        startup = json.loads(job["text"]).get("mode") == "latest"
        return job["processor"].answer(
            llm, incoming, job["job_id"], cancel,
            startup_chat_key=job["chat_key"] if startup else None,
        )

    def format_reply(self, reply):
        return reply
