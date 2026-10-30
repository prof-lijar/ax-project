"""Copy the reconciled month through the existing live-dev SSH route."""

import os

import asyncpg
from dotenv import dotenv_values

from workflows.daily_risk_counts.live_copy import DevSettings, copy_rows, dev_tunnel


async def sync_month(source, month, *, env_file, event):
    settings = DevSettings.from_env({**dotenv_values(env_file), **os.environ})
    # This scheduler's explicitly selected destination is always ansimk.
    if settings.db_schema != "ansimk":
        raise ValueError("Daily live-dev sync requires LIVE_DEV_DB_SCHEMA=ansimk")
    async with dev_tunnel(settings) as local_port:
        target = await asyncpg.connect(
            host="127.0.0.1",
            port=local_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            ssl=settings.db_ssl,
            timeout=15,
            command_timeout=1830,
            server_settings={"application_name": "daily_risk_counts_live_dev"},
        )
        try:
            identity = "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
            if await source.fetchrow(identity) == await target.fetchrow(identity):
                raise ValueError("Source and live-dev target must differ")
            result = await copy_rows(
                source,
                target,
                schema="ansimk",
                write=True,
                month=month,
            )
        finally:
            try:
                await target.close(timeout=10)
            except Exception as exc:  # noqa: BLE001 -- sanitize cleanup failures
                event(
                    "daily_risk_cleanup_failed",
                    target="dev",
                    error_type=type(exc).__name__,
                )
    return result
