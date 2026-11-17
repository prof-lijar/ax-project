import json
import math
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from app.models import Region, Selection, Target


def validate_endpoint(url, allow_local_http=False):
    if not url:
        return
    parsed = urlsplit(url)
    try:
        parsed.port
    except ValueError:
        raise ValueError("API URL has an invalid port") from None
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("API URL must have a host and no embedded credentials or fragment")
    if parsed.scheme == "https":
        return
    if allow_local_http and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}:
        return
    raise ValueError("Use HTTPS, or enable test HTTP for a literal loopback address")


@dataclass
class Config:
    version: int = 1
    device_id: str = field(default_factory=lambda: str(uuid4()))
    chat_id: str = ""
    api_url: str = ""
    local_only: bool = False
    allow_local_http: bool = False
    llm_url: str = ""
    llm_model: str = ""
    llm_supports_vision: bool = False
    llm_allow_http: bool = False
    llm_timeout_seconds: int = 120
    capture_interval_seconds: float = 2
    change_detection: bool = True
    difference_threshold: float = 0.01
    pixel_threshold: int = 20
    debounce_seconds: float = 0.5
    max_debounce_seconds: float = 2
    scroll_step: int = 3
    scroll_delay_ms: int = 800
    max_scroll_steps: int = 50
    overlap_target_percent: int = 30
    recovery_seconds: int = 30
    request_timeout_seconds: int = 15
    max_retries: int = 5
    storage_limit_bytes: int = 5 * 1024**3
    uploaded_retention_hours: int = 0
    metadata_retention_days: int = 30
    auto_resume: bool = True
    launch_at_signin: bool = False
    auto_start_monitoring: bool = False
    target: Target | None = None
    selection: Selection | None = None

    def validate(self):
        validate_endpoint(self.api_url, self.allow_local_http)
        from app.api.workflow_llm import validate_llm_url

        if self.llm_url:
            validate_llm_url(self.llm_url, self.llm_allow_http)
        if not isinstance(self.llm_model, str):
            raise ValueError("LLM model must be text")
        ranges = {
            "llm_timeout_seconds": (5, 300),
            "capture_interval_seconds": (1, 60),
            "difference_threshold": (0.0001, 1),
            "pixel_threshold": (1, 255),
            "debounce_seconds": (0, 10),
            "max_debounce_seconds": (0.1, 30),
            "scroll_step": (1, 10),
            "scroll_delay_ms": (200, 10000),
            "max_scroll_steps": (1, 500),
            "overlap_target_percent": (10, 90),
            "recovery_seconds": (5, 3600),
            "request_timeout_seconds": (1, 120),
            "max_retries": (0, 20),
            "storage_limit_bytes": (1024**2, 1024**5),
            "uploaded_retention_hours": (0, 8760),
            "metadata_retention_days": (1, 3650),
        }
        for name, (low, high) in ranges.items():
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"Invalid {name}: expected {low} through {high}")
        for name in (
            "llm_timeout_seconds",
            "pixel_threshold",
            "scroll_step",
            "scroll_delay_ms",
            "max_scroll_steps",
            "overlap_target_percent",
            "recovery_seconds",
            "request_timeout_seconds",
            "max_retries",
            "storage_limit_bytes",
            "uploaded_retention_hours",
            "metadata_retention_days",
        ):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        for name in (
            "llm_supports_vision",
            "llm_allow_http",
            "allow_local_http",
            "local_only",
            "change_detection",
            "auto_resume",
            "launch_at_signin",
            "auto_start_monitoring",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false")
        if self.max_debounce_seconds < self.debounce_seconds:
            raise ValueError("Maximum debounce must be at least the debounce period")
        if (
            not isinstance(self.device_id, str)
            or not self.device_id.strip()
            or not isinstance(self.chat_id, str)
        ):
            raise ValueError("Device ID is required and chat ID must be text")
        if self.selection:
            self.selection.region.validate()


def data_directory():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "KakaoCaptureAgent"


def load(path):
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Unsupported configuration version")
    if data.get("target"):
        data["target"] = Target(**data["target"])
    if data.get("selection"):
        s = data["selection"]
        data["selection"] = Selection(
            Region(**s["region"]), s["client_width"], s["client_height"], s["dpi"]
        )
    result = Config(**{k: v for k, v in data.items() if k in {f.name for f in fields(Config)}})
    result.validate()
    return result


def save(path, config):
    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(asdict(config), file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp, path)
