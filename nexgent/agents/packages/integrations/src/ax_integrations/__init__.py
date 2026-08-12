"""Integration ports; implementations stay outside graph topology."""

from .agent_server import AgentServerClient, AgentServerUnavailable
from .chat import (
    ChatMessage,
    ChatModel,
    ModelConfigurationError,
    ModelRequestError,
    OpenAICompatibleChatModel,
    OpenAICompatibleSettings,
    get_default_chat_model,
)
from .web import (
    AsyncHostResolver,
    HostResolver,
    SafeWebFetchClient,
    SearxngSearchClient,
    SearxngSettings,
    WebFetchSettings,
    WebRetrievalError,
    canonicalize_url,
    get_default_web_fetch_client,
    get_default_web_search_client,
    source_id_for_url,
)

__all__ = [
    "AgentServerClient",
    "AgentServerUnavailable",
    "AsyncHostResolver",
    "ChatMessage",
    "ChatModel",
    "HostResolver",
    "ModelConfigurationError",
    "ModelRequestError",
    "OpenAICompatibleChatModel",
    "OpenAICompatibleSettings",
    "SafeWebFetchClient",
    "SearxngSearchClient",
    "SearxngSettings",
    "WebFetchSettings",
    "WebRetrievalError",
    "canonicalize_url",
    "get_default_chat_model",
    "get_default_web_fetch_client",
    "get_default_web_search_client",
    "source_id_for_url",
]
