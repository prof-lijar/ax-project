"""One operator-triggered capture → vision → simulated summary → reply cycle."""

from app.api.bizgo_client import create_bizgo
from app.api.workflow_llm import LLMSettings, WorkflowLLM, check_cancel, llm_token
from app.capture.screen_capture import encode_png
from app.models import AgentError, Cancelled


def create_llm(config):
    settings = LLMSettings.resolve(config)
    token = llm_token(settings.url)
    if not token:
        raise AgentError("Configure the LLM API key in Settings or OPENAI_API_KEY; nothing sent")
    return WorkflowLLM(settings, token)


class OneCycleWorkflow:
    def __init__(
        self,
        desktop,
        capture,
        queue,
        config,
        sender,
        cancel,
        preview,
        progress,
        llm_factory=create_llm,
        bizgo_factory=create_bizgo,
    ):
        self.desktop, self.capture, self.queue, self.config = desktop, capture, queue, config
        self.sender, self.cancel = sender, cancel
        self.preview, self.progress, self.llm_factory = preview, progress, llm_factory
        self.bizgo_factory = bizgo_factory

    def run(self):
        check_cancel(self.cancel)
        llm = self.llm_factory(self.config)
        # Fail missing Bizgo settings/credentials before any capture or chat send.
        bizgo = self.bizgo_factory(self.config, self.queue.event)
        identity = (self.config.target, self.config.selection, self.config.chat_id)
        self.queue.event("workflow_started", "Operator requested one capture/LLM/reply cycle")
        try:
            self.progress("Capturing the selected region at its current position")
            self.desktop.activate_target()
            check_cancel(self.cancel)
            image, region = self.capture.grab()
            check_cancel(self.cancel)
            png = encode_png(image)
            capture_id = self.queue.enqueue(png, region, "live", local_only=True)
            self.preview(png)
            self.progress(
                f"Workflow capture saved locally: {self.queue.images / (capture_id + '.png')}"
            )
            self.queue.event("workflow_capture", capture_id)
            check_cancel(self.cancel)
            reply = llm.run(png, self.cancel, self.progress)
            check_cancel(self.cancel)
            if identity != (self.config.target, self.config.selection, self.config.chat_id):
                raise AgentError("Workflow target changed during analysis; no reply sent")
            phone_message = bizgo.prepare(reply, capture_id) if bizgo else None
            if phone_message:
                for warning in phone_message.warnings:
                    self.progress(warning)
            self.progress("Sending the test summary to the selected conversation")
            # Sender reactivates/revalidates the exact target and composer before any typing.
            result = self.sender.send(reply)
            if bizgo:
                if not self.sender.composer_cleared:
                    result += "; Bizgo skipped because KakaoTalk submission was not confirmed"
                    self.queue.event("bizgo_skipped", capture_id + ": composer did not clear")
                else:
                    try:
                        check_cancel(self.cancel)
                        mode = "sandbox (no delivery)" if bizgo.settings.sandbox else "production"
                        self.progress(f"Submitting one {phone_message.channel} to Bizgo {mode}")
                        result += "; " + bizgo.send(phone_message, self.cancel)
                    except Cancelled as error:
                        self.progress("KakaoTalk reply already requested; " + str(error))
                        raise
                    except AgentError as error:
                        raise AgentError(
                            "KakaoTalk reply already requested; " + str(error)
                        ) from None
            self.queue.event("workflow_finished", capture_id + ": " + result)
            return "Test workflow: " + result
        except Exception:
            self.queue.event("workflow_incomplete", "Cycle stopped or failed; no automatic retry")
            raise
