"""Loopback-only acceptance server. No production OCR or message interpretation."""

import hashlib
import hmac
import json
import os
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from app.models import Region

MAX_IMAGE_BYTES = 20 * 1024**2


def create_app(root, token, failures=0, failure_status=503, retry_after="1"):
    if not token:
        raise ValueError("Set KAKAO_MOCK_TOKEN before starting the mock server")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    database = root / "mock.db"
    with sqlite3.connect(database) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS captures (
            capture_id TEXT PRIMARY KEY, metadata TEXT NOT NULL, image BLOB NOT NULL)""")
    app = FastAPI(title="Kakao Capture Mock API")
    app.state.remaining_failures = failures

    @app.post("/api/v1/captures")
    async def receive(
        image: Annotated[UploadFile, File()],
        capture_id: Annotated[str, Form()],
        device_id: Annotated[str, Form()],
        chat_id: Annotated[str, Form()],
        timestamp: Annotated[str, Form()],
        capture_mode: Annotated[str, Form()],
        image_hash: Annotated[str, Form()],
        region: Annotated[str, Form()],
        sequence_number: Annotated[int, Form()],
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "Authentication required")
        if app.state.remaining_failures > 0:
            app.state.remaining_failures -= 1
            raise HTTPException(
                failure_status, "Simulated failure", headers={"Retry-After": retry_after}
            )
        png = await image.read(MAX_IMAGE_BYTES + 1)
        if len(png) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image too large")
        try:
            UUID(capture_id)
            captured_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if captured_at.utcoffset() is None or captured_at.utcoffset().total_seconds() != 0:
                raise ValueError()
            coordinates = Region(**json.loads(region))
            coordinates.validate()
            if (
                capture_mode not in ("live", "history")
                or sequence_number < 1
                or not device_id.strip()
                or not chat_id.strip()
                or len(device_id) > 256
                or len(chat_id) > 256
                or idempotency_key != capture_id
            ):
                raise ValueError()
            if len(png) < 24 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError()
            width, height = struct.unpack(">II", png[16:24])
            if (width, height) != (
                coordinates.width,
                coordinates.height,
            ) or width * height > 40_000_000:
                raise ValueError()
            if hashlib.sha256(png).hexdigest() != image_hash:
                raise ValueError()
            import cv2
            import numpy as np

            decoded = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None or decoded.shape[:2] != (height, width):
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            raise HTTPException(422, "Invalid capture payload") from None
        metadata = json.dumps(
            {
                "capture_id": capture_id,
                "device_id": device_id,
                "chat_id": chat_id,
                "timestamp": timestamp,
                "capture_mode": capture_mode,
                "image_hash": image_hash,
                "region": json.loads(region),
                "sequence_number": sequence_number,
            },
            sort_keys=True,
        )
        with sqlite3.connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT metadata FROM captures WHERE capture_id=?", (capture_id,)
            ).fetchone()
            if previous and previous[0] != metadata:
                raise HTTPException(409, "Capture ID already exists with a different payload")
            db.execute("INSERT OR IGNORE INTO captures VALUES(?,?,?)", (capture_id, metadata, png))
        # Commit has completed before acknowledgement.
        return {"status": "accepted", "capture_id": capture_id}

    return app


def from_env():
    return create_app(
        os.environ.get("KAKAO_MOCK_DATA", "mock-data"),
        os.environ.get("KAKAO_MOCK_TOKEN", ""),
        int(os.environ.get("KAKAO_MOCK_FAILURES", "0")),
        int(os.environ.get("KAKAO_MOCK_STATUS", "503")),
        os.environ.get("KAKAO_MOCK_RETRY_AFTER", "1"),
    )
