import os
import re
from dataclasses import dataclass, field, replace

from ax_integrations.slack_files import SlackFiles


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(repr=False)
    database_dsn: str = field(repr=False)
    nextcloud_url: str
    nextcloud_user: str
    nextcloud_password: str = field(repr=False)
    app_token: str = field(default="", repr=False)
    signing_secret: str = field(default="", repr=False)
    # Discovered from the bot token, never loaded from environment overrides.
    team_id: str | None = None
    bot_user_id: str | None = None
    nextcloud_ca_bundle: str | None = None
    nextcloud_verify_ssl: bool = True
    root: str = "Slack"
    max_file_bytes: int = 25 * 1024 * 1024

    def __post_init__(self):
        if self.team_id is not None and not re.fullmatch(r"T[A-Z0-9]+", self.team_id):
            raise ValueError("invalid Sumin team ID")
        if self.bot_user_id is not None and not re.fullmatch(
            r"[UW][A-Z0-9]+", self.bot_user_id
        ):
            raise ValueError("invalid Sumin bot user ID")
        if (self.team_id is None) != (self.bot_user_id is None):
            raise ValueError("incomplete Sumin identity")
        if (
            not self.bot_token.startswith("xoxb-")
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
            value = os.environ.get(key, "")
            if not value:
                raise ValueError(key + " is required")
            return value

        verify_ssl = os.environ.get("SUMIN_NEXTCLOUD_VERIFY_SSL", "true").strip().lower()
        if verify_ssl not in {"true", "false"}:
            raise ValueError("SUMIN_NEXTCLOUD_VERIFY_SSL must be true or false")

        return cls(
            bot_token=required("SUMIN_SLACK_BOT_TOKEN"),
            signing_secret=os.environ.get("SUMIN_SLACK_SIGNING_SECRET", ""),
            app_token=os.environ.get("SUMIN_SLACK_APP_TOKEN", ""),
            database_dsn=required("AGENT_DATABASE_DSN"),
            nextcloud_url=required("SUMIN_NEXTCLOUD_URL"),
            nextcloud_user=required("SUMIN_NEXTCLOUD_USER"),
            nextcloud_password=required("SUMIN_NEXTCLOUD_PASSWORD"),
            nextcloud_ca_bundle=os.environ.get("SUMIN_NEXTCLOUD_CA_BUNDLE") or None,
            nextcloud_verify_ssl=verify_ssl == "true",
            root=os.environ.get("SUMIN_NEXTCLOUD_ROOT", "Slack"),
            max_file_bytes=int(
                os.environ.get("SUMIN_MAX_FILE_BYTES", str(25 * 1024 * 1024))
            ),
        )

    async def discover_identity(self, slack: SlackFiles):
        identity = await slack.identity()
        return replace(
            self, team_id=identity["team_id"], bot_user_id=identity["user_id"]
        )
