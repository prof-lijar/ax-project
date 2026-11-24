"""One explicit operator action sends one bounded reply; no automatic retries."""

from contextlib import nullcontext

from app.automation.composer_text import composer_is_empty
from app.models import AgentError, Cancelled

TEST_REPLY = "[AI가 답장드렸습니다]"


class TestReplySender:
    def __init__(self, composer, audit, cancel):
        self.composer, self.audit, self.cancel = composer, audit, cancel
        self.composer_cleared = False
        self.input_started = False

    def composer_session(self):
        return nullcontext(self.composer)

    def check(self, composer, handle=None):
        if self.cancel.is_set():
            raise Cancelled("Test reply cancelled; inspect the chat before trying again")
        current = composer.focused()
        if handle is not None and current != handle:
            raise AgentError(
                "Message-box focus changed; test reply stopped. Inspect the chat draft"
            )
        return current

    def send(self, text=TEST_REPLY, *, require_empty=False):
        self.composer_cleared = False
        self.input_started = False
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 2000
            or any(ord(c) < 32 and c not in "\r\n\t" for c in text)
        ):
            raise AgentError("Reply is empty, too long, or contains unsupported control characters")
        with self.composer_session() as composer:
            return self.send_with_composer(composer, text, require_empty)

    def send_with_composer(self, composer, text, require_empty):
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.audit(
            "reply_attempt",
            "Reply requested with empty-composer guard; no automatic retries"
            if require_empty
            else "Operator requested reply with draft replacement; no automatic retries",
        )
        try:
            if self.cancel.is_set():
                raise Cancelled("Test reply cancelled")
            selected = composer.prepare(self.cancel)
            handle = self.check(composer, selected)
            if require_empty and not composer_is_empty(composer.read(handle)):
                raise AgentError(
                    "Message box is not empty; no text replaced or Enter sent. Clear the draft before restarting Run Agent (auto)"
                )
            self.check(composer, handle)
            # Win32 multiline editors may normalize LF to CRLF on readback.
            # Set before writing: even a failed write may have changed the draft.
            self.input_started = True
            composer.write(handle, normalized.replace("\n", "\r\n"))
            self.check(composer, handle)
            actual = composer.read(handle).replace("\r\n", "\n").replace("\r", "\n")
            if actual != normalized:
                raise AgentError(
                    "Test text could not be verified; Enter was not sent. Inspect the draft"
                )
            self.check(composer, handle)
            composer.submit(handle)
        except Exception:
            self.audit(
                "reply_incomplete",
                "Attempt stopped or uncertain; inspect chat/draft before retrying",
            )
            raise
        self.audit("reply_submitted", "Enter requested once; delivery is not verified")
        observation = composer.observe_submission(handle, self.cancel)
        self.composer_cleared = observation.composer_cleared
        self.audit("reply_observed", observation.message)
        return observation.message
