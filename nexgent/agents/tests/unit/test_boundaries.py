import httpx
import pytest

from apps.gateway import create_app


@pytest.mark.asyncio
async def test_gateway_health() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_gateway_does_not_run_without_internal_adapter() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/runs", json={"message": "hello"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_gateway_validates_public_input() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/runs", json={"message": ""})
    assert response.status_code == 422
