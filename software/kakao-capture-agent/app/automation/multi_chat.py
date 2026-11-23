"""Run the unchanged workflow per chat, serializing all desktop work on one thread."""

from app.api.workflow_llm import check_cancel
from app.automation.reply_service import TestReplySender
from app.automation.window_manager import WindowsDesktop
from app.automation.windows_composer import WindowsComposer
from app.capture.screen_capture import ScreenCapture
from app.models import AgentError, Cancelled
from app.storage.chat_paths import chat_queue_key


class MultiChatWorkflow:
    def __init__(
        self,
        base_workflow,
        configs,
        queue,
        cancel,
        preview,
        progress,
        text_preview,
        activity,
        mode,
        desktop_factory=WindowsDesktop,
        capture_factory=ScreenCapture,
        sender_factory=None,
        preview_chat=lambda _: None,
        chat_activity=lambda key, message: None,
    ):
        self.base_workflow, self.cancel, self.mode = base_workflow, cancel, mode
        self.workflows = []
        self.active = False
        self.waiting_reason = ""
        for index, config in enumerate(configs):
            name = f"Chat {index + 1}: {config.target.title}"
            key = chat_queue_key(config)

            def report(message, name=name, key=key):
                chat_activity(key, message)
                progress(f"{name} — {message}")

            def log(message, name=name, key=key):
                chat_activity(key, message)
                activity(f"{name} — {message}")

            def show(png, name=name):
                preview_chat(name)
                preview(png)

            def show_text(text, name=name):
                text_preview(f"{name}\n{text}" if text else "")

            desktop = desktop_factory(config)
            sender = (
                sender_factory(desktop, cancel)
                if sender_factory
                else TestReplySender(WindowsComposer(desktop, log), queue.event, cancel)
            )
            workflow = type(base_workflow)(
                desktop,
                capture_factory(desktop),
                queue,
                config,
                sender,
                cancel,
                show,
                report,
                text_preview=show_text,
                activity=log,
                # Share storage without re-running crash recovery while another
                # chat has an in-flight job. Keys still isolate every chat's FIFO.
                jobs_factory=lambda _: base_workflow.jobs,
            )
            self.workflows.append(workflow)

    @property
    def reply_count(self):
        return sum(workflow.reply_count for workflow in self.workflows)

    def reset(self):
        self.active = False
        # Signal every inference worker before waiting for any one of them.
        for workflow in self.workflows:
            if workflow.work_cancel is not None:
                workflow.work_cancel.set()
        for workflow in self.workflows:
            workflow.reset()

    def check(self):
        check_cancel(self.cancel)
        for workflow in self.workflows:
            workflow.check()

    def arm(self):
        self.reset()
        try:
            # Check all windows/layouts before the first chat can send a greeting
            # or enqueue its startup message. Selection remains fixed for this run.
            for index, workflow in enumerate(self.workflows):
                check_cancel(self.cancel)
                try:
                    workflow.config.selection = workflow.desktop.suggest_chat_region()
                except Cancelled:
                    raise
                except AgentError as error:
                    raise AgentError(f"Chat {index + 1}: {error}; all chats paused") from error
            for index, workflow in enumerate(self.workflows):
                check_cancel(self.cancel)
                try:
                    workflow.arm()
                except Cancelled:
                    raise
                except AgentError as error:
                    raise AgentError(f"Chat {index + 1}: {error}; all chats paused") from error
            self.active = True
        except Exception:
            self.cancel.set()
            self.reset()
            raise

    def tick(self):
        self.check()
        if not self.active:
            raise AgentError("Multi-chat monitoring is not armed")
        for index, workflow in enumerate(self.workflows):
            check_cancel(self.cancel)
            try:
                # tick activates and verifies this exact window, captures it, then
                # sends only this chat's completed reply. Inference runs separately.
                workflow.tick()
            except Cancelled:
                raise
            except AgentError as error:
                # Do not let the single-chat focus recovery activate the primary
                # window for a failure belonging to a different conversation.
                raise AgentError(f"Chat {index + 1}: {error}; all chats paused") from error
        self.waiting_reason = (
            f"Watching {len(self.workflows)} chats in rotation; "
            f"{self.reply_count} replies submitted"
        )
