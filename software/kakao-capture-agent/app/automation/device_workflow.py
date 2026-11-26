"""Continuous device requests → operations API → KakaoTalk, without SMS."""

import hashlib
import json
from dataclasses import asdict

from app.api.device_request import CLARIFY, extract_requests
from app.api.operations_client import create_operations
from app.api.workflow_llm import check_cancel
from app.api.workflow_requests import device_action_keyword
from app.automation.keyword_visual_catch import KeywordVisualCatchWorkflow
from app.models import AgentError, Cancelled
from app.storage.operation_journal import OperationJournal

UNCERTAIN = "운영시트 처리 결과를 확인하지 못했습니다. 중복 처리를 막기 위해 재실행하지 않았습니다. 운영시트와 회원 메모를 확인해주세요."


class DeviceProcessor:
    def __init__(self, journal, operations, activity=lambda _: None):
        self.journal, self.operations, self.activity = (
            journal,
            operations,
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
        action = "기기 위치변경" if request["action"] == "기기위치조정" else "전원연결"
        return (
            f"{request['name']}님 {action} 후 기기신호 확인 완료입니다.\n"
            "내용 기재해두었습니다.\n"
            "감사합니다. :)"
        )

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
        reply = "[자동 확인]\n" + "\n\n".join(
            (f"{i + 1}. " if len(parts) > 1 else "")
            + (part if len(part) <= budget else part[: budget - 18] + "… (상세 결과 확인 필요)")
            for i, part in enumerate(parts)
        )
        self.journal.claim(job_id + ":reply", job_id, reply)
        return self.journal.get(job_id + ":reply")


class DeviceWorkflow(KeywordVisualCatchWorkflow):
    action_keyword = staticmethod(device_action_keyword)
    greeting = "[AI] 기기위치조정/전원연결 요청을 보내주세요. 대상자 이름 / 주소 / 작업을 한 메시지로 보내주시면 처리하겠습니다."

    def __init__(self, *args, activity=lambda _: None, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = OperationJournal(self.queue)
        self.activity = activity
        self.processor_factory = lambda: DeviceProcessor(
            self.journal,
            create_operations(self.config),
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
