"""Run Agent (auto): queued screenshots → AX768 dispatcher → unchanged API reply."""

import hashlib
import json
from dataclasses import asdict

from app.api.incoming_llm import IncomingMessage, automated_text
from app.api.unified_operations import ACTION_KEYWORDS, create_unified_operations, message_action
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import extract_sources
from app.automation.device_workflow import UNCERTAIN
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


def actionable_message(text):
    """Only currently enabled incoming actions may reach AX768."""
    return any(keyword in text for keyword in ACTION_KEYWORDS) and not automated_text(text)


class UnifiedProcessor:
    def __init__(self, journal, operations, activity=lambda _: None):
        self.journal, self.operations, self.activity = journal, operations, activity

    def answer(self, llm, incoming, job_id, cancel):
        check_cancel(cancel)
        if incoming.kind != "incoming" or not actionable_message(incoming.text):
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
            action = message_action(message)
            if not actionable_message(message) or action is None:
                continue
            key = f"{job_id}-{index}:api"
            uncertain = {
                "status": "uncertain",
                "response": "[자동 확인]\n" + UNCERTAIN,
                "completed": False,
            }
            if self.journal.claim(key, job_id, uncertain):
                self.activity(f"AX768: processing {action} with the 기기위치조정/전원연결 workflow")
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

    def begin_job(self, job):
        super().begin_job(dict(job, processor=self.processor))

    def analyze_job(self, llm, job, cancel):
        plan = job["processor"].journal.get(job["job_id"] + ":plan")
        if plan is not None:
            return IncomingMessage("incoming", "\n".join(plan))
        return super().analyze_job(llm, job, cancel)

    def answer_job(self, llm, incoming, job, cancel):
        return job["processor"].answer(llm, incoming, job["job_id"], cancel)

    def format_reply(self, reply):
        return reply
