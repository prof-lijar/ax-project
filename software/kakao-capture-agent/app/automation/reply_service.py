"""One explicit operator click sends one fixed test reply; no background replies."""

from app.models import AgentError, Cancelled

TEST_REPLY = "[AI가 답장드렸습니다]"


class TestReplySender:
    def __init__(self, composer, audit, cancel):
        self.composer, self.audit, self.cancel = composer, audit, cancel

    def check(self, handle=None):
        if self.cancel.is_set():
            raise Cancelled("Test reply cancelled; inspect the chat before trying again")
        current = self.composer.focused()
        if handle is not None and current != handle:
            raise AgentError(
                "Message-box focus changed; test reply stopped. Inspect the chat draft"
            )
        return current

    def send(self):
        self.audit("reply_attempt", "Operator requested fixed test reply; no automatic retries")
        try:
            handle = self.check()
            if self.composer.read(handle):
                raise AgentError(
                    "Message box already contains a draft; nothing was overwritten or sent"
                )
            self.check(handle)
            self.composer.write(handle, TEST_REPLY)
            self.check(handle)
            if self.composer.read(handle) != TEST_REPLY:
                raise AgentError(
                    "Test text could not be verified; Enter was not sent. Inspect the draft"
                )
            self.check(handle)
            self.composer.submit(handle)
        except Exception:
            self.audit(
                "reply_incomplete",
                "Attempt stopped or uncertain; inspect chat/draft before retrying",
            )
            raise
        self.audit("reply_submitted", "Enter requested once; delivery is not verified")
        return "Test reply send requested. Verify it in KakaoTalk; no automatic retry"
