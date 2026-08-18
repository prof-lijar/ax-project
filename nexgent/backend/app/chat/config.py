import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChatSettings:
    agent_server_url: str
    assistant_id: str
    artifact_root: Path
    stale_after_seconds: int
    connect_timeout_seconds: float
    write_timeout_seconds: float


def get_chat_settings() -> ChatSettings:
    artifact_root = Path(os.getenv("AX_CHAT_ARTIFACT_ROOT", "/tmp/ax-chat-artifacts"))
    if not artifact_root.is_absolute():
        raise RuntimeError("AX_CHAT_ARTIFACT_ROOT must be an absolute path")

    return ChatSettings(
        agent_server_url=os.getenv(
            "AX_AGENT_SERVER_URL", "http://agent-server:2024"
        ).rstrip("/"),
        assistant_id=os.getenv("AX_CHAT_ASSISTANT_ID", "chat"),
        artifact_root=artifact_root,
        stale_after_seconds=int(os.getenv("AX_CHAT_STALE_AFTER_SECONDS", "900")),
        connect_timeout_seconds=float(
            os.getenv("AX_AGENT_SERVER_CONNECT_TIMEOUT_SECONDS", "5")
        ),
        write_timeout_seconds=float(
            os.getenv("AX_AGENT_SERVER_WRITE_TIMEOUT_SECONDS", "30")
        ),
    )
