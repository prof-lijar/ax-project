"""Portable values shared by desktop, queue and HTTP adapters."""

from dataclasses import asdict, dataclass
from enum import Enum


class AgentError(Exception):
    """Operator-facing error; messages must never contain credentials or chat content."""


class TargetUnavailable(AgentError):
    pass


class ReselectionRequired(TargetUnavailable):
    pass


class StorageFull(AgentError):
    pass


class Cancelled(AgentError):
    pass


@dataclass(frozen=True)
class SubmissionObservation:
    message: str
    composer_cleared: bool = False


class State(str, Enum):
    STOPPED = "STOPPED"
    INITIALIZING = "INITIALIZING"
    WAITING_FOR_MESSAGE = "WAITING_FOR_MESSAGE"
    LIVE_MONITORING = "LIVE_MONITORING"
    HISTORY_SCANNING = "HISTORY_SCANNING"
    RESTORING_POSITION = "RESTORING_POSITION"
    PAUSED = "PAUSED"


TRANSITIONS = {
    State.STOPPED: {State.INITIALIZING},
    State.INITIALIZING: {
        State.WAITING_FOR_MESSAGE,
        State.LIVE_MONITORING,
        State.PAUSED,
        State.STOPPED,
    },
    State.WAITING_FOR_MESSAGE: {State.INITIALIZING, State.PAUSED, State.STOPPED},
    State.LIVE_MONITORING: {
        State.HISTORY_SCANNING,
        State.RESTORING_POSITION,
        State.PAUSED,
        State.STOPPED,
    },
    State.HISTORY_SCANNING: {State.RESTORING_POSITION, State.PAUSED, State.STOPPED},
    State.RESTORING_POSITION: {State.LIVE_MONITORING, State.PAUSED, State.STOPPED},
    State.PAUSED: {State.INITIALIZING, State.STOPPED},
}


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    def validate(self, minimum=32):
        if any(type(v) is not int for v in asdict(self).values()):
            raise ValueError("Region coordinates must be integers")
        if self.width < minimum or self.height < minimum:
            raise ValueError(f"Select a region at least {minimum} × {minimum} pixels")

    def contains(self, other):
        return (
            self.left <= other.left
            and self.top <= other.top
            and self.left + self.width >= other.left + other.width
            and self.top + self.height >= other.top + other.height
        )

    def intersects(self, other):
        return (
            self.left < other.left + other.width
            and other.left < self.left + self.width
            and self.top < other.top + other.height
            and other.top < self.top + self.height
        )

    @property
    def center(self):
        return self.left + self.width // 2, self.top + self.height // 2


def covered_by_monitors(region, monitors):
    """Union coverage, including negative origins and gaps in multi-monitor layouts."""
    remaining = [region]
    for monitor in monitors:
        pieces = []
        for r in remaining:
            x0, y0 = max(r.left, monitor.left), max(r.top, monitor.top)
            x1 = min(r.left + r.width, monitor.left + monitor.width)
            y1 = min(r.top + r.height, monitor.top + monitor.height)
            if x0 >= x1 or y0 >= y1:
                pieces.append(r)
                continue
            for x, y, w, h in [
                (r.left, r.top, r.width, y0 - r.top),
                (r.left, y1, r.width, r.top + r.height - y1),
                (r.left, y0, x0 - r.left, y1 - y0),
                (x1, y0, r.left + r.width - x1, y1 - y0),
            ]:
                if w > 0 and h > 0:
                    pieces.append(Region(x, y, w, h))
        remaining = pieces
    return not remaining


@dataclass(frozen=True)
class Target:
    hwnd: int
    pid: int
    process_started: str
    executable: str
    window_class: str
    title: str


@dataclass(frozen=True)
class Selection:
    region: Region  # physical client-relative coordinates
    client_width: int
    client_height: int
    dpi: int

    def resolve(self, client, dpi, monitors):
        self.region.validate()
        if (client.width, client.height, dpi) != (self.client_width, self.client_height, self.dpi):
            raise ReselectionRequired(
                "Window size or display scaling changed; select the region again"
            )
        result = Region(
            client.left + self.region.left,
            client.top + self.region.top,
            self.region.width,
            self.region.height,
        )
        if not client.contains(result) or not covered_by_monitors(result, monitors):
            raise ReselectionRequired("Selected region is outside the target or visible displays")
        return result
