"""Explicit production-only switches; never infer a target from local credentials."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit


def production_enabled(values: Mapping[str, str], key: str) -> bool:
    value = values.get(key, "false")
    if value not in {"true", "false"}:
        raise ValueError(f"{key} must be true or false")
    if value == "true" and values.get("WEEKLY_REPORT_DEPLOYMENT") != "production":
        raise ValueError(f"{key} requires WEEKLY_REPORT_DEPLOYMENT=production")
    return value == "true"


@dataclass(frozen=True)
class SyncSettings:
    local_dsn: str = field(repr=False)
    target_dsn: str = field(repr=False)
    poll_seconds: int = 30
    max_attempts: int = 8
    limit: int = 100

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SyncSettings:
        values = os.environ if environ is None else environ
        if not production_enabled(values, "WEEKLY_REPORT_SYNC_ENABLED"):
            raise ValueError("WEEKLY_REPORT_SYNC_ENABLED must be true")
        if values.get("WEEKLY_REPORT_SYNC_WARD_IDS_VERIFIED") != "true":
            raise ValueError("WEEKLY_REPORT_SYNC_WARD_IDS_VERIFIED must be true")
        local = values.get("WEEKLY_REPORT_SYNC_LOCAL_DSN", "")
        target = values.get("WEEKLY_REPORT_SYNC_TARGET_DSN", "")
        if not local or not target or local == target:
            raise ValueError(
                "explicit, distinct sync local and target DSNs are required"
            )
        try:
            endpoint = urlsplit(target)
            query = parse_qs(endpoint.query)
            valid_target = (
                endpoint.scheme in {"postgres", "postgresql"}
                and bool(endpoint.hostname)
                and query.get("sslmode") == ["verify-full"]
                and bool(query.get("sslrootcert"))
            )
        except ValueError:
            valid_target = False
        if not valid_target:
            raise ValueError("target DSN requires verify-full TLS and an explicit CA")
        return cls(local, target)
