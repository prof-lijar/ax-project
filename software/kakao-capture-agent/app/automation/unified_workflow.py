"""Run Agent (auto): queued screenshots → AX768 dispatcher → unchanged API reply."""

import hashlib
import json
from dataclasses import asdict

from app.api.incoming_llm import IncomingMessage
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import extract_sources
from app.automation.device_workflow import UNCERTAIN
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


class UnifiedProcessor:
    def __init__(self, journal, operations, activity=lambda _: None):
        self.journal, self.operations, self.activity = journal, operations, activity

    def answer(self, llm, incoming, job_id, cancel):
        check_cancel(cancel)
        reply = self.journal.get(job_id + ":reply")
        if reply is not None:
            return reply
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
            key = f"{job_id}-{index}:api"
            uncertain = {
                "status": "uncertain",
                "response": "[자동 확인]\n" + UNCERTAIN,
                "completed": False,
            }
            if self.journal.claim(key, job_id, uncertain):
                self.activity("AX768: selecting and executing the requested workflow")
                try:
                    result = asdict(self.operations.run(message, cancel))
                except Cancelled:
                    raise
                except AgentError as error:
                    result = uncertain
                    self.activity("AX768 result unavailable; no automatic retry: " + str(error))
                self.journal.complete(key, result)
            replies.append(self.journal.get(key)["response"])
        check_cancel(cancel)
        reply = "\n\n".join(replies)
        if len(reply) > 2000:
            raise AgentError(
                "Combined AX768 replies exceed the composer limit; review saved results"
            )
        self.journal.claim(job_id + ":reply", job_id, reply)
        return self.journal.get(job_id + ":reply")


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

    def begin_job(self, job):
        super().begin_job(dict(job, processor=self.processor))

    def analyze_job(self, llm, job, cancel):
        if job["processor"].journal.get(job["job_id"] + ":plan") is not None:
            return IncomingMessage("incoming", "저장된 요청 처리 결과")
        return super().analyze_job(llm, job, cancel)

    def answer_job(self, llm, incoming, job, cancel):
        return job["processor"].answer(llm, incoming, job["job_id"], cancel)

    def format_reply(self, reply):
        return reply
