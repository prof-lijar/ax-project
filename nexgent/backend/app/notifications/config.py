import json
import os
import re

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class NotificationSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    bot_token: SecretStr = SecretStr("")
    service_token: SecretStr = SecretStr("")
    channels: dict[str, str] = Field(default_factory=dict)
    deployment: str = Field(default="default", min_length=1, max_length=200)
    concurrency: int = Field(default=4, ge=1, le=32)
    max_attempts: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=10, ge=1, le=60)
    poll_seconds: float = Field(default=1, ge=0.1, le=30)

    @model_validator(mode="after")
    def validate_configuration(self):
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", alias)
               or not re.fullmatch(r"[CG][A-Z0-9]{8,31}", channel)
               for alias, channel in self.channels.items()):
            raise ValueError("Slack destinations must map aliases to channel IDs")
        if self.enabled and (not self.bot_token.get_secret_value().strip() or not self.channels):
            raise ValueError("Enabled Slack notifications require a bot token and channels")
        token = self.service_token.get_secret_value()
        if token and (len(token) < 32 or len(token) > 512 or not token.isascii() or any(c.isspace() for c in token)):
            raise ValueError("The notification service token must be 32-512 non-whitespace ASCII characters")
        return self

    @property
    def lease_seconds(self) -> float:
        return self.timeout_seconds + 30


def load_notification_settings() -> NotificationSettings:
    # Missing configuration is a supported state. No credentials are needed to boot.
    try:
        return NotificationSettings(
            enabled=os.getenv("NEXGENT_SLACK_ENABLED", "false"),
            bot_token=os.getenv("NEXGENT_SLACK_BOT_TOKEN", ""),
            service_token=os.getenv("NEXGENT_NOTIFICATION_SERVICE_TOKEN", ""),
            channels=json.loads(os.getenv("NEXGENT_SLACK_CHANNELS", "{}")),
            deployment=os.getenv("NEXGENT_NOTIFICATION_DEPLOYMENT", os.getenv("AX_CHAT_DEPLOYMENT", "default")),
            concurrency=os.getenv("NEXGENT_NOTIFICATION_CONCURRENCY", "4"),
            max_attempts=os.getenv("NEXGENT_NOTIFICATION_MAX_ATTEMPTS", "5"),
            timeout_seconds=os.getenv("NEXGENT_SLACK_TIMEOUT_SECONDS", "10"),
            poll_seconds=os.getenv("NEXGENT_NOTIFICATION_POLL_SECONDS", "1"),
        )
    except (ValueError, TypeError):
        # Pydantic errors can contain input values. Never expose secret env values.
        raise RuntimeError("Invalid notification configuration; check the documented environment variables") from None
