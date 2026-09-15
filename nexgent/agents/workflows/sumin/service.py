"""Sumin policy and deterministic file discovery; file contents are never model input."""

import json
import re
from html import escape

from ax_contracts.sumin import SuminTask
from ax_integrations.file_http import FileIntegrationError
from ax_integrations.nextcloud import Nextcloud, path_component
from ax_integrations.slack import SlackMessage
from ax_integrations.slack_files import MemberSlackService, SlackFiles

from .settings import Settings
from .store import Store

STOP_WORDS = frozenset(
    [
        "sumin",
        "find",
        "search",
        "show",
        "get",
        "give",
        "me",
        "us",
        "the",
        "a",
        "an",
        "for",
        "of",
        "in",
        "on",
        "about",
        "please",
        "file",
        "files",
        "document",
        "documents",
        "link",
        "links",
        "url",
        "urls",
        "where",
        "is",
        "are",
        "can",
        "you",
        "could",
        "would",
        "my",
        "our",
        "수민",
        "수민아",
        "파일",
        "파일을",
        "문서",
        "문서를",
        "찾아줘",
        "찾아주세요",
        "보여줘",
        "보여주세요",
        "링크",
        "알려줘",
    ]
)


def search_terms(text: str) -> list[str]:
    text = re.sub(r"<[^>]*>", " ", text).casefold()
    quoted = re.findall(r'"([^"\n]{1,160})"', text)
    if quoted:
        return list(dict.fromkeys(quoted))[:8]
    return list(
        dict.fromkeys(
            word
            for word in re.findall(r"[\w.-]+", text)
            if word not in STOP_WORDS and len(word) > 1
        )
    )[:8]


class Sumin:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        slack: SlackFiles,
        cloud: Nextcloud,
        sender: MemberSlackService,
    ):
        self.settings, self.store, self.slack = settings, store, slack
        self.cloud, self.sender = cloud, sender

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
        await self.store.save_context(task)

    async def search(self, task: SuminTask, folder: str) -> None:
        terms = search_terms(task.text)
        if not terms:
            text = (
                'Tell me a filename or keyword, for example: @Sumin find "budget.xlsx".'
            )
        else:
            # Live WebDAV results are authoritative: never return stale database-only links.
            files = await self.cloud.list_files(folder)
            context_ids = await self.store.match_context(task, terms)
            ranked = []
            for file in files:
                name = file.name.casefold()
                score = sum(term in name for term in terms)
                if file.name.split("--", 1)[0] in context_ids:
                    score += 1
                if score:
                    ranked.append((score, file))
            ranked.sort(key=lambda item: (-item[0], item[1].name))
            if ranked:
                lines = ["Matching files in this channel’s Nextcloud folder:"]
                for _, file in ranked[:10]:
                    label = escape(file.name, quote=False).replace("|", "&#124;")
                    lines.append(f"• <{file.url}|{label}>")
                if len(ranked) > 10:
                    lines.append(
                        "Showing the first 10 matches. Add a more specific keyword to narrow them."
                    )
                text = "\n".join(lines)
            else:
                text = "I couldn’t find a matching file in this channel’s Nextcloud folder. Try a filename or a keyword from the upload message."
        result = await self.sender.send_message(
            SlackMessage(
                channel_id=task.channel_id,
                thread_ts=task.thread_ts or task.message_ts,
                text=text,
            )
        )
        if not result.success:
            raise FileIntegrationError("slack_reply_failed")
