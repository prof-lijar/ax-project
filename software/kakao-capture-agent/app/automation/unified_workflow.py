"""Process each watched chat’s queued requests, notifications and replies."""

import hashlib
import json
from dataclasses import asdict

from app.api.incoming_llm import IncomingMessage, analysis_error, automated_text
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import (
    INSTALLATION,
    analyze_request,
    extract_sources,
    installation_header,
)
from app.automation.device_workflow import UNCERTAIN
from app.automation.installation_sms import InstallationSMS
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


class UnifiedProcessor:
    def __init__(self, journal, operations, activity=lambda _: None, *, installation_sms=None):
        self.installation_sms = installation_sms
        self.journal, self.operations, self.activity = journal, operations, activity

    def answer(self, llm, incoming, job_id, cancel, *, startup_chat_key=None):
        check_cancel(cancel)
        if incoming.kind != "incoming" or automated_text(incoming.text):
            return None
        plan_key = job_id + ":plan"
        plan = self.journal.get(plan_key)
        if plan is None:
            if incoming.bubbles:
                plan = list(incoming.bubbles)
            elif startup_chat_key:
                # Startup classification already selected exactly one complete bubble.
                plan = [incoming.text]
            else:
                plan = extract_sources(llm, incoming, cancel)
                # A legacy flat transcript cannot establish a new installation
                # boundary inside prose. Only an entire form may be dispatched.
                if self.installation_sms and any(installation_header(m) for m in plan):
                    if len(plan) != 1 or not installation_header(incoming.text):
                        raise analysis_error("installation bubble boundaries unclear")
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
                if installation_header(message):
                    request = (
                        {"workflow_id": INSTALLATION, "message": message}
                        if self.installation_sms
                        else None
                    )
                else:
                    request = analyze_request(llm, message, cancel)
                check_cancel(cancel)
                self.journal.claim(analysis_key, job_id, {"request": request})
                cached = self.journal.get(analysis_key)
            request = cached["request"]
            if request is None:
                self.activity(
                    f"AX768 analysis: no complete supported request ({len(message)} characters); "
                    "see Latest extracted incoming text; no API call"
                )
                continue
            if startup_chat_key and self.journal.previously_attempted(
                startup_chat_key, request, job_id
            ):
                self.activity(
                    "Startup request already attempted in this chat; no duplicate API call or reply"
                )
                continue
            installation = request.get("workflow_id") == INSTALLATION
            sms_key = f"{job_id}-{index}:sms"
            if installation:
                self.installation_sms.record_routing(job_id)
            uncertain = {
                "status": "uncertain",
                "response": "[자동 확인]\n"
                + (
                    "신규설치 등록 결과를 확인하지 못했습니다. 재실행 전에 명부와 마스터페이지를 확인해 주세요."
                    if installation
                    else UNCERTAIN
                ),
                "completed": False,
            }
            if self.journal.claim(key, job_id, uncertain):
                workflow = "가입자신규설치" if installation else request["action"]
                self.activity(f"AX768: processing {workflow}")
                try:
                    result = asdict(self.operations.run(request, cancel))
                except Cancelled:
                    raise
                except AgentError as error:
                    result = uncertain
                    self.activity("AX768 result unavailable; no automatic retry: " + str(error))
                self.journal.complete(key, result)
            result = self.journal.get(key)
            if installation and result.get("sms") is not None:
                reply = self.installation_sms.reply(result, job_id, sms_key, cancel)
            else:
                reply = result["response"]
            replies.append(reply)
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
        self.installation_sms = InstallationSMS(self.config, self.journal, self.queue.event, activity)
        self.processor_factory = lambda: UnifiedProcessor(
            self.journal,
            create_unified_operations(self.config),
            activity,
            installation_sms=self.installation_sms,
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

    def enqueue_capture(self, before, after, *, mode="changes"):
        job_id, path = super().enqueue_capture(before, after, mode=mode)
        self.installation_sms.record_routing(job_id)
        return job_id, path

    def queue_initial_capture(self):
        job_id, path = self.enqueue_capture(self.baseline, self.baseline, mode="latest")
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
        return llm.classify(job["before_png"], job["after_png"], cancel, batch="bubbles")

    def answer_job(self, llm, incoming, job, cancel):
        startup = json.loads(job["text"]).get("mode") == "latest"
        return job["processor"].answer(
            llm,
            incoming,
            job["job_id"],
            cancel,
            startup_chat_key=job["chat_key"] if startup else None,
        )

    def format_reply(self, reply):
        return reply
