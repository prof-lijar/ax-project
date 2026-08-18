from dataclasses import dataclass

import httpx

from app.chat.config import ChatSettings
from app.chat.errors import ChatRequestError
from app.chat.models import ChatAttachmentRef


@dataclass(slots=True)
class AgentServerStream:
    client: httpx.AsyncClient
    response: httpx.Response

    async def close(self) -> None:
        await self.response.aclose()
        await self.client.aclose()


async def open_agent_stream(
    prompt: str,
    attachments: tuple[ChatAttachmentRef, ...],
    settings: ChatSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AgentServerStream:
    timeout = httpx.Timeout(
        connect=settings.connect_timeout_seconds,
        read=None,
        write=settings.write_timeout_seconds,
        pool=settings.connect_timeout_seconds,
    )
    client = httpx.AsyncClient(timeout=timeout, transport=transport)
    graph_input: dict[str, object] = {"message": prompt}
    if attachments:
        graph_input["attachments"] = [
            attachment.model_dump(mode="json") for attachment in attachments
        ]
    request = client.build_request(
        "POST",
        f"{settings.agent_server_url}/runs/stream",
        headers={"Accept": "text/event-stream"},
        json={
            "assistant_id": settings.assistant_id,
            "input": graph_input,
            "stream_mode": ["custom"] if attachments else ["custom", "values"],
            "on_disconnect": "cancel",
        },
    )
    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise ChatRequestError(
            "agent_server_unavailable",
            "The chat service is temporarily unavailable.",
            status_code=502,
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        await response.aclose()
        await client.aclose()
        raise ChatRequestError(
            "agent_server_error",
            "The chat service rejected the request.",
            status_code=502,
        )
    content_type = response.headers.get("content-type", "").lower()
    if not content_type.startswith("text/event-stream"):
        await response.aclose()
        await client.aclose()
        raise ChatRequestError(
            "invalid_agent_stream",
            "The chat service returned an invalid stream.",
            status_code=502,
        )
    return AgentServerStream(client=client, response=response)
