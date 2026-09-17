"""Sumin archive policy and model-directed file discovery; file contents are never model input."""

import json
import re
from html import escape

from ax_contracts.sumin import SuminTask
from ax_integrations.file_http import FileIntegrationError
from ax_integrations.nextcloud import Nextcloud, path_component
from ax_integrations.slack import SlackMessage
from ax_integrations.slack_files import MemberSlackService, SlackFiles

from .search import FileSearchAgent
from .settings import Settings
from .store import Store


class Sumin:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        slack: SlackFiles,
        cloud: Nextcloud,
        sender: MemberSlackService,
        search_agent=None,
    ):
        self.settings, self.store, self.slack = settings, store, slack
        self.cloud, self.sender = cloud, sender
        self.search_agent = search_agent or FileSearchAgent(store, cloud)

    async def run(self, task: SuminTask) -> str:
        # Re-authorize queued work using current membership, including after removal.
        if self.settings.team_id is None or task.team_id != self.settings.team_id:
            raise FileIntegrationError("channel_not_authorized")
        info = await self.slack.member_channel(task.channel_id)
        folder = await self.store.folder(
            task.team_id,
            task.channel_id,
            f"{self.settings.root}/{path_component(info['name'])}",
        )
        if task.kind == "archive":
            await self.archive(task, folder)
            return "archived"
        await self.search(task, folder)
        return "replied"

    async def archive(self, task: SuminTask, folder: str) -> None:
        file = (await self.slack.info("files.info", file=task.file_id))["file"]
        if (
            file.get("id") != task.file_id
            or file.get("is_external")
            # Slack also stores editable text uploads as downloadable snippets.
            or file.get("mode") not in {"hosted", "snippet"}
        ):
            raise FileIntegrationError("unsupported_slack_file")
        if (
            not isinstance(file.get("size"), int)
            or not 0 <= file["size"] <= self.settings.max_file_bytes
        ):
            raise FileIntegrationError("file_too_large")
        # Source URL is fetched afresh, not trusted from the incoming event.
        data = await self.slack.download(
            file.get("url_private_download") or file.get("url_private", ""),
            self.settings.max_file_bytes,
        )
        if len(data) != file["size"]:
            raise FileIntegrationError("file_size_mismatch")
        name = path_component(file.get("name") or file.get("title") or task.file_id)
        path = await self.store.file_path(task, f"{folder}/{task.file_id}--{name}")
        await self.cloud.mkdirs(folder)
        await self.cloud.put_once(path, data)
        # One immutable context per Slack event avoids order-dependent metadata overwrites.
        context_folder = f"{folder}/.sumin-context/{task.file_id}"
        await self.cloud.mkdirs(context_folder)
        context = {
            "schema_version": "sumin-context-v1",
            "team_id": task.team_id,
            "channel_id": task.channel_id,
            "file_id": task.file_id,
            "event_id": task.event_id,
            "user_id": task.user_id,
            "message_ts": task.message_ts,
            "thread_ts": task.thread_ts,
            "text": task.text,
            "archive_path": path,
        }
        await self.cloud.put_once(
            f"{context_folder}/{task.event_id}.json",
            json.dumps(context, ensure_ascii=False, sort_keys=True).encode(),
        )
        await self.store.save_file_metadata(task, file)
        await self.store.save_context(task)

    async def search(self, task: SuminTask, folder: str) -> None:
        found = await self.search_agent.find(task, folder)
        text = escape(found.message, quote=False)
        if found.files:
            lines = [text or "Here are the matching files:"]
            for file in found.files[:10]:
                data = await self.cloud.download(
                    f"{folder}/{file.name}", self.settings.max_file_bytes
                )
                filename = path_component(re.sub(r"^F[A-Z0-9]+--", "", file.name))
                await self.sender.upload_file(
                    channel_id=task.channel_id,
                    thread_ts=task.thread_ts or task.message_ts,
                    filename=filename,
                    data=data,
                )
                label = escape(filename, quote=False).replace("|", "&#124;")
                lines.append(f"• <{file.url}|{label}>")
            text = "\n".join(lines)
        result = await self.sender.send_message(
            SlackMessage(
                channel_id=task.channel_id,
                thread_ts=task.thread_ts or task.message_ts,
                text=text,
            )
        )
        if not result.success:
            raise FileIntegrationError("slack_reply_failed")
