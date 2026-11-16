import queue as commands
import threading
import time
from datetime import datetime, timezone

from app.automation.scroll_controller import ScrollController
from app.capture.change_detector import ChangeDetector
from app.capture.screen_capture import encode_png
from app.models import (
    TRANSITIONS,
    AgentError,
    Cancelled,
    ReselectionRequired,
    State,
    TargetUnavailable,
)


class MonitoringService(threading.Thread):
    def __init__(self, desktop, capture, queue, config, status, preview, activity):
        super().__init__(name="capture", daemon=False)
        self.desktop, self.capture, self.queue, self.config = desktop, capture, queue, config
        self.status, self.preview, self.activity = status, preview, activity
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
        self.next_capture = self.next_recovery = 0
        self.operator_bottom = False
        self.want_live = False

    def transition(self, state, reason=""):
        if state != self.state and state not in TRANSITIONS[self.state]:
            raise RuntimeError(f"Invalid transition {self.state} -> {state}")
        self.state, self.reason = state, reason
        self.status(state.value, reason)
        self.activity(state.value + (": " + reason if reason else ""))
        try:
            self.queue.event("state", state.value + ": " + reason)
        except Exception:
            # The activity log still records the transition when SQLite is unavailable.
            self.activity("Could not persist state audit event; check local storage")

    def command(self, name):
        if name == "stop":
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
        self.commands.put(name)

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

    def initialize(self, confirmed=False):
        self.scroller.check()
        self.transition(State.INITIALIZING)
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
        if command == "stop":
            self.recoverable = False
            self.operator_bottom = False
            self.transition(State.STOPPED)
        elif command in ("start", "confirm_bottom") and self.state in (State.STOPPED, State.PAUSED):
            self.want_live = True
            self.stop_input.clear()
            self.initialize(confirmed=command == "confirm_bottom")
        elif command == "history" and self.state == State.LIVE_MONITORING:
            self.history()
        elif command in ("up", "down", "preview", "save_local") and self.state in (
            State.STOPPED,
            State.PAUSED,
        ):
            self.want_live = False
            self.stop_input.clear()
            self.transition(State.INITIALIZING)
            try:
                if command in ("preview", "save_local"):
                    self.scroller.check()
                    image, region = self.capture.grab()
                    self.scroller.check()
                    png = encode_png(image)
                    if command == "save_local":
                        # A requested test capture always saves, even if pixels are unchanged.
                        # It never inherits an API destination or alters the live baseline.
                        capture_id = self.queue.enqueue(png, region, "live", local_only=True)
                        self.activity(
                            f"Capture saved locally: {self.queue.images / (capture_id + '.png')}"
                        )
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

    def pause(self, error):
        self.recoverable = (
            self.want_live
            and isinstance(error, TargetUnavailable)
            and not isinstance(error, ReselectionRequired)
        )
        self.operator_bottom = False
        self.scroller.operator_confirmed = False
        self.stop_input.set()
        self.next_recovery = time.monotonic() + 2
        self.transition(State.PAUSED, str(error))

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
                elif (
                    self.state == State.PAUSED
                    and self.recoverable
                    and self.config.auto_resume
                    and now >= self.next_recovery
                ):
                    self.stop_input.clear()
                    self.initialize()
            except Cancelled:
                self.stop_input.set()
                self.transition(State.STOPPED, "Input stopped")
            except AgentError as error:
                if self.state == State.STOPPED:
                    self.status(State.STOPPED.value, str(error))
                else:
                    self.pause(error)
            except Exception as error:
                # Do not expose OS exception text, which may include private paths/content.
                self.stop_input.set()
                self.recoverable = False
                reason = (
                    f"Operation failed ({type(error).__name__}); check storage and configuration"
                )
                self.state, self.reason = State.PAUSED, reason
                self.status(State.PAUSED.value, reason)
                self.activity(reason)
