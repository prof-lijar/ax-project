"""Continuous device requests → operations API → Bizgo test receipt → KakaoTalk."""

import hashlib
import json
from dataclasses import asdict

from app.api.bizgo_client import create_bizgo
from app.api.device_request import CLARIFY, extract_requests
from app.api.incoming_llm import IncomingMessage
from app.api.operations_client import create_operations
from app.api.workflow_llm import check_cancel
from app.automation.queued_visual_catch import QueuedVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal

UNCERTAIN = "운영시트 처리 결과를 확인하지 못했습니다. 중복 처리를 막기 위해 재실행하지 않았습니다. 운영시트와 회원 메모를 확인해주세요."
SMS_UNCERTAIN = "Bizgo 접수 결과 미확인(자동 재전송 없음)."


class DeviceProcessor:
    def __init__(self, journal, operations, bizgo, activity=lambda _: None):
        self.journal, self.operations, self.bizgo, self.activity = (
            journal,
            operations,
            bizgo,
            activity,
        )

    def process_request(self, request, job_id, index, cancel):
        check_cancel(cancel)
        if not request["action"] or not request["name"] or not request["address"]:
            return CLARIFY
        reference = f"{job_id}-{index}"
        key = reference + ":api"
        if self.journal.claim(
            key, job_id, {"status": "uncertain", "response": UNCERTAIN, "completed": False}
        ):
            self.activity("기기위치조정/전원연결: calling 운영시트에이젠트; watching continues")
            try:
                # The server's deterministic parser expects address before NAME님.
                message = f"{request['address']} {request['name']}님 {request['action']} 신호확인요.".strip()
                result = asdict(self.operations.run(message, cancel))
            except Cancelled:
                raise
            except AgentError as error:
                result = {"status": "uncertain", "response": UNCERTAIN, "completed": False}
                self.activity(
                    "Operations API result unavailable; continuing with a KakaoTalk status reply: "
                    + str(error)
                )
            self.journal.complete(key, result)
        result = self.journal.get(key)
        check_cancel(cancel)
        # API needs-confirmation/not-found/etc. is returned honestly; never mark it
        # successful or automatically set confirmed_name on behalf of the user.
        if not result["completed"]:
            return result["response"]
        sms_key = reference + ":sms"
        if self.journal.claim(sms_key, job_id, SMS_UNCERTAIN):
            self.activity("Operations workflow completed; submitting Bizgo test notification")
            try:
                message = self.bizgo.prepare("[test] 기기위치조정/전원연결 처리 성공", reference)
                self.bizgo.send(message, cancel)
                sms = (
                    "Bizgo 샌드박스 접수 완료(실제 문자 발송 없음)."
                    if self.bizgo.settings.sandbox
                    else "Bizgo 문자 접수 완료(최종 수신 여부는 Bizgo에서 확인)."
                )
            except Cancelled:
                raise
            except AgentError as error:
                sms = SMS_UNCERTAIN
                self.activity(
                    "Bizgo notification not confirmed; operations result will still be replied in KakaoTalk: "
                    + str(error)
                )
            self.journal.complete(sms_key, sms)
        return result["response"] + "\n" + self.journal.get(sms_key)

    def answer(self, llm, incoming, job_id, cancel):
        check_cancel(cancel)
        reply = self.journal.get(job_id + ":reply")
        if reply is not None:
            return reply
        plan_key = job_id + ":plan"
        plan = self.journal.get(plan_key)
        if plan is None:
            plan = extract_requests(llm, incoming, cancel)
            check_cancel(cancel)
            self.journal.claim(plan_key, job_id, plan)
            plan = self.journal.get(plan_key)
        parts = [self.process_request(request, job_id, i, cancel) for i, request in enumerate(plan)]
        check_cancel(cancel)
        # Bound the composer payload without hiding the last request entirely.
        budget = 1600 // len(parts)
        reply = "[AI] " + "\n\n".join(
            (f"{i + 1}. " if len(parts) > 1 else "")
            + (part if len(part) <= budget else part[: budget - 18] + "… (상세 결과 확인 필요)")
            for i, part in enumerate(parts)
        )
        self.journal.claim(job_id + ":reply", job_id, reply)
        return self.journal.get(job_id + ":reply")


class DeviceWorkflow(QueuedVisualCatchWorkflow):
    greeting = "[AI] 기기위치조정/전원연결 요청을 보내주세요. 대상자 이름 / 주소 / 작업을 한 메시지로 보내주시면 처리하겠습니다."

    def __init__(self, *args, activity=lambda _: None, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = OperationJournal(self.queue)
        self.activity = activity
        self.processor_factory = lambda: DeviceProcessor(
            self.journal,
            create_operations(self.config),
            create_bizgo(self.config, self.queue.event, force=True),
            self.activity,
        )

    def queue_key(self):
        # Old captures cannot change purpose or destination after a settings edit.
        destination = [
            "append-name-address-v1",
            self.config.operations_url.rstrip("/"),
            self.config.operations_username,
            self.config.bizgo_sender,
            self.config.bizgo_recipient,
            self.config.bizgo_sandbox,
        ]
        digest = hashlib.sha256(json.dumps(destination).encode()).hexdigest()
        return super().queue_key() + ":device:" + digest

    def arm(self):
        # Validate API and SMS credentials before sending a greeting or collecting.
        self.processor = self.processor_factory()
        super().arm()

    def begin_job(self, job):
        # Each worker keeps its processor/destinations even if Stop starts a new mode.
        super().begin_job(dict(job, processor=self.processor))

    def analyze_job(self, llm, job, cancel):
        if job["processor"].journal.get(job["job_id"] + ":plan") is not None:
            return IncomingMessage("incoming", "저장된 요청 처리 결과")
        return super().analyze_job(llm, job, cancel)

    def answer_job(self, llm, incoming, job, cancel):
        return job["processor"].answer(llm, incoming, job["job_id"], cancel)
