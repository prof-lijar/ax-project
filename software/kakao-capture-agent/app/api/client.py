import hashlib
import json
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from app.config import validate_endpoint


class UploadError(Exception):
    def __init__(self, message, retryable=False, retry_after=None, authentication=False):
        super().__init__(message)
        self.retryable, self.retry_after, self.authentication = (
            retryable,
            retry_after,
            authentication,
        )


def retry_delay(attempt, retry_after=None, now=None, random_value=None):
    backoff = min(300, 2 ** min(attempt, 20)) + (
        random.random() if random_value is None else random_value
    )
    if retry_after:
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                date = parsedate_to_datetime(retry_after)
                seconds = (date - (now or datetime.now(timezone.utc))).total_seconds()
            except (TypeError, ValueError, OverflowError):
                seconds = 0
        if 0 <= seconds < float("inf"):
            backoff = max(backoff, seconds)
    return backoff


async def upload(client, job, token):
    validate_endpoint(job["destination"], bool(job["allow_local_http"]))
    if not token:
        raise UploadError("API token is not configured", authentication=True)
    metadata = json.loads(job["metadata"])
    try:
        png = Path(job["image_path"]).read_bytes()
    except OSError:
        raise UploadError("Queued image is missing or unreadable") from None
    if hashlib.sha256(png).hexdigest() != job["image_hash"]:
        raise UploadError("Queued image failed integrity verification")
    fields = {
        key: json.dumps(value) if key == "region" else str(value) for key, value in metadata.items()
    }
    try:
        response = await client.post(
            job["destination"],
            data=fields,
            files={"image": (f"{job['capture_id']}.png", png, "image/png")},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": job["capture_id"]},
        )
    except httpx.RequestError:
        raise UploadError("Network request failed or timed out", retryable=True) from None
    code = response.status_code
    if code in (401, 403):
        raise UploadError(f"API authentication rejected (HTTP {code})", authentication=True)
    if code == 429 or code >= 500:
        raise UploadError(
            f"Temporary API failure (HTTP {code})", True, response.headers.get("Retry-After")
        )
    if not 200 <= code < 300:
        raise UploadError(f"API rejected capture (HTTP {code})")
    try:
        body = response.json()
        valid = (
            isinstance(body, dict)
            and body.get("status") == "accepted"
            and body.get("capture_id") == job["capture_id"]
        )
    except ValueError:
        valid = False
    if not valid:
        raise UploadError("API acknowledgement is invalid", retryable=True)
