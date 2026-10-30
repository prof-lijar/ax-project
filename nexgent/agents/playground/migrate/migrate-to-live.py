"""Copy local monthly risk rows to live dev; --migrate-to-live commits the copy."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from migrate_weekly_risk_counts import ENV_FILE, log, progress, source_database_dsn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from workflows.daily_risk_counts.live_copy import (  # noqa: F401
    COPY_FIELDS,
    SOURCE_TABLE,
    DevSettings,
    MigrationError,
    copy_rows,
    database_endpoint,
    dev_tunnel,
    ssh_command,
)


async def run(args):
    load_dotenv(ENV_FILE, override=False)
    settings = DevSettings.from_env()
    dsn = source_database_dsn()
    async with progress("Connecting to local archive database"):
        source = await asyncpg.connect(dsn, timeout=15, command_timeout=1830)
    try:
        async with (
            progress("Opening dev SSH tunnel"),
            dev_tunnel(settings) as local_port,
        ):
            async with progress("Connecting to live dev database"):
                target = await asyncpg.connect(
                    host="127.0.0.1",
                    port=local_port,
                    database=settings.db_name,
                    user=settings.db_user,
                    password=settings.db_password,
                    ssl=settings.db_ssl,
                    timeout=15,
                    command_timeout=1830,
                    server_settings={
                        "application_name": "migrate_risk_counts_to_live_dev"
                    },
                )
            try:
                identity = "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
                if await source.fetchrow(identity) == await target.fetchrow(identity):
                    raise MigrationError(
                        "Source and destination appear identical; copy aborted."
                    )
                async with progress("Copying local monthly risk data to dev"):
                    result = await copy_rows(
                        source,
                        target,
                        schema=settings.db_schema,
                        write=args.migrate_to_live,
                    )
                print(json.dumps(result), flush=True)
            finally:
                await target.close(timeout=10)
    finally:
        await source.close(timeout=10)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate-to-live",
        action="store_true",
        help="Commit all local risk rows to dev; otherwise preview.",
    )
    parser.add_argument("-target", "--target", choices=["dev"], required=True)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    log(f"Target: dev; mode: {'APPLY' if args.migrate_to_live else 'PREVIEW'}")
    try:
        asyncio.run(run(args))
    except MigrationError as exc:
        log(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        log("Interrupted. Rerun to reconcile any uncertain commit.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 -- keep credentials out of CLI errors
        log(
            f"Dev copy failed ({type(exc).__name__}, SQLSTATE={getattr(exc, 'sqlstate', None) or 'n/a'}). "
            "No success confirmed. Resolve the failing stage and rerun; an uncertain commit is safe to reconcile.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
