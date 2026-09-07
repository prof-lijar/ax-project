"""Declarative MCP registry and Streamable HTTP client integration."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx2
from ax_contracts import McpToolCallResult, McpToolDefinition
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_MCP_REGISTRY_PATH = Path("config/mcp_servers.json")
MCP_REGISTRY_ENV = "MCP_SERVERS_CONFIG"
_SERVER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_HEADER_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31} $")


class McpConfigurationError(RuntimeError):
    """Raised when MCP registry or secret configuration is invalid."""


class McpIntegrationError(RuntimeError):
    """Safe MCP transport or protocol failure with an explicit retry decision."""

    def __init__(
        self,
        error_code: str,
        safe_message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.error_code = error_code
        self.safe_message = safe_message
        self.retryable = retryable
        self.status_code = status_code


class McpHeaderSource(BaseModel):
    """Environment-backed HTTP header without storing its secret value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    prefix: str = Field(default="", max_length=128)

    @field_validator("prefix")
    @classmethod
    def reject_header_injection(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("header prefix must not contain line breaks")
        if value and not _HEADER_PREFIX.fullmatch(value):
            raise ValueError(
                "header prefix must be a short authentication scheme ending in a space"
            )
        return value


class McpServerSettings(BaseModel):
    """Validated settings for one registered MCP server."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    transport: Literal["streamable_http"]
    url: str = Field(min_length=1, max_length=8_000)
    headers: dict[str, McpHeaderSource] = Field(default_factory=dict)
    connect_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    read_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)
    max_result_characters: int = Field(default=200_000, ge=1_000, le=2_000_000)
    connect_mode: Literal["auto", "legacy"] = "auto"
    terminate_on_close: bool = True
    enabled: bool = True
    tool_risks: dict[str, Literal["read", "write", "destructive"]] = Field(
        default_factory=dict
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("MCP URL must not contain credentials")
        return value

    @field_validator("headers")
    @classmethod
    def validate_header_names(
        cls, value: dict[str, McpHeaderSource]
    ) -> dict[str, McpHeaderSource]:
        for name in value:
            if not _HEADER_NAME.fullmatch(name):
                raise ValueError("MCP header names must be valid HTTP field names")
        return value

    def resolve_headers(
        self, environ: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        values = os.environ if environ is None else environ
        resolved: dict[str, str] = {}
        for name, source in self.headers.items():
            secret = values.get(source.env)
            if not secret:
                raise McpConfigurationError(
                    f"MCP header {name!r} requires environment variable {source.env}"
                )
            if "\r" in secret or "\n" in secret:
                raise McpConfigurationError(
                    f"MCP header environment variable {source.env} is invalid"
                )
            resolved[name] = source.prefix + secret
        return resolved


class McpRegistrySettings(BaseModel):
    """Strict registry of named MCP servers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    servers: dict[str, McpServerSettings]

    @field_validator("servers")
    @classmethod
    def validate_server_names(
        cls, value: dict[str, McpServerSettings]
    ) -> dict[str, McpServerSettings]:
        if not value:
            raise ValueError("MCP registry must define at least one server")
        invalid = [name for name in value if not _SERVER_NAME.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid MCP server name: {invalid[0]!r}")
        return value

    def get(self, server_name: str) -> McpServerSettings:
        try:
            settings = self.servers[server_name]
        except KeyError as exc:
            raise McpConfigurationError(
                f"MCP server is not registered: {server_name}"
            ) from exc
        if not settings.enabled:
            raise McpConfigurationError(f"MCP server is disabled: {server_name}")
        return settings

    def create_client(
        self,
        server_name: str,
        *,
        environ: Mapping[str, str] | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> McpServerClient:
        return McpServerClient(
            server_name,
            self.get(server_name),
            environ=environ,
            http_client=http_client,
        )


def load_mcp_registry(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> McpRegistrySettings:
    """Load a strict JSON registry; secret values remain environment-backed."""

    values = os.environ if environ is None else environ
    selected = Path(path or values.get(MCP_REGISTRY_ENV, DEFAULT_MCP_REGISTRY_PATH))
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
        return McpRegistrySettings.model_validate(payload)
    except (OSError, ValueError) as exc:
        raise McpConfigurationError(
            f"unable to load MCP registry from {selected}"
        ) from exc


class McpServerClient:
    """Pooled async client for one configured Streamable HTTP MCP server."""

    def __init__(
        self,
        server_name: str,
        settings: McpServerSettings,
        *,
        environ: Mapping[str, str] | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        if not _SERVER_NAME.fullmatch(server_name):
            raise McpConfigurationError(f"invalid MCP server name: {server_name!r}")
        self.server_name = server_name
        self.settings = settings
        self._owns_client = http_client is None
        self._http_client = http_client or httpx2.AsyncClient(
            headers=settings.resolve_headers(environ),
            timeout=httpx2.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=settings.connect_timeout_seconds,
                pool=settings.connect_timeout_seconds,
            ),
            limits=httpx2.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=False,
            trust_env=False,
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Client]:
        transport = streamable_http_client(
            self.settings.url,
            http_client=self._http_client,
            terminate_on_close=self.settings.terminate_on_close,
        )
        try:
            async with Client(
                transport,
                read_timeout_seconds=self.settings.read_timeout_seconds,
                mode=self.settings.connect_mode,
                cache=None,
            ) as client:
                yield client
        except MCPError as exc:
            raise McpIntegrationError(
                "mcp_protocol_error",
                f"MCP server {self.server_name} returned a protocol error",
                retryable=False,
            ) from exc
        except httpx2.HTTPStatusError as exc:
            status_code = exc.response.status_code
            retryable = status_code == 429 or 500 <= status_code < 600
            code = (
                "mcp_authentication_failed"
                if status_code in {401, 403}
                else "mcp_http_error"
            )
            raise McpIntegrationError(
                code,
                f"MCP server {self.server_name} failed with HTTP {status_code}",
                retryable=retryable,
                status_code=status_code,
            ) from exc
        except (httpx2.TransportError, TimeoutError) as exc:
            raise McpIntegrationError(
                "mcp_unavailable",
                f"MCP server {self.server_name} is unavailable",
                retryable=True,
            ) from exc
        except BaseExceptionGroup as exc:
            if any(
                isinstance(leaf, asyncio.CancelledError)
                for leaf in _exception_leaves(exc)
            ):
                raise
            raise _normalize_exception_group(self.server_name, exc) from exc

    async def list_tools(self) -> list[McpToolDefinition]:
        async with self._client() as client:
            return await self._list_tools(client)

    async def _list_tools(self, client: Client) -> list[McpToolDefinition]:
        tools: list[McpToolDefinition] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(20):
            listing = await client.list_tools(cursor=cursor, cache_mode="bypass")
            for tool in listing.tools:
                tools.append(
                    McpToolDefinition(
                        server_name=self.server_name,
                        name=tool.name,
                        title=tool.title,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        output_schema=tool.output_schema,
                        risk=self.settings.tool_risks.get(tool.name),
                    )
                )
            cursor = listing.next_cursor
            if cursor is None:
                return tools
            if cursor in seen_cursors:
                raise McpIntegrationError(
                    "mcp_invalid_pagination",
                    f"MCP server {self.server_name} repeated a pagination cursor",
                    retryable=False,
                )
            seen_cursors.add(cursor)
        raise McpIntegrationError(
            "mcp_tool_limit_exceeded",
            f"MCP server {self.server_name} exceeded the tool pagination limit",
            retryable=False,
        )

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> McpToolCallResult:
        async with self._client() as client:
            result = await client.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=self.settings.read_timeout_seconds,
            )
        content = [
            block.model_dump(mode="json", by_alias=False) for block in result.content
        ]
        encoded_result = json.dumps(
            {
                "content": content,
                "structured_content": result.structured_content,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(encoded_result) > self.settings.max_result_characters:
            raise McpIntegrationError(
                "mcp_result_too_large",
                f"MCP server {self.server_name} returned an oversized tool result",
                retryable=False,
            )
        return McpToolCallResult(
            server_name=self.server_name,
            tool_name=tool_name,
            content=content,
            structured_content=result.structured_content,
            is_error=result.is_error,
        )

    async def inspect(self) -> dict[str, Any]:
        """Return non-secret server and tool metadata for development checks."""

        async with self._client() as client:
            protocol_version = client.protocol_version
            server_info = client.server_info
            tools = await self._list_tools(client)
        return {
            "server_name": self.server_name,
            "url": self.settings.url,
            "protocol_version": protocol_version,
            "server_info": (
                server_info.model_dump(mode="json") if server_info else None
            ),
            "tools": [tool.model_dump(mode="json") for tool in tools],
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()


def _exception_leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in _exception_leaves(child)]
    return [exc]


def _normalize_exception_group(
    server_name: str, exc: BaseExceptionGroup
) -> McpIntegrationError:
    leaves = _exception_leaves(exc)
    for leaf in leaves:
        if isinstance(leaf, httpx2.HTTPStatusError):
            status_code = leaf.response.status_code
            return McpIntegrationError(
                "mcp_authentication_failed"
                if status_code in {401, 403}
                else "mcp_http_error",
                f"MCP server {server_name} failed with HTTP {status_code}",
                retryable=status_code == 429 or 500 <= status_code < 600,
                status_code=status_code,
            )
        if isinstance(leaf, httpx2.TransportError | TimeoutError):
            return McpIntegrationError(
                "mcp_unavailable",
                f"MCP server {server_name} is unavailable",
                retryable=True,
            )
        if isinstance(leaf, MCPError):
            return McpIntegrationError(
                "mcp_protocol_error",
                f"MCP server {server_name} returned a protocol error",
                retryable=False,
            )
    return McpIntegrationError(
        "mcp_connection_failed",
        f"MCP server {server_name} connection failed",
        retryable=False,
    )
