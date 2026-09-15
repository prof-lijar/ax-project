import os
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    team_id: str
    bot_user_id: str
    channels: frozenset[str]
    bot_token: str = field(repr=False)
    signing_secret: str = field(repr=False)
    database_dsn: str = field(repr=False)
    nextcloud_url: str
    nextcloud_user: str
    nextcloud_password: str = field(repr=False)
    root: str = "Slack"
    max_file_bytes: int = 25 * 1024 * 1024

    def __post_init__(self):
        if not re.fullmatch(r"T[A-Z0-9]+", self.team_id):
            raise ValueError("invalid Sumin team ID")
        if not re.fullmatch(r"U[A-Z0-9]+", self.bot_user_id):
            raise ValueError("invalid Sumin bot user ID")
        if not self.channels or any(
            not re.fullmatch(r"[CG][A-Z0-9]{8,}", c) for c in self.channels
        ):
            raise ValueError("Sumin requires explicit Slack channel IDs")
        if (
            not self.bot_token.startswith("xoxb-")
            or not self.signing_secret
            or not self.database_dsn
            or not self.nextcloud_password
        ):
            raise ValueError("missing Sumin credentials")
        if any(p in {"", ".", ".."} for p in self.root.split("/")) or "\\" in self.root:
            raise ValueError("invalid Sumin root folder")
        if not 1 <= self.max_file_bytes <= 100 * 1024 * 1024:
            raise ValueError("Sumin file limit must be 1 byte to 100 MiB")

    @classmethod
    def from_env(cls):
        def required(key):
            value = os.environ.get("SUMIN_" + key, "")
            if not value:
                raise ValueError("SUMIN_" + key + " is required")
            return value

        return cls(
            team_id=required("SLACK_TEAM_ID"),
            bot_user_id=required("SLACK_BOT_USER_ID"),
            channels=frozenset(
                c.strip() for c in required("SLACK_CHANNEL_IDS").split(",")
            ),
            bot_token=required("SLACK_BOT_TOKEN"),
            signing_secret=required("SLACK_SIGNING_SECRET"),
            database_dsn=required("DATABASE_DSN"),
            nextcloud_url=required("NEXTCLOUD_URL"),
            nextcloud_user=required("NEXTCLOUD_USER"),
            nextcloud_password=required("NEXTCLOUD_PASSWORD"),
            root=os.environ.get("SUMIN_NEXTCLOUD_ROOT", "Slack"),
            max_file_bytes=int(
                os.environ.get("SUMIN_MAX_FILE_BYTES", str(25 * 1024 * 1024))
            ),
        )
