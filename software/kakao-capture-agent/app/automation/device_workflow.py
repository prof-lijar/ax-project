"""Continuous device requests → operations API → KakaoTalk, without SMS."""

import hashlib
import json
from dataclasses import asdict

from app.api.device_request import extract_requests
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import device_action_keyword
from app.automation.keyword_visual_catch import KeywordVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


class DeviceProcessor:
    def __init__(self, journal, operations, activity=lambda _: None):
        self.journal, self.operations, self.activity = (
            journal,
            operations,
            activity,
        )

    def process_request(self, request, job_id, index, cancel, original_request):
        check_cancel(cancel)
        if not request["action"] or not request["name"] or not request["address"]:
            self.activity("Enter the person's name, address and device action")
            return None
        reference = f"{job_id}-{index}"
        key = reference + ":api"
        message = f"{request['name']}/{request['address']}/{request['action']}"
        payload = {**request, "message": message, "action_text": request["action"]}
        if not self.journal.start_execution(key, job_id, payload, original_request=original_request):
            self.activity("This queued request was already attempted; check its history before resubmitting")
            return None
        self.activity("기기위치조정/전원연결: calling 운영시트에이젠트; watching continues")
        try:
            result = asdict(self.operations.run(payload, cancel))
        except Cancelled:
            raise
        except AgentError as error:
            self.activity("Operations API result unavailable; check the operation before resubmitting: " + str(error))
            return None
        self.journal.finish_execution(key, result)
        check_cancel(cancel)
        return key, result["response"]

    def answer(self, llm, incoming, job_id, cancel):
        check_cancel(cancel)
        plan_key = job_id + ":plan"
        plan = self.journal.get(plan_key)
        if plan is None:
            plan = extract_requests(llm, incoming, cancel)
            check_cancel(cancel)
            self.journal.claim(plan_key, job_id, plan)
            plan = self.journal.get(plan_key)
        parts = [self.process_request(request, job_id, i, cancel, incoming.text) for i, request in enumerate(plan)]
        parts = [part for part in parts if part is not None]
        check_cancel(cancel)
        if not parts:
            return None
        reply = "\n\n".join(text for _, text in parts)
        self.journal.record_outgoing(job_id, reply, [key for key, _ in parts],
                                     "review" if len(reply) > 2000 else "ready")
        if len(reply) > 2000:
            raise AgentError("Combined API replies exceed the composer limit; review operation history")
        return reply


class DeviceWorkflow(KeywordVisualCatchWorkflow):
    action_keyword = staticmethod(device_action_keyword)
    greeting = None

    def __init__(self, *args, activity=lambda _: None, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = OperationJournal(self.queue)
        self.activity = activity
        self.processor_factory = lambda: DeviceProcessor(
            self.journal,
            create_unified_operations(self.config),
            self.activity,
        )

    def queue_key(self):
        # Old captures cannot change purpose or destination after a settings edit.
        # Retain the legacy key fields so pending captures survive the SMS removal.
        destination = [
            "prepend-name-address-v2",
            self.config.operations_url.rstrip("/"),
            self.config.operations_username,
            self.config.bizgo_sender,
            self.config.bizgo_recipient,
            self.config.bizgo_sandbox,
        ]
        digest = hashlib.sha256(json.dumps(destination).encode()).hexdigest()
        return super().queue_key() + ":device:" + digest

    def arm(self):
        # Validate operations API credentials before collecting.
        self.processor = self.processor_factory()
        super().arm()

    def begin_job(self, job):
        # Each worker keeps its processor/destinations even if Stop starts a new mode.
        super().begin_job(dict(job, processor=self.processor))

    def answer_job(self, llm, incoming, job, cancel):
        return job["processor"].answer(llm, incoming, job["job_id"], cancel)

    def format_reply(self, reply):
        # Device confirmations use their complete template, without the generic suffix.
        return reply
