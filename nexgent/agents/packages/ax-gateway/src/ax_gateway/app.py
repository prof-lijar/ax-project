import json
from collections.abc import AsyncIterator
from typing import Any

from ax_contracts import AgentInput
from ax_integrations import AgentServerClient, AgentServerUnavailable
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse


class UnconfiguredClient:
    async def submit(self, assistant_id: str, input: AgentInput) -> dict[str, Any]:
        raise AgentServerUnavailable("Agent Server adapter is not configured")

    async def get(self, run_id: str) -> dict[str, Any]:
        raise AgentServerUnavailable("Agent Server adapter is not configured")

    async def stream(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        raise AgentServerUnavailable("Agent Server adapter is not configured")
        yield  # pragma: no cover

    async def resume(self, thread_id: str, command: dict[str, Any]) -> dict[str, Any]:
        raise AgentServerUnavailable("Agent Server adapter is not configured")


def create_app(client: AgentServerClient | None = None) -> FastAPI:
    """Create the gateway app; inject a real adapter in deployment/tests."""

    app = FastAPI(title="AX Agent Gateway", version="0.1.0")
    adapter = client or UnconfiguredClient()

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/runs")
    async def submit_run(payload: AgentInput, assistant_id: str = "agent") -> dict[str, Any]:
        try:
            return await adapter.submit(assistant_id, payload)
        except AgentServerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        try:
            return await adapter.get(run_id)
        except AgentServerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/runs/{run_id}/events")
    async def stream_run(run_id: str) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            try:
                async for event in adapter.stream(run_id):
                    yield f"data: {json.dumps(event)}\n\n"
            except AgentServerUnavailable as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/v1/threads/{thread_id}/resume")
    async def resume_thread(thread_id: str, command: dict[str, Any]) -> dict[str, Any]:
        try:
            return await adapter.resume(thread_id, command)
        except AgentServerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()
