"""Deliver authorized guardian SMS and append only the observed client outcome."""

import hashlib
import json
from dataclasses import replace

from app.api.bizgo_client import create_bizgo, installation_test_numbers
from app.api.workflow_llm import check_cancel
from app.models import AgentError, Cancelled

SMS_UNCERTAIN = (
    "■ 보호자 안내 문자\n일부 안내 문자의 발송 결과를 확인하지 못했습니다.\n"
    "재발송 전에 발송 내역을 확인해 주세요."
)
SMS_TEST = "■ 보호자 안내 문자\n설정된 테스트 번호로 앱 설치 안내 문자 발송을 요청했습니다."
SMS_SANDBOX = "■ 보호자 안내 문자\nBizgo 샌드박스 테스트가 완료되었습니다.\n실제 문자는 발송되지 않았습니다."


def notification_reply(result, notice):
    # The processor checks the complete outgoing length before chat submission.
    return result["response"] + "\n\n" + notice


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
            return result["response"]
        # Receipts prevent duplicate SMS operations; no saved notice is replayed.
        check_cancel(cancel)
        if not self.journal.claim(key, job_id, {"status": "uncertain"}):
            self.activity(SMS_UNCERTAIN)
            return notification_reply(result, SMS_UNCERTAIN)
        accepted_parts = 0
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
                    accepted_parts += 1
        except Cancelled:
            raise
        except (AgentError, ValueError) as error:
            self.activity(f"Installation SMS needs review. {error}")
            self.journal.complete(key, {"status": "uncertain", "accepted_parts": accepted_parts})
            return notification_reply(result, SMS_UNCERTAIN)

        if self.config.bizgo_sandbox:
            notice = SMS_SANDBOX
        elif self.config.bizgo_installation_test:
            notice = SMS_TEST
        else:
            endings = ", ".join(number[-4:] for number in recipients)
            notice = (
                "■ 보호자 안내 문자\n앱 설치 안내 문자 발송 요청이 정상 접수되었습니다.\n"
                f"보호자 번호 끝자리 : {endings}"
            )
        self.journal.complete(key, {"status": "accepted", "accepted_parts": accepted_parts,
                                    "sandbox": self.config.bizgo_sandbox,
                                    "test_routing": self.config.bizgo_installation_test})
        self.activity(notice)
        return notification_reply(result, notice)
