import time

from app.capture.change_detector import difference, displacement, gray
from app.models import AgentError, Cancelled


class ScrollController:
    def __init__(self, desktop, capture, config, stop, history_cancel, notify):
        self.desktop, self.capture, self.config = desktop, capture, config
        self.stop, self.history_cancel, self.notify = stop, history_cancel, notify
        self.calibrated = False
        self.operator_confirmed = False
        self.step = 1  # Establish response before using configured upper bound.

    def check(self, history=False):
        if self.stop.is_set() or (history and self.history_cancel.is_set()):
            raise Cancelled("History cancelled" if history else "Stopped")

    def settle(self, history=False):
        deadline = time.monotonic() + self.config.scroll_delay_ms / 1000
        while time.monotonic() < deadline:
            self.check(history)
            self.stop.wait(min(0.05, max(0, deadline - time.monotonic())))

    def move(self, direction, history=False):
        self.check(history)
        before, _ = self.capture.grab()
        self.notify(f"Scrolling {'up' if direction > 0 else 'down'}: {self.step} wheel notch(es)")
        for _ in range(self.step):
            self.check(history)
            self.desktop.scroll(direction, self.stop)
        self.settle(history)
        after, region = self.capture.grab()
        dy, confidence = displacement(before, after)
        change = difference(gray(before), gray(after), self.config.pixel_threshold)
        moving = abs(dy) >= 2 and confidence >= 0.8 and dy * direction > 0
        if moving:
            self.calibrated = True
            overlap = 1 - abs(dy) / region.height
            desired = self.config.overlap_target_percent / 100
            if overlap < desired:
                self.step = max(1, self.step - 1)
                raise AgentError(
                    "Insufficient screenshot overlap; coverage incomplete. Reduce wheel settings in Windows"
                )
            if overlap > desired + 0.2:
                self.step = min(self.config.scroll_step, self.step + 1)
        return after, region, change, moving

    def restore(self):
        self.notify("Verifying latest-message position")
        stationary = 0
        for _ in range(self.config.max_scroll_steps):
            self.check()
            native = self.desktop.at_bottom()
            if native is True:
                return "standard scrollbar"
            _, _, change, _ = self.move(-1)
            stationary = stationary + 1 if change < self.config.difference_threshold else 0
            if native is None and stationary >= 3:
                if self.calibrated:
                    return "visual boundary (approximate)"
                if self.operator_confirmed:
                    return "operator-confirmed visual boundary (approximate)"
                raise AgentError(
                    "Cannot verify bottom: scroll response uncalibrated. Use Up/Down, or confirm latest position"
                )
        raise AgentError(
            "Return to latest messages exceeded the step limit; monitoring remains paused"
        )
