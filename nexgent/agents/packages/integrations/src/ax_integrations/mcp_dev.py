"""Small, non-secret MCP registry inspection CLI for development."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from .mcp import (
    DEFAULT_MCP_REGISTRY_PATH,
    McpConfigurationError,
    McpIntegrationError,
    load_mcp_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ax-mcp")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help=f"registry JSON path (default: {DEFAULT_MCP_REGISTRY_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list configured servers without connecting")
    inspect_parser = subparsers.add_parser(
        "inspect", help="connect and print non-secret server/tool metadata"
    )
    inspect_parser.add_argument("server_name")
    return parser


async def _run(args: argparse.Namespace) -> int:
    registry = load_mcp_registry(args.registry)
    if args.command == "list":
        payload = {
            "servers": [
                {
                    "name": name,
                    "transport": settings.transport,
                    "url": settings.url,
                    "enabled": settings.enabled,
                }
                for name, settings in sorted(registry.servers.items())
            ]
        }
    else:
        client = registry.create_client(args.server_name)
        try:
            payload = await client.inspect()
        finally:
            await client.aclose()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(_run(build_parser().parse_args(argv)))
    except (McpConfigurationError, McpIntegrationError) as exc:
        payload = {
            "status": "failed",
            "error": {
                "code": getattr(exc, "error_code", "mcp_configuration_error"),
                "message": str(exc),
                "retryable": bool(getattr(exc, "retryable", False)),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
