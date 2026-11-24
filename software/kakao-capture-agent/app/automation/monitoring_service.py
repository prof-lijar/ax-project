import queue as commands
import threading
import time
from copy import copy
from datetime import datetime, timezone
from uuid import uuid4

from app.api.bizgo_client import BIZGO_SAMPLE, create_bizgo
from app.automation.device_workflow import DeviceWorkflow
from app.automation.incoming_workflow import IncomingReplyWorkflow
from app.automation.multi_chat import MultiChatWorkflow
from app.automation.saved_image_workflow import SavedImageWorkflow
from app.automation.scroll_controller import ScrollController
from app.automation.test_workflow import OneCycleWorkflow
from app.automation.unified_workflow import UnifiedWorkflow
from app.automation.windows_composer import WindowsComposer, WindowsReplySender
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import (
    TRANSITIONS,
    AgentError,
    Cancelled,
    ForegroundLost,
    ReselectionRequired,
    State,
    TargetUnavailable,
)
from app.storage.chat_paths import chat_queue_key


class MonitoringService(threading.Thread):
    def __init__(
        self,
        desktop,
        capture,
        queue,
        config,
        status,
        preview,
        activity,
        text_preview=lambda _: None,
        setup_ready=lambda: None,
        preview_chat=lambda _: None,
        image_test_output=lambda _: None,
        image_test_text=lambda _: None,
        chat_activity=lambda key, message: None,
    ):
        super().__init__(name="capture", daemon=False)
        self.desktop, self.capture, self.queue, self.config = desktop, capture, queue, config
        self.status, self.preview, self.activity = status, preview, activity
        self.chat_activity = chat_activity
        self.chat_run_keys = []
        self.setup_ready = setup_ready
        self.text_preview, self.preview_chat = text_preview, preview_chat
        self.image_test_output = image_test_output
        self.state = State.STOPPED
        self.reason = ""
        self.stop_input = threading.Event()
        self.stop_input.set()
        self.history_cancel = threading.Event()
        self.shutdown = threading.Event()
        self.commands = commands.Queue()
        self.detector = ChangeDetector(config)
        self.history_detector = ChangeDetector(config)
        self.scroller = ScrollController(
            desktop, capture, config, self.stop_input, self.history_cancel, activity
        )
        self.recoverable = False
        self.auto_focus_recovery = False
        self.next_capture = self.next_recovery = 0
        self.operator_bottom = False
        self.want_live = False
        self.reply_sender = WindowsReplySender(
            WindowsComposer(desktop, self.primary_activity), queue.event, self.stop_input
        )
        self.manual_reply_sender = WindowsReplySender(
            WindowsComposer(desktop, self.primary_activity, require_capture=False),
            queue.event,
            self.stop_input,
        )
        self.test_workflow = OneCycleWorkflow(
            desktop,
            capture,
            queue,
            config,
            self.reply_sender,
            self.stop_input,
            preview,
            lambda message: self.transition(State.INITIALIZING, message),
        )
        self.incoming_workflow = IncomingReplyWorkflow(
            desktop,
            capture,
            queue,
            config,
            self.reply_sender,
            self.stop_input,
            preview,
            lambda message: self.transition(State.INITIALIZING, message),
        )

        self.auto_catch = UnifiedWorkflow(
            desktop,
            capture,
            queue,
            config,
            self.reply_sender,
            self.stop_input,
            preview,
            self.primary_progress,
            text_preview=text_preview,
            activity=self.primary_activity,
        )
        self.general_auto_catch = self.auto_catch
        self.saved_image_workflow = SavedImageWorkflow(
            config,
            queue,
            self.general_auto_catch.jobs,
            self.general_auto_catch.journal,
            self.stop_input,
            lambda message: self.transition(State.INITIALIZING, message),
            image_test_text,
        )
        self.device_workflow = DeviceWorkflow(
            desktop,
            capture,
            queue,
            config,
            self.reply_sender,
            self.stop_input,
            preview,
            self.primary_progress,
            text_preview=text_preview,
            activity=self.primary_activity,
        )

    def primary_activity(self, message):
        if self.config.target is not None:
            self.chat_activity(chat_queue_key(self.config), message)
        self.activity(message)

    def primary_progress(self, message):
        if self.config.target is not None:
            self.chat_activity(chat_queue_key(self.config), message)
        self.transition(State.INITIALIZING, message)

    def transition(self, state, reason=""):
        if state != self.state and state not in TRANSITIONS[self.state]:
            raise RuntimeError(f"Invalid transition {self.state} -> {state}")
        self.state, self.reason = state, reason
        self.status(state.value, reason)
        self.activity(state.value + (": " + reason if reason else ""))
        if state in {State.STOPPED, State.PAUSED}:
            for key in self.chat_run_keys:
                self.chat_activity(key, state.value + (": " + reason if reason else ""))
            if state == State.STOPPED:
                self.chat_run_keys = []
        try:
            self.queue.event("state", state.value + ": " + reason)
        except Exception:
            # The activity log still records the transition when SQLite is unavailable.
            self.activity("Could not persist state audit event; check local storage")

    def command(self, name, payload=None):
        if name == "stop":
            self.auto_focus_recovery = False
            self.want_live = False
            self.stop_input.set()
            self.history_cancel.set()
            # Discard commands waiting before this Stop.
            while True:
                try:
                    self.commands.get_nowait()
                except commands.Empty:
                    break
        elif name == "cancel_history":
            self.history_cancel.set()
            return
        self.commands.put(name if payload is None else (name, payload))

    def suspend_recovery(self):
        """Reserve a manual action while the GUI yields foreground to the chat."""
        self.want_live = self.recoverable = False
        self.auto_focus_recovery = False
        self.stop_input.set()

    def record(self, image, region, mode):
        png = encode_png(image)
        capture_id = None
        detector = self.detector if mode == "live" else self.history_detector
        if detector.ready(image, time.monotonic()) or mode == "history":
            capture_id = self.queue.enqueue(
                png, region, mode, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            detector.accept(image)
            destination = (
                "saved locally" if self.config.local_only or not self.config.api_url else "queued"
            )
            self.activity(f"{mode.title()} capture {destination}: {capture_id}.png")
        else:
            self.activity("Capture checked: unchanged or awaiting visual debounce")
        self.preview(png)
        return capture_id

    def prepare_chat(self):
        """Refresh geometry from the chosen window; saved manual rectangles are never reused."""
        if self.stop_input.is_set():
            raise Cancelled("Chat setup cancelled")
        target = self.config.target
        selection = self.desktop.suggest_chat_region()
        if self.stop_input.is_set():
            raise Cancelled("Chat setup cancelled")
        if self.config.target != target:
            raise ReselectionRequired("Selected conversation changed during setup")
        if self.config.selection != selection:
            self.scroller.calibrated = False
        self.config.selection = selection
        if not self.config.chat_id.strip():
            self.config.chat_id = "chat-" + uuid4().hex[:12]
        self.preview_chat(self.config.target.title if self.config.target else "")
        self.activity("Conversation area detected automatically from the selected window")
        self.setup_ready()

    def initialize(self, confirmed=False):
        self.transition(State.INITIALIZING)
        self.prepare_chat()
        self.scroller.check()
        self.desktop.validate()
        image, _ = self.capture.grab()
        self.preview(encode_png(image))
        self.scroller.check()
        if not confirmed:
            self.scroller.restore()
        self.operator_bottom = confirmed
        self.scroller.operator_confirmed = confirmed
        self.recoverable = False
        self.next_capture = 0
        self.next_recovery = time.monotonic() + self.config.recovery_seconds
        self.transition(
            State.LIVE_MONITORING,
            "Operator confirmed latest position" if confirmed else "Latest position verified",
        )

    def history(self):
        self.transition(State.HISTORY_SCANNING)
        self.history_cancel.clear()
        self.history_detector = ChangeDetector(self.config)
        outcome = "step limit reached; coverage bounded"
        stationary = 0
        first_capture = last_capture = None
        steps = 0
        try:
            initial, region = self.capture.grab()
            first_capture = last_capture = self.record(initial, region, "history")
            for step in range(self.config.max_scroll_steps):
                image, region, change, moving = self.scroller.move(1, history=True)
                steps = step + 1
                self.activity(f"History progress: {step + 1}/{self.config.max_scroll_steps}")
                stationary = stationary + 1 if change < self.config.difference_threshold else 0
                if change >= self.config.difference_threshold:
                    if not moving:
                        raise AgentError(
                            "History movement could not be measured; coverage incomplete"
                        )
                    last_capture = self.record(image, region, "history")
                if stationary >= 3:
                    outcome = "visual boundary reached; coverage approximate"
                    break
        except Cancelled:
            outcome = "cancelled; coverage incomplete"
        except Exception:
            outcome = "failed; coverage incomplete"
            raise
        finally:
            import json

            self.queue.event(
                "history",
                json.dumps(
                    {
                        "outcome": outcome,
                        "steps": steps,
                        "first_capture_id": first_capture,
                        "last_capture_id": last_capture,
                        "coverage": "approximate; not exhaustive",
                    }
                ),
            )
            self.activity("History " + outcome)
        if self.stop_input.is_set():
            raise Cancelled("Stopped")
        self.transition(State.RESTORING_POSITION)
        try:
            verification = self.scroller.restore()
        except Exception:
            self.queue.event("history_restore", "failed; monitoring remains paused")
            raise
        self.queue.event("history_restore", verification)
        self.detector = ChangeDetector(self.config)
        self.transition(State.LIVE_MONITORING, verification)
        self.next_recovery = time.monotonic() + self.config.recovery_seconds

    def dispatch(self, command):
        payload = None
        if isinstance(command, tuple):
            command, payload = command
        if command == "stop":
            self.auto_focus_recovery = False
            self.incoming_workflow.reset()
            self.auto_catch.reset()
            self.recoverable = False
            self.operator_bottom = False
            self.transition(State.STOPPED)
        elif command == "image_test" and self.state == State.STOPPED:
            self.want_live = self.recoverable = self.auto_focus_recovery = False
            self.stop_input.clear()
            self.transition(State.INITIALIZING, "Preparing saved image test")
            try:
                result = self.saved_image_workflow.run(payload)
                if self.stop_input.is_set():
                    raise Cancelled("Image test cancelled")
                self.image_test_output(result)
                self.transition(State.STOPPED, "Image test complete; see Output")
            except Cancelled:
                self.image_test_output(
                    "Image test cancelled. An API request already submitted may still finish."
                )
                raise
            except Exception as error:
                reason = (
                    str(error)
                    if isinstance(error, AgentError)
                    else (
                        f"Image test failed ({type(error).__name__}); check settings and local storage"
                    )
                )
                self.image_test_output(reason)
                raise
            finally:
                self.stop_input.set()
        elif command in ("start", "confirm_bottom") and self.state in (State.STOPPED, State.PAUSED):
            self.want_live = True
            self.stop_input.clear()
            self.initialize(confirmed=command == "confirm_bottom")
        elif command == "history" and self.state == State.LIVE_MONITORING:
            self.history()
        elif command in ("auto_catch", "device_workflow") and self.state == State.STOPPED:
            if isinstance(self.auto_catch, MultiChatWorkflow):
                self.auto_catch = self.auto_catch.base_workflow
            if command == "device_workflow":
                if self.auto_catch is not self.device_workflow:
                    self.general_auto_catch = self.auto_catch
                self.auto_catch = self.device_workflow
            elif self.auto_catch is self.device_workflow:
                self.auto_catch = self.general_auto_catch
            self.want_live = self.recoverable = False
            self.stop_input.clear()
            self.chat_run_keys = [
                chat_queue_key(chat)
                for chat in self.config.agent_configs()
                if chat.target is not None
            ]
            self.transition(
                State.INITIALIZING,
                "Starting 기기위치조정/전원연결"
                if command == "device_workflow"
                else "Starting Run Agent (auto)",
            )
            try:
                if len(self.config.agent_chats) > 1:
                    self.config.validate()
                    self.auto_catch = self.create_multi_chat(command)
                else:
                    self.prepare_chat()
                self.auto_catch.arm()
                self.next_capture = time.monotonic() + self.config.auto_catch_interval_seconds
                self.transition(
                    State.AUTO_CATCHING,
                    f"Watching {len(self.config.agent_chats)} chats in rotation; Stop ends all chats"
                    if isinstance(self.auto_catch, MultiChatWorkflow)
                    else "Watching display changes; captures queue for text extraction, LLM processing, and reply; Stop ends Run Agent (auto)",
                )
            except Exception:
                self.stop_input.set()
                self.auto_catch.reset()
                raise
        elif command == "incoming_test" and self.state == State.STOPPED:
            self.want_live = self.recoverable = False
            self.stop_input.clear()
            self.transition(State.INITIALIZING, "Arming Test Workflow 2")
            try:
                self.prepare_chat()
                self.incoming_workflow.arm()
                self.next_capture = time.monotonic() + self.config.capture_interval_seconds
                self.transition(State.WAITING_FOR_MESSAGE, "Watching for one new incoming message")
            except Exception:
                self.stop_input.set()
                self.incoming_workflow.reset()
                raise
        elif (
            command in ("send_test", "test_workflow", "bizgo_test") and self.state == State.STOPPED
        ):
            self.want_live = self.recoverable = False
            self.stop_input.clear()
            self.transition(
                State.INITIALIZING,
                "Preparing Bizgo sample"
                if command == "bizgo_test"
                else "Preparing test workflow"
                if command == "test_workflow"
                else "Preparing test reply",
            )
            try:
                if command == "bizgo_test":
                    client = create_bizgo(self.config, self.queue.event, force=True)
                    message = client.prepare(BIZGO_SAMPLE, str(uuid4()))
                    result = client.send(message, self.stop_input)
                elif command == "send_test":
                    result = self.manual_reply_sender.send(self.config.test_reply_text)
                else:
                    self.prepare_chat()
                    result = self.test_workflow.run()
                self.transition(State.STOPPED, result)
            finally:
                self.stop_input.set()
        elif command in ("up", "down", "preview", "save_local") and self.state in (
            State.STOPPED,
            State.PAUSED,
        ):
            self.want_live = False
            self.stop_input.clear()
            self.transition(State.INITIALIZING)
            try:
                self.prepare_chat()
                if command in ("preview", "save_local"):
                    self.scroller.check()
                    image, region = self.capture.grab()
                    self.scroller.check()
                    png = encode_png(image)
                    if command == "save_local":
                        # A requested test capture always saves, even if pixels are unchanged.
                        # It never inherits an API destination or alters the live baseline.
                        capture_id = self.queue.enqueue(png, region, "live", local_only=True)
                        self.activity(f"Capture saved locally: {self.queue.image_path(capture_id)}")
                    self.preview(png)
                else:
                    self.scroller.operator_confirmed = False
                    image, region, _, _ = self.scroller.move(1 if command == "up" else -1)
                    self.record(image, region, "history")
                self.transition(
                    State.STOPPED,
                    "Capture saved locally"
                    if command == "save_local"
                    else "Preview ready"
                    if command == "preview"
                    else "Manual scroll complete",
                )
            finally:
                self.stop_input.set()

    def create_multi_chat(self, mode):
        return MultiChatWorkflow(
            self.auto_catch,
            self.config.agent_configs(),
            self.queue,
            self.stop_input,
            self.preview,
            lambda message: self.transition(State.INITIALIZING, message),
            self.text_preview,
            self.activity,
            mode,
            preview_chat=self.preview_chat,
            chat_activity=self.chat_activity,
        )

    def review_scopes(self):
        """Resolve only the currently selected chats, including before a run starts."""
        base = self.auto_catch
        if isinstance(base, MultiChatWorkflow):
            base = base.base_workflow
        scopes = []
        for config in self.config.agent_configs():
            view = copy(base)
            view.config = config
            scopes.append((base.jobs, view.queue_key()))
        return scopes

    def pause(self, error):
        if (
            isinstance(error, ForegroundLost)
            and self.auto_catch.active
            and not self.stop_input.is_set()
        ):
            # Only retry BEFORE a reply attempt. Never clear the operator's Stop event.
            self.auto_focus_recovery = True
            self.recoverable = False
            self.next_recovery = time.monotonic() + 2
            reason = "Run Agent (auto) waiting for chat focus; retrying automatically; Stop cancels"
            if self.state != State.PAUSED or self.reason != reason:
                self.transition(State.PAUSED, reason)
            return
        self.auto_focus_recovery = False
        self.incoming_workflow.reset()
        self.auto_catch.reset()
        self.recoverable = (
            self.want_live
            and isinstance(error, TargetUnavailable)
            and not isinstance(error, ReselectionRequired)
        )
        self.operator_bottom = False
        self.scroller.operator_confirmed = False
        self.stop_input.set()
        self.next_recovery = time.monotonic() + 2
        if self.state != State.PAUSED or self.reason != str(error):
            self.transition(State.PAUSED, str(error))

    def try_recover(self):
        # Stay paused until the desktop is usable. Validation sends no input and
        # captures no pixels; repeated focus failures should not churn the state log.
        self.next_recovery = time.monotonic() + 2
        self.desktop.validate()
        if not self.want_live or self.shutdown.is_set():
            return
        self.stop_input.clear()
        self.initialize()

    def poll_incoming(self):
        result = self.incoming_workflow.tick()
        self.next_capture = time.monotonic() + self.config.capture_interval_seconds
        if result is not None:
            self.incoming_workflow.reset()
            self.stop_input.set()
            self.transition(State.STOPPED, result)
        elif self.state != State.WAITING_FOR_MESSAGE:
            self.transition(State.WAITING_FOR_MESSAGE, "Watching for one new incoming message")

    def poll_auto_catch(self):
        self.auto_catch.tick()
        self.next_capture = time.monotonic() + self.config.auto_catch_interval_seconds
        if self.state != State.AUTO_CATCHING:
            self.transition(
                State.AUTO_CATCHING,
                self.auto_catch.waiting_reason
                or f"Watching for incoming text; {self.auto_catch.reply_count} replies submitted",
            )

    def try_recover_auto_focus(self):
        self.next_recovery = time.monotonic() + 2
        if not self.auto_focus_recovery or self.stop_input.is_set() or self.shutdown.is_set():
            return
        self.auto_catch.check()
        self.desktop.activate_target(self.stop_input)
        self.auto_catch.check()
        self.desktop.validate()
        self.auto_focus_recovery = False
        self.next_capture = 0
        self.transition(
            State.AUTO_CATCHING, "Chat focus recovered; continuing from previous capture"
        )

    def run(self):
        while not self.shutdown.is_set():
            try:
                try:
                    command = self.commands.get(timeout=0.1)
                except commands.Empty:
                    command = None
                if command:
                    self.dispatch(command)
                now = time.monotonic()
                if self.state == State.LIVE_MONITORING and not self.stop_input.is_set():
                    if now >= self.next_recovery:
                        self.transition(State.RESTORING_POSITION)
                        self.scroller.restore()
                        self.transition(State.LIVE_MONITORING)
                        self.next_recovery = now + self.config.recovery_seconds
                    if now >= self.next_capture:
                        image, region = self.capture.grab()
                        self.record(image, region, "live")
                        self.next_capture = now + self.config.capture_interval_seconds
                elif self.state == State.AUTO_CATCHING and not self.stop_input.is_set():
                    if now >= self.next_capture:
                        self.poll_auto_catch()
                elif self.state == State.WAITING_FOR_MESSAGE and not self.stop_input.is_set():
                    if now >= self.next_capture:
                        self.poll_incoming()
                elif (
                    self.state == State.PAUSED
                    and self.auto_focus_recovery
                    and now >= self.next_recovery
                ):
                    self.try_recover_auto_focus()
                elif (
                    self.state == State.PAUSED
                    and self.recoverable
                    and self.config.auto_resume
                    and now >= self.next_recovery
                ):
                    self.try_recover()
            except Cancelled:
                self.auto_focus_recovery = False
                self.incoming_workflow.reset()
                self.auto_catch.reset()
                self.stop_input.set()
                self.transition(State.STOPPED, "Input stopped")
            except AgentError as error:
                if self.state == State.STOPPED:
                    self.status(State.STOPPED.value, str(error))
                else:
                    self.pause(error)
            except Exception as error:
                self.auto_focus_recovery = False
                self.incoming_workflow.reset()
                self.auto_catch.reset()
                # Do not expose OS exception text, which may include private paths/content.
                self.stop_input.set()
                self.recoverable = False
                reason = (
                    f"Operation failed ({type(error).__name__}); check storage and configuration"
                )
                self.state, self.reason = State.PAUSED, reason
                self.status(State.PAUSED.value, reason)
                self.activity(reason)
        # Shutdown may exit before the queued Stop command is dispatched.
        self.stop_input.set()
        self.auto_catch.reset()
