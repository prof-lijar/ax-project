"""Process each watched chat’s queued requests, notifications and replies."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from app.api.incoming_llm import IncomingMessage, analysis_error, automated_text
from app.api.unified_operations import create_unified_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import (
    INSTALLATION,
    analyze_request,
    extract_sources,
    installation_header,
    kakao_command,
    plan_texts,
    workflow_action_keyword,
)
from app.automation.device_workflow import UNCERTAIN
from app.automation.installation_sms import InstallationSMS
from app.automation.keyword_visual_catch import KeywordVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal


class UnifiedProcessor:
    def __init__(self, journal, operations, activity=lambda _: None, *, installation_sms=None):
        self.installation_sms = installation_sms
        self.journal, self.operations, self.activity = journal, operations, activity

    def answer(self, llm, incoming, job_id, cancel, *, startup=False, received_date="",
               queue_each_request=False):
        check_cancel(cancel)
        if incoming.kind != "incoming" or automated_text(incoming.text):
            return None
        plan_key = job_id + ":plan"
        plan = self.journal.get(plan_key)
        if plan is None:
            if incoming.bubbles:
                plan = list(incoming.bubbles)
            elif startup:
                # Startup classification already selected exactly one complete bubble.
                plan = [incoming.text]
            else:
                plan = extract_sources(llm, incoming, cancel)
                # A legacy flat transcript cannot establish a new installation
                # boundary inside prose. Only an entire form may be dispatched.
                if any(installation_header(m) for m in plan):
                    if len(plan) != 1 or not installation_header(incoming.text):
                        raise analysis_error("installation bubble boundaries unclear")
                if any(kakao_command(m) for m in plan) and plan != [incoming.text]:
                    raise analysis_error("workflow command bubble boundaries unclear")
            for index, message in enumerate(plan):
                sender = incoming.sender if len(plan) == 1 else ""
                if incoming.bubble_senders:
                    sender = incoming.bubble_senders[index]
                command = kakao_command(message, sender, received_date or incoming.received_date)
                if command:
                    plan[index] = command
            check_cancel(cancel)
            if queue_each_request and len(plan) > 1:
                self.journal.queue_requests(job_id, plan)
            else:
                self.journal.claim(plan_key, job_id, plan)
            plan = self.journal.get(plan_key)
        replies = []
        live_capture = queue_each_request or startup
        for index, message in enumerate(plan_texts(plan)):
            check_cancel(cancel)
            if automated_text(message) or (live_capture and not workflow_action_keyword(message)):
                continue
            key = f"{job_id}-{index}:api"
            # Analyze before claiming an external action. Malformed model output
            # can be retried without implying that the API was already called.
            analysis_key = f"{job_id}-{index}:analysis"
            cached = self.journal.get(analysis_key)
            if cached is None:
                if isinstance(plan[index], dict):
                    request = plan[index]
                elif installation_header(message):
                    request = {"workflow_id": INSTALLATION, "message": message}
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
            workflow_id = request.get("workflow_id")
            installation = workflow_id == INSTALLATION
            sms_key = f"{job_id}-{index}:sms"
            if workflow_id in (INSTALLATION, "information_update") and self.installation_sms:
                self.installation_sms.record_routing(job_id)
            uncertain = {
                "status": "uncertain",
                "response": "[자동 확인]\n"
                + (
                    "신규설치 등록 결과를 확인하지 못했습니다. 재실행 전에 명부와 마스터페이지를 확인해 주세요."
                    if installation
                    else "처리 결과를 확인하지 못했습니다. 중복 처리를 막기 위해 재요청 전에 기록을 확인해 주세요."
                    if workflow_id else UNCERTAIN
                ),
                "completed": False,
            }
            check_cancel(cancel)
            if self.journal.claim(key, job_id, uncertain):
                workflow = "가입자신규설치" if installation else workflow_id or request["action"]
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
            if self.installation_sms and result.get("sms") is not None:
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


class UnifiedWorkflow(KeywordVisualCatchWorkflow):
    greeting = None
    action_keyword = staticmethod(workflow_action_keyword)

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

    def on_action_queued(self, job_id):
        self.installation_sms.record_routing(job_id)

    def queue_initial_capture(self):
        discarded = self.jobs.reset_for_run(self.chat_key)
        self.progress(f"Fresh run: discarded {discarded} unfinished task(s); checking the latest visible message")
        self.start_screen(self.baseline, self.baseline, startup=True)

    def begin_job(self, job):
        super().begin_job(dict(job, processor=self.processor))

    def analyze_job(self, llm, job, cancel):
        plan = job["processor"].journal.get(job["job_id"] + ":plan")
        if plan is not None:
            return IncomingMessage("incoming", "\n".join(plan_texts(plan)))
        return super().analyze_job(llm, job, cancel)

    def answer_job(self, llm, incoming, job, cancel):
        startup = json.loads(job["text"]).get("mode") == "latest"
        return job["processor"].answer(
            llm,
            incoming,
            job["job_id"],
            cancel,
            startup=startup,
            queue_each_request=not startup,
            received_date=("" if startup else datetime.fromtimestamp(
                job["created_at"], timezone(timedelta(hours=9))
            ).date().isoformat()),
        )

    def format_reply(self, reply):
        return reply
