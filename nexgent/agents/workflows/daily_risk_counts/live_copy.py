"""Copy local monthly risk rows to a selected live database; --migrate-to-live commits the copy."""

import asyncio
import contextlib
import os
import re
import shutil
import signal
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from urllib.parse import urlsplit

SOURCE_TABLE = "archive.resources_ward_monthly_risk_count"
TABLE_NAME = "resources_ward_monthly_risk_count"
COPY_FIELDS = (
    "ward_id",
    "month",
    "total_risk_count",
    "risk_days",
    "total_danger_stable_count",
    "danger_stable_days",
    "created_at",
    "updated_at",
)
VALUE_FIELDS = COPY_FIELDS[2:]
STAGE = "pg_temp.risk_live_stage"


def log(message):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


class MigrationError(ValueError):
    """An operator-facing error containing no connection credentials."""


def required(name, *, secret=False, environment=None):
    environment = os.environ if environment is None else environment
    value = environment.get(name, "") or ""
    if not value.strip():
        raise MigrationError(f"Missing {name}; configure agents/.env.")
    return value if secret else value.strip()


def port_setting(name, default, *, environment=None):
    environment = os.environ if environment is None else environment
    try:
        value = int(environment.get(name, default))
        if not 1 <= value <= 65535:
            raise ValueError
    except ValueError as exc:
        raise MigrationError(f"{name} must be between 1 and 65535.") from exc
    return value


def database_endpoint(value):
    """Accept a bare endpoint or a console-copied http(s) endpoint URL."""
    try:
        endpoint = urlsplit(value if "://" in value else "//" + value)
        if (
            endpoint.scheme not in {"", "http", "https", "postgres", "postgresql"}
            or endpoint.username is not None
            or endpoint.path not in {"", "/"}
            or endpoint.query
            or endpoint.fragment
            or not endpoint.hostname
        ):
            raise ValueError
        return endpoint.hostname, endpoint.port or 5432
    except ValueError as exc:
        raise MigrationError(
            "Invalid LIVE_DEV_DB_HOST endpoint; use a hostname or endpoint URL without credentials or a path."
        ) from exc


@dataclass(frozen=True)
class DevSettings:
    db_host: str
    db_user: str
    db_password: str = field(repr=False)
    ssh_host: str
    ssh_user: str
    ssh_password: str = field(repr=False)
    db_port: int = 5432
    db_name: str = "ansimk"
    db_schema: str = "ansimk"
    db_ssl: str = "prefer"
    ssh_port: int = 22
    target: str = "dev"

    @classmethod
    def from_env(cls, environment=None, *, target="dev"):
        if target not in {"dev", "prod"}:
            raise MigrationError("Target must be dev or prod.")
        environment = os.environ if environment is None else environment
        if target == "prod":
            # Reuse validation with an isolated mapping; never fall back to dev.
            mapped = {
                "LIVE_DEV_" + key.removeprefix("LIVE_PROD_"): value
                for key, value in environment.items()
                if key.startswith("LIVE_PROD_")
            }
            mapped.setdefault("LIVE_DEV_DB_SSL", "require")
            try:
                settings = cls.from_env(mapped)
            except MigrationError as exc:
                raise MigrationError(str(exc).replace("LIVE_DEV_", "LIVE_PROD_")) from None
            return replace(settings, target="prod")

        def setting(name, *, secret=False):
            return required(name, secret=secret, environment=environment)

        def port(name, default):
            return port_setting(name, default, environment=environment)

        db_host, db_port = database_endpoint(setting("LIVE_DEV_DB_HOST"))
        settings = cls(
            db_host=db_host,
            db_user=setting("LIVE_DEV_DB_USER"),
            db_password=setting("LIVE_DEV_DB_PASSWORD", secret=True),
            ssh_host=setting("LIVE_DEV_SSH_HOST"),
            ssh_user=setting("LIVE_DEV_SSH_ID"),
            ssh_password=setting("LIVE_DEV_SSH_PASSWORD", secret=True),
            db_port=port("LIVE_DEV_DB_PORT", db_port),
            db_name=environment.get("LIVE_DEV_DB_NAME", "ansimk").strip(),
            db_schema=environment.get("LIVE_DEV_DB_SCHEMA", "ansimk").strip(),
            db_ssl=environment.get("LIVE_DEV_DB_SSL", "prefer").strip(),
            ssh_port=port("LIVE_DEV_SSH_PORT", 22),
        )
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", settings.db_schema):
            raise MigrationError("Invalid LIVE_DEV_DB_SCHEMA.")
        for name, value in (
            ("LIVE_DEV_DB_HOST", settings.db_host),
            ("LIVE_DEV_SSH_HOST", settings.ssh_host),
        ):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*", value):
                raise MigrationError(f"Invalid {name}; use a hostname or IP address.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", settings.ssh_user):
            raise MigrationError("Invalid LIVE_DEV_SSH_ID.")
        if any(c in settings.ssh_password for c in "\n\r\0"):
            raise MigrationError(
                "LIVE_DEV_SSH_PASSWORD cannot contain a newline or NUL."
            )
        if not settings.db_name:
            raise MigrationError("LIVE_DEV_DB_NAME cannot be blank.")
        if settings.db_ssl not in {
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise MigrationError("Invalid LIVE_DEV_DB_SSL mode.")
        return settings


def ssh_command(settings, local_port, password_fd):
    remote_host = (
        f"[{settings.db_host}]" if ":" in settings.db_host else settings.db_host
    )
    return [
        "sshpass",
        "-d",
        str(password_fd),
        "ssh",
        "-F",
        "/dev/null",
        "-NT",
        "-p",
        str(settings.ssh_port),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "PreferredAuthentications=password,keyboard-interactive",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "LogLevel=ERROR",
        "-L",
        f"127.0.0.1:{local_port}:{remote_host}:{settings.db_port}",
        f"{settings.ssh_user}@{settings.ssh_host}",
    ]


@asynccontextmanager
async def dev_tunnel(settings):
    if not shutil.which("ssh") or not shutil.which("sshpass"):
        raise MigrationError(
            "ssh and sshpass are required, as in the other playground migrations."
        )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        local_port = probe.getsockname()[1]
    read_fd, write_fd = os.pipe()
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_command(settings, local_port, read_fd),
            pass_fds=(read_fd,),
            start_new_session=True,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        os.close(read_fd)
        read_fd = None
        os.write(write_fd, settings.ssh_password.encode() + b"\n")
        os.close(write_fd)
        write_fd = None
        deadline = asyncio.get_running_loop().time() + 25
        while True:
            if process.returncode is not None:
                raise MigrationError(
                    f"{settings.target} SSH tunnel failed (exit={process.returncode}); check SSH settings and known_hosts."
                )
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", local_port), timeout=1
                )
                writer.close()
                await writer.wait_closed()
                break
            except (OSError, TimeoutError):
                if asyncio.get_running_loop().time() >= deadline:
                    raise MigrationError(
                        f"{settings.target} SSH tunnel did not become ready within 25 seconds."
                    ) from None
                await asyncio.sleep(0.2)
        yield local_port
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()


def target_tables(schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise MigrationError("Invalid target schema.")
    return f'"{schema}"."{TABLE_NAME}"', f'"{schema}"."resources_ward"'


def row_values(alias):
    return "ROW(" + ", ".join(f"{alias}.{name}" for name in VALUE_FIELDS) + ")"


async def copy_rows(
    source, target, *, schema, write=False, batch_size=5000, month=None, target_name="dev"
):
    if target_name not in {"dev", "prod"}:
        raise MigrationError("Target must be dev or prod.")
    table, wards = target_tables(schema)
    fields = ", ".join(COPY_FIELDS)
    transaction = target.transaction(isolation="repeatable_read")
    await transaction.start()
    try:
        await target.execute("SET LOCAL lock_timeout='10s'")
        await target.execute("SET LOCAL statement_timeout='30min'")
        if not await target.fetchval("SELECT to_regclass($1) IS NOT NULL", table):
            raise MigrationError(
                f"Target table {table} is missing; create its nine-column schema first."
            )
        target_columns = {
            row["attname"]
            for row in await target.fetch(
                "SELECT attname FROM pg_attribute WHERE attrelid=$1::regclass "
                "AND attnum>0 AND NOT attisdropped",
                table,
            )
        }
        missing_columns = {"id", *COPY_FIELDS} - target_columns
        if missing_columns:
            raise MigrationError(
                f"Target table {table} is missing columns: {', '.join(sorted(missing_columns))}."
            )
        if write:
            log(f"Locking {target_name} target for an atomic copy")
            await target.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
        await target.execute("""
            CREATE TEMP TABLE risk_live_stage (
                ward_id bigint NOT NULL, month varchar(7) NOT NULL
                    CHECK (month ~ '^[0-9]{4}\\.(0[1-9]|1[0-2])$'),
                total_risk_count integer NOT NULL, risk_days integer[] NOT NULL,
                total_danger_stable_count integer NOT NULL, danger_stable_days integer[] NOT NULL,
                created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
                UNIQUE (ward_id, month)
            ) ON COMMIT DROP
        """)
        async with source.transaction(isolation="repeatable_read", readonly=True):
            where = " WHERE month=$1" if month is not None else ""
            params = (month,) if month is not None else ()
            total = await source.fetchval(
                f"SELECT count(*) FROM {SOURCE_TABLE}{where}", *params
            )
            staged = 0
            batch = []
            async for row in source.cursor(
                f"SELECT {fields} FROM {SOURCE_TABLE}{where} ORDER BY ward_id, month",
                *params,
                prefetch=batch_size,
            ):
                batch.append(tuple(row))
                if len(batch) == batch_size:
                    await target.copy_records_to_table(
                        "risk_live_stage",
                        schema_name="pg_temp",
                        records=batch,
                        columns=COPY_FIELDS,
                    )
                    staged += len(batch)
                    log(
                        f"Staged {staged:,}/{total:,} local rows ({staged / total * 100:.1f}%)"
                    )
                    batch.clear()
            if batch:
                await target.copy_records_to_table(
                    "risk_live_stage",
                    schema_name="pg_temp",
                    records=batch,
                    columns=COPY_FIELDS,
                )
                staged += len(batch)
            if staged != total:
                raise MigrationError(
                    "Local snapshot count differs from staged count; copy aborted."
                )
        log(f"Staged all {staged:,} rows; validating arrays and {target_name} ward references")
        invalid = await target.fetchval(f"""
            SELECT count(*) FROM {STAGE}
            WHERE total_risk_count <> cardinality(risk_days)
               OR total_danger_stable_count <> cardinality(danger_stable_days)
               OR NOT (danger_stable_days <@ risk_days)
               OR risk_days IS DISTINCT FROM ARRAY(SELECT DISTINCT d FROM unnest(risk_days) d ORDER BY d)
               OR danger_stable_days IS DISTINCT FROM ARRAY(SELECT DISTINCT d FROM unnest(danger_stable_days) d ORDER BY d)
               OR EXISTS (SELECT 1 FROM unnest(risk_days || danger_stable_days) d
                   WHERE d IS NULL OR d < 1 OR d > EXTRACT(DAY FROM
                       to_date(month, 'YYYY.MM') + interval '1 month' - interval '1 day'))
        """)
        if invalid:
            raise MigrationError(
                f"{invalid:,} local rows have invalid risk/recovery data; copy aborted."
            )
        skipped = await target.fetchrow(f"""
            SELECT count(DISTINCT s.ward_id) AS wards, count(*) AS rows
            FROM {STAGE} s LEFT JOIN {wards} w ON w.id=s.ward_id
            WHERE w.id IS NULL
        """)
        if skipped["rows"]:
            examples = await target.fetch(f"""
                SELECT DISTINCT s.ward_id FROM {STAGE} s
                LEFT JOIN {wards} w ON w.id=s.ward_id WHERE w.id IS NULL
                ORDER BY s.ward_id LIMIT 50
            """)
            ids = ", ".join(str(row["ward_id"]) for row in examples)
            log(
                f"Skipping {skipped['rows']:,} rows for {skipped['wards']:,} ward IDs "
                f"missing from {wards}. Missing IDs (up to 50): {ids}"
            )
            deleted = await target.execute(f"""
                DELETE FROM {STAGE} s
                WHERE NOT EXISTS (SELECT 1 FROM {wards} w WHERE w.id=s.ward_id)
            """)
            if deleted != f"DELETE {skipped['rows']}":
                raise MigrationError("Unexpected skipped-row count; rolling back.")
        summary = dict(
            await target.fetchrow(f"""
            SELECT count(*) AS eligible_rows,
                   count(*) FILTER (WHERE t.id IS NULL) AS inserts,
                   count(*) FILTER (WHERE t.id IS NOT NULL AND
                       {row_values("t")} IS DISTINCT FROM {row_values("s")}) AS updates
            FROM {STAGE} s LEFT JOIN {table} t ON t.ward_id=s.ward_id AND t.month=s.month
        """)
        )
        summary["source_rows"] = staged
        summary["skipped_wards"] = skipped["wards"]
        summary["skipped_rows"] = skipped["rows"]
        summary["unchanged"] = (
            summary["eligible_rows"] - summary["inserts"] - summary["updates"]
        )
        log(
            f"Plan: {summary['eligible_rows']:,} eligible, {summary['skipped_rows']:,} skipped, "
            f"{summary['inserts']:,} inserts, {summary['updates']:,} updates, {summary['unchanged']:,} unchanged"
        )
        if write:
            assignments = ", ".join(f"{name}=EXCLUDED.{name}" for name in VALUE_FIELDS)
            log(f"Applying {target_name} upserts")
            written = await target.fetchval(f"""
                WITH written AS (
                    INSERT INTO {table} AS t ({fields}) SELECT {fields} FROM {STAGE} WHERE TRUE
                    ON CONFLICT (ward_id, month) DO UPDATE SET {assignments}
                    WHERE {row_values("t")} IS DISTINCT FROM {row_values("EXCLUDED")}
                    RETURNING 1
                ) SELECT count(*) FROM written
            """)
            if written != summary["inserts"] + summary["updates"]:
                raise MigrationError(f"Unexpected {target_name} write count; rolling back.")
            mismatches = await target.fetchval(f"""
                SELECT count(*) FROM {STAGE} s LEFT JOIN {table} t
                ON t.ward_id=s.ward_id AND t.month=s.month
                WHERE t.id IS NULL OR {row_values("t")} IS DISTINCT FROM {row_values("s")}
            """)
            if mismatches:
                raise MigrationError(
                    f"{mismatches:,} copied rows failed verification; rolling back."
                )
            log(f"All eligible source keys verified in {target_name}; committing")
            await transaction.commit()
            summary["written"] = written
        else:
            await transaction.rollback()
        return {
            "target": target_name,
            "table": table,
            "mode": "committed" if write else "preview",
            **summary,
        }
    except BaseException:
        with contextlib.suppress(Exception):
            await transaction.rollback()
        raise
