import json

import pytest
from ax_integrations import (
    McpConfigurationError,
    McpHeaderSource,
    McpRegistrySettings,
    McpServerSettings,
    load_mcp_registry,
)
from pydantic import ValidationError


def test_mcp_header_secret_is_environment_backed_and_prefix_is_preserved() -> None:
    settings = McpServerSettings(
        transport="streamable_http",
        url="http://mcp.internal:8001/mcp",
        headers={
            "Authorization": McpHeaderSource(env="MCP_TEST_TOKEN", prefix="Bearer ")
        },
    )

    headers = settings.resolve_headers({"MCP_TEST_TOKEN": "secret-token"})

    assert headers == {"Authorization": "Bearer secret-token"}
    assert "secret-token" not in repr(settings)


def test_mcp_header_reports_missing_secret_without_value() -> None:
    settings = McpServerSettings(
        transport="streamable_http",
        url="http://mcp.internal:8001/mcp",
        headers={"Authorization": {"env": "MCP_TEST_TOKEN", "prefix": "Bearer "}},
    )

    with pytest.raises(McpConfigurationError, match="MCP_TEST_TOKEN"):
        settings.resolve_headers({})


def test_mcp_header_prefix_cannot_be_used_as_an_inline_secret() -> None:
    with pytest.raises(ValidationError, match="authentication scheme"):
        McpHeaderSource(
            env="MCP_TEST_TOKEN",
            prefix="8d0699a81bc4fdb4cf5c04c57086b43c",
        )


def test_mcp_registry_loads_multiple_servers_from_strict_json(tmp_path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "servers": {
                    "first_server": {
                        "transport": "streamable_http",
                        "url": "https://first.example/mcp",
                        "headers": {},
                        "tool_risks": {"lookup": "read"},
                    },
                    "second_server": {
                        "transport": "streamable_http",
                        "url": "http://second.internal/mcp",
                        "headers": {},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    registry = load_mcp_registry(path)

    assert isinstance(registry, McpRegistrySettings)
    assert list(registry.servers) == ["first_server", "second_server"]
    assert registry.get("first_server").tool_risks == {"lookup": "read"}


def test_mcp_registry_rejects_unknown_configuration_fields(tmp_path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "servers": {
                    "bad_server": {
                        "transport": "streamable_http",
                        "url": "https://example.com/mcp",
                        "inline_secret": "must-not-be-supported",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(McpConfigurationError):
        load_mcp_registry(path)


def test_mcp_settings_reject_credentials_embedded_in_url() -> None:
    with pytest.raises(ValidationError, match="must not contain credentials"):
        McpServerSettings(
            transport="streamable_http",
            url="https://token@example.com/mcp",
        )


def test_db_mcp_server_registry_has_only_environment_secret_references() -> None:
    registry = load_mcp_registry()
    settings = registry.get("db_mcp_server")

    assert settings.url == "http://192.168.0.11:8001/mcp"
    assert settings.connect_mode == "legacy"
    assert settings.headers["Authorization"].env == "DB_MCP_SERVER_BEARER_TOKEN"
    assert set(settings.tool_risks.values()) == {"read"}
    assert len(settings.tool_risks) == 10
