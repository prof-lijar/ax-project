"""Production-only sync CLI. Logs contain delivery metadata, never report content."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal

import asyncpg

from workflows.weekly_report.sync.delivery import (
    check_target,
    classify_error,
    decode_payload,
    deliver,
    process_one,
)
from workflows.weekly_report.sync.outbox import Outbox
from workflows.weekly_report.sync.settings import SyncSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weekly-report-sync")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="poll and deliver pending reports")
    commands.add_parser("run-once", help="process up to 100 ready reports")
    commands.add_parser("status", help="show counts and up to 100 outstanding IDs")
    commands.add_parser("check", help="read-only database and schema readiness check")
    commands.add_parser("dry-run", help="read-only validation of up to 100 deliveries")
    retry = commands.add_parser("retry", help="requeue one blocked delivery")
    retry.add_argument("delivery_id", type=int)
    return parser


def emit(data: dict) -> None:
    print(json.dumps(data, default=str), flush=True)


async def connect(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn,
        min_size=0,
        max_size=1,
        timeout=10,
        command_timeout=20,
        server_settings={
            "application_name": "ax_weekly_report_sync",
            "statement_timeout": "20000",
            "lock_timeout": "10000",
        },
    )


async def run_command(args: argparse.Namespace, settings: SyncSettings) -> int:
    local = await connect(settings.local_dsn)
    target = None
    try:
        outbox = Outbox(local, settings.max_attempts)
        if args.command == "status":
            emit(await outbox.status())
            return 0
        if args.command == "retry":
            changed = await outbox.retry(args.delivery_id)
            emit({"delivery_id": args.delivery_id, "requeued": changed})
            return 0 if changed else 2
        target = await connect(settings.target_dsn)
        if args.command in {"check", "dry-run"}:
            try:
                await outbox.check()
                await check_target(target)
            except Exception as error:  # noqa: BLE001 -- sanitize external diagnostics
                emit({"stage": "readiness", "error_code": classify_error(error)[0]})
                return 1
            emit({"stage": "readiness", "outcome": "ready"})
            if args.command == "check":
                return 0
        if args.command == "dry-run":
            failures = 0
            for row in await outbox.preview(settings.limit):
                try:
                    outcome = await deliver(target, decode_payload(row), dry_run=True)
                    emit({"delivery_id": row["id"], "outcome": outcome})
                except Exception as error:  # noqa: BLE001 -- sanitize external diagnostics
                    failures += 1
                    emit(
                        {
                            "delivery_id": row["id"],
                            "error_code": classify_error(error)[0],
                        }
                    )
            return 2 if failures else 0
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        while not stop.is_set():
            processed = 0
            failures = 0
            try:
                for _ in range(settings.limit):
                    if stop.is_set():
                        break
                    result = await process_one(outbox, target)
                    if result is None:
                        break
                    processed += 1
                    failures += "error_code" in result
                    emit(result)
            except Exception as error:  # noqa: BLE001 -- sanitize external diagnostics
                failures += 1
                emit({"error_code": classify_error(error)[0], "stage": "local_queue"})
            if args.command == "run-once":
                return 2 if failures else 0
            if processed == settings.limit and not failures:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.poll_seconds)
            except TimeoutError:
                pass
        return 0
    finally:
        for pool in (target, local):
            if pool is not None:
                try:
                    await asyncio.wait_for(pool.close(), timeout=5)
                except TimeoutError:
                    pool.terminate()


def main() -> None:
    args = build_parser().parse_args()
    try:
        settings = SyncSettings.from_env()
        code = asyncio.run(run_command(args, settings))
    except Exception:  # noqa: BLE001 -- never print secrets from driver errors
        # asyncpg and DSN parsing exceptions can contain credentials or row data.
        emit({"error_code": "sync_configuration_or_connection_failed"})
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
