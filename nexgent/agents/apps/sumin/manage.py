"""Local operator CLI: migrate, status, and explicit failed-event retry."""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg


async def execute(args):
    connection = await asyncpg.connect(
        os.environ["AGENT_DATABASE_DSN"], command_timeout=30
    )
    try:
        if args.command == "migrate":
            async with connection.transaction():
                await connection.execute(
                    Path("workflows/sumin/schema.sql").read_text(encoding="utf-8")
                )
            print("Sumin schema ready")
        elif args.command == "status":
            rows = await connection.fetch(
                "SELECT key,status,attempts,error_code,updated_at FROM agent.sumin_events "
                "ORDER BY created_at DESC LIMIT 50"
            )
            for row in rows:
                print(dict(row))
        else:
            result = await connection.execute(
                "UPDATE agent.sumin_events SET status='pending', attempts=0, error_code=NULL, "
                "available_at=NOW(), updated_at=NOW() WHERE key=$1 AND status='failed'",
                args.key,
            )
            print(result)
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("status")
    sub.add_parser("retry").add_argument("key")
    try:
        asyncio.run(execute(parser.parse_args()))
    except (asyncpg.PostgresError, OSError, TimeoutError, ValueError, KeyError):
        parser.exit(
            1,
            "Sumin management command failed; check database settings and permissions.\n",
        )


if __name__ == "__main__":
    main()
