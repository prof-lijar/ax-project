"""Shared bounded file-transfer primitives and safe errors."""

import httpx


class FileIntegrationError(RuntimeError):
    """Safe code only; never propagate provider response bodies."""


async def bounded_response(response: httpx.Response, limit: int) -> bytes:
    data = bytearray()
    async for chunk in response.aiter_bytes():
        data.extend(chunk)
        if len(data) > limit:
            raise FileIntegrationError("response_too_large")
    return bytes(data)
