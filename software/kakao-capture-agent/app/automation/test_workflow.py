"""One operator-triggered capture → vision → simulated summary → reply cycle."""

from app.api.workflow_llm import LLMSettings, WorkflowLLM, check_cancel, llm_token
from app.capture.screen_capture import encode_png
from app.models import AgentError


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
    ):
        self.desktop, self.capture, self.queue, self.config = desktop, capture, queue, config
        self.sender, self.cancel = sender, cancel
        self.preview, self.progress, self.llm_factory = preview, progress, llm_factory

    def run(self):
        check_cancel(self.cancel)
        llm = self.llm_factory(self.config)
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
            self.progress("Sending the test summary to the selected conversation")
            # Sender reactivates/revalidates the exact target and composer before any typing.
            result = self.sender.send(reply)
            self.queue.event("workflow_finished", capture_id + ": " + result)
            return "Test workflow: " + result
        except Exception:
            self.queue.event("workflow_incomplete", "Cycle stopped or failed; no automatic retry")
            raise
