from dataclasses import dataclass
from uuid import UUID

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
    assistant_id: str | None = None,
    session_id: UUID | None = None,
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
    payload: dict[str, object] = {
        "assistant_id": assistant_id or settings.assistant_id,
        "input": graph_input,
        "stream_mode": ["custom"] if attachments else ["custom", "values"],
        "on_disconnect": "cancel",
    }
    path = "/runs/stream"
    if session_id is not None:
        path = f"/threads/{session_id}/runs/stream"
        # Reset transient fields, preserving only server-owned history.
        graph_input.update(
            {
                "attachments": graph_input.get("attachments", []),
                "response": "",
                "error": None,
            }
        )
        payload.update(
            {
                "stream_mode": ["custom"],
                "if_not_exists": "create",
                "multitask_strategy": "reject",
            }
        )
    request = client.build_request(
        "POST",
        f"{settings.agent_server_url}{path}",
        headers={"Accept": "text/event-stream"},
        json=payload,
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
    except BaseException:
        await client.aclose()
        raise

    if response.status_code == 409 and session_id is not None:
        await response.aclose()
        await client.aclose()
        raise ChatRequestError(
            "chat_session_busy",
            "This conversation is still finishing a reply. Please try again shortly.",
            status_code=409,
        )
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
