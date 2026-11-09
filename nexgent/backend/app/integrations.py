"""Same-origin feature gateway. AccountBoundary authenticates every request."""
import os

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.identity.router import require_admin

router = APIRouter()
# Fixed server-side destinations: the browser cannot choose a host.
UPSTREAMS = {
    "agent-server": ("AX_AGENT_SERVER_URL", "http://agent-server:2024"),
    "weekly-report-bulk-api": ("AX_WEEKLY_REPORT_BULK_URL", "http://weekly-report-bulk-api:8090"),
    "scout-api": ("AX_SCOUT_URL", "http://scout:8091"),
    "scout-scheduler-api": ("AX_SCOUT_SCHEDULER_URL", "http://host.docker.internal:8092"),
    "rag-api": ("AX_RAG_SERVER_URL", "http://host.docker.internal:8765"),
}
# These gateways back the administrator-only Knowledge and agent workspaces.
ADMIN_ONLY_UPSTREAMS = {"rag-api", "scout-api", "scout-scheduler-api", "weekly-report-bulk-api"}
REQUEST_HEADERS = {"accept", "content-type", "range", "if-range"}
RESPONSE_HEADERS = {"content-type", "content-disposition", "content-encoding",
                    "content-length", "content-range", "accept-ranges"}


def endpoint(variable, default):
    async def proxy(request: Request, path: str):
        if variable == "AX_AGENT_SERVER_URL" and not (request.method in {"GET", "HEAD"} and path == "ok"):
            require_admin(request)
        base = httpx.URL(os.getenv(variable, default).rstrip("/"))
        if base.scheme not in {"http", "https"} or not base.host or base.userinfo or base.query or base.fragment:
            return JSONResponse({"error": {"code": "integration_unavailable"}}, status_code=503)
        url = base.copy_with(path=base.path.rstrip("/") + "/" + path,
                             query=request.scope["query_string"])
        # Never forward account cookies, CSRF values or browser Authorization.
        headers = {key: value for key, value in request.headers.items() if key in REQUEST_HEADERS}
        headers["accept-encoding"] = "identity"
        client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5, pool=5), follow_redirects=False)
        try:
            upstream_request = client.build_request(request.method, url, headers=headers, content=request.stream())
            response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return JSONResponse({"error": {"code": "integration_unavailable"}}, status_code=502)
        except BaseException:
            await client.aclose()
            raise

        async def close():
            await response.aclose()
            await client.aclose()

        # A redirect to a private upstream would bypass the authenticated boundary.
        if response.is_redirect or response.status_code == 401:
            await close()
            return JSONResponse({"error": {"code": "integration_unavailable"}}, status_code=502)

        async def body():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await close()

        return StreamingResponse(body(), status_code=response.status_code,
                                 headers={k: v for k, v in response.headers.items() if k in RESPONSE_HEADERS},
                                 background=BackgroundTask(close))
    return proxy


for prefix, (variable, default) in UPSTREAMS.items():
    router.add_api_route(f"/{prefix}/{{path:path}}", endpoint(variable, default),
                         methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
                         dependencies=[Depends(require_admin)] if prefix in ADMIN_ONLY_UPSTREAMS else [])
