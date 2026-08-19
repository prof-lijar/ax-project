"""Operator CLI for a safe outbound Slack smoke message."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from .slack import (
    SlackConfigurationError,
    SlackMessage,
    SlackService,
    SlackSettings,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ax-slack-send")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--destination",
        help="configured logical destination, for example reports",
    )
    destination.add_argument(
        "--channel-id",
        help="explicit channel ID; it must already be approved in configuration",
    )
    parser.add_argument(
        "--text",
        default="Nexgent outbound Slack integration test completed successfully.",
        help="test message text",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    service = SlackService(SlackSettings.from_env())
    if args.destination:
        result = await service.send_to(destination=args.destination, text=args.text)
    else:
        result = await service.send_message(
            SlackMessage(channel_id=args.channel_id, text=args.text)
        )
    print(
        json.dumps(
            {
                "success": result.success,
                "channel_id": result.channel_id,
                "message_ts": result.message_ts,
                "error": result.error,
            },
            sort_keys=True,
        )
    )
    return 0 if result.success else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(_run(build_parser().parse_args(argv)))
    except SlackConfigurationError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
