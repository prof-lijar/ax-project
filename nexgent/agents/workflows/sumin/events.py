"""Normalize only authorized channel events; ignore bots, edits, DMs and other teams."""

from ax_contracts.sumin import SuminTask
from ax_integrations.slack import CHANNEL_ID_PATTERN

from .settings import Settings


def normalize(payload: dict, settings: Settings) -> list[SuminTask]:
    if (
        settings.team_id is None
        or payload.get("type") != "event_callback"
        or payload.get("team_id") != settings.team_id
    ):
        return []
    event = payload.get("event", {})
    if not isinstance(event, dict):
        raise TypeError("invalid Slack event")
    channel = event.get("channel", event.get("channel_id"))
    if (
        not isinstance(channel, str)
        or not CHANNEL_ID_PATTERN.fullmatch(channel)
        or event.get("channel_type") in {"im", "mpim"}
        or event.get("bot_id")
        or event.get("user", event.get("user_id")) == settings.bot_user_id
    ):
        return []
    common = {
        "event_id": payload["event_id"],
        "team_id": settings.team_id,
        "channel_id": channel,
        "user_id": event.get("user", event.get("user_id", "")),
        "text": event.get("text", ""),
        "message_ts": event.get("ts"),
        "thread_ts": event.get("thread_ts"),
    }
    tasks = []
    if event.get("type") == "app_mention":
        tasks.append(SuminTask(kind="search", **common))
    if event.get("type") == "file_shared":
        return [SuminTask(kind="archive", file_id=event.get("file_id"), **common)]
    if event.get("type") == "app_mention" or (
        event.get("type") == "message" and event.get("subtype") in {None, "file_share"}
    ):
        files = event.get("files", [])
        if not isinstance(files, list) or len(files) > 20:
            raise ValueError("invalid Slack file list")
        tasks.extend(
            SuminTask(kind="archive", file_id=f["id"], **common) for f in files
        )
    return tasks
