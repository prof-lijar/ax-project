from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class ScoutSettings:
    """Configuration owned solely by the standalone Scout application."""

    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    output_root: Path = PROJECT_ROOT / "var"
    search_call_limit: int = 3
    search_result_limit: int = 6
    fetch_page_limit: int = 3
    max_agent_llm_calls: int = 8
    request_timeout_seconds: float = 12.0
    max_redirects: int = 3
    max_response_bytes: int = 1_048_576
    max_extracted_characters: int = 12_000
    slack_bot_token: str | None = field(default=None, repr=False)
    slack_channel_id: str | None = None

    @classmethod
    def from_env(cls) -> ScoutSettings:
        output_root = Path(os.getenv("SCOUT_OUTPUT_ROOT", "var"))
        if not output_root.is_absolute():
            output_root = PROJECT_ROOT / output_root
        return cls(
            api_base=_clean_env("OPENAI_API_BASE"),
            api_key=_clean_env("OPENAI_API_KEY"),
            model=_clean_env("SCOUT_MODEL"),
            output_root=output_root.resolve(),
            slack_bot_token=_clean_env("SCOUT_SLACK_BOT_TOKEN"),
            slack_channel_id=_clean_env("SCOUT_SLACK_CHANNEL_ID"),
        )

    @property
    def is_model_ready(self) -> bool:
        if not (self.api_base and self.api_key and self.model):
            return False
        parsed = urlsplit(self.api_base)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @property
    def litellm_model(self) -> str:
        model = self.model or "openai/unconfigured-scout-model"
        return model if "/" in model else f"openai/{model}"


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
