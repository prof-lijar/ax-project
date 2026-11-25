"""Deliver the server's guardian guide before composing the installation chat reply."""

import hashlib
import json
from dataclasses import replace

from app.api.bizgo_client import create_bizgo, installation_test_numbers
from app.api.workflow_llm import check_cancel
from app.models import AgentError, Cancelled


def installation_message(result, sms_status):
    name = result["subscriber_name"]
    signal = result["signal_status"]
    if signal == "confirmed":
        heading = f"{name}님 신규설치된 기기신호 확인 완료입니다."
    elif signal == "disconnected":
        heading = f"{name}님 신규설치된 기기신호가 아직 확인되지 않았습니다."
    elif signal == "unverified":
        heading = f"{name}님 신규설치된 기기의 신호 확인 결과를 확인할 수 없습니다."
    else:
        heading = f"{name}님 신규설치 처리가 완료되지 않았습니다."
    lines = [f"{i}.{item['label']} : {item['status']}" for i, item in enumerate(result["kakao_reply"], 1)]
    lines.append(f"4.보호자 앱설치문자 발송 : {sms_status}")
    sections = [f"[자동 확인]\n{heading}", "■ 반영 영역", "\n".join(lines)]
    summary = result.get("issue_summary", "")
    if summary:
        available = 2000 - len("\n\n".join([*sections, "", "감사합니다."]))
        sections.append(summary if len(summary) <= available else summary[:available-1] + "…")
    return "\n\n".join([*sections, "감사합니다."])


def notification_reply(result, notice, *, guardian_request_accepted=False):
    draft = result["kakao_reply"]
    sent_line = "내용 기재 및 보호자님께 앱설치 문자 발송 완료했습니다."
    if isinstance(draft, list):
        return installation_message(result, "완료" if guardian_request_accepted else notice)
    # A cached text draft from the old API has no independent signal evidence.
    draft = draft.replace("신규설치 기기신호 확인 완료입니다.", "신규설치 등록 완료입니다.")
    draft = draft.replace("기기신호 확인 완료입니다.", "등록 완료입니다.")
    if sent_line in draft:
        reply = draft.replace(sent_line, "내용 기재를 완료했습니다.\n" + notice)
        if len(reply) <= 2000:
            return reply
    elif guardian_request_accepted:
        reply = draft.rstrip() + "\n\n" + notice
        if len(reply) <= 2000:
            return reply
    summary = "[자동 확인]\n" + result["response"] + "\n" + notice
    return (
        summary if len(summary) <= 2000 else "[자동 확인]\n신규설치 등록을 완료했습니다. " + notice
    )


class InstallationSMS:
    def __init__(self, config, journal, audit, activity):
        self.config, self.journal = config, journal
        self.audit, self.activity = audit, activity

    def routing(self):
        settings = [
            self.config.bizgo_installation_test,
            self.config.bizgo_sandbox,
            self.config.bizgo_sender,
        ]
        if self.config.bizgo_installation_test:
            settings.append(self.config.bizgo_test_recipients)
        return hashlib.sha256(json.dumps(settings).encode()).hexdigest()

    def record_routing(self, job_id):
        self.journal.claim(job_id + ":sms-routing", job_id, self.routing())

    def reply(self, result, job_id, key, cancel):
        sms = result["sms"]
        if not sms["should_send"]:
            if isinstance(result["kakao_reply"], list):
                return installation_message(result, "미발송")
            return result["kakao_reply"]
        # Journal a review message before the first send. Only all accepted
        # production requests can promote the fourth item to 완료.
        review = notification_reply(result, "보호자 안내 문자 발송 결과를 확인해 주세요.")
        check_cancel(cancel)
        if not self.journal.claim(key, job_id, review):
            return self.journal.get(key)
        try:
            if self.journal.get(job_id + ":sms-routing") != self.routing():
                raise AgentError(
                    "Bizgo routing settings changed since capture; review before sending"
                )
            recipients = sms["recipients"]
            if self.config.bizgo_installation_test:
                recipients = installation_test_numbers(self.config.bizgo_test_recipients)
                if set(recipients).intersection(sms["recipients"]):
                    raise AgentError(
                        "Installation test numbers overlap guardian numbers; SMS stopped"
                    )
            for index, recipient in enumerate(recipients):
                check_cancel(cancel)
                config = replace(self.config, bizgo_recipient=recipient)
                client = create_bizgo(config, self.audit, force=True)
                reference = hashlib.sha256(f"{key}/{index}".encode()).hexdigest()
                messages = client.prepare_installation(sms["title"], sms["text"], reference)
                for message in messages:
                    self.activity(client.send(message, cancel))
        except Cancelled:
            raise
        except (AgentError, ValueError) as error:
            self.activity(f"Installation SMS needs review. {error}")
            return review

        if self.config.bizgo_sandbox:
            reply = notification_reply(
                result, "Bizgo 샌드박스 테스트가 완료되었습니다. 실제 문자는 발송되지 않았습니다."
            )
        elif self.config.bizgo_installation_test:
            reply = notification_reply(
                result, "앱설치 안내 문자는 설정된 테스트 번호로만 발송 요청했습니다."
            )
        else:
            endings = ", ".join(number[-4:] for number in recipients)
            reply = notification_reply(
                result,
                "보호자님께 앱 설치 안내 문자를 성공적으로 발송했습니다.\n"
                f"보호자 번호 끝자리: {endings}",
                guardian_request_accepted=True,
            )
        self.journal.complete(key, reply)
        return reply
