from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.chat.attachments import cleanup_stale_artifacts
from app.chat.config import get_chat_settings
from app.chat.errors import ChatRequestError
from app.chat.router import router as chat_router
from app.identity.config import load_identity_settings
from app.identity.router import AccountBoundary, access_error, database_error, router as account_router, validation_error
from app.identity.store import AccessError, IdentityStore
from app.integrations import router as integration_router
from app.nextcloud.router import router as nextcloud_router
from app.rag_chat.router import router as rag_chat_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if not hasattr(app.state, "identity_store"):
        settings = load_identity_settings()
        app.state.identity_settings = settings
        app.state.identity_store = IdentityStore(settings)
    try:
        await run_in_threadpool(app.state.identity_store.ready)
        settings = get_chat_settings()
        cleanup_stale_artifacts(settings.artifact_root, settings.stale_after_seconds)
        yield
    finally:
        app.state.identity_store.engine.dispose()


async def health_check():
    return {"status": "ok"}


async def _chat_error_response(_request: Request, error: ChatRequestError):
    return JSONResponse(status_code=error.status_code,
                        content={"error": error.detail.model_dump(exclude_none=True)})


def create_app(*, identity_settings=None, identity_store=None):
    app = FastAPI(title="Nexgent Backend", version="0.1.0", lifespan=_lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    # Explicit dependency injection is used by tests; normal startup requires
    # the configured external database and signing key, with no unauthenticated mode.
    if identity_settings is not None:
        app.state.identity_settings = identity_settings
        app.state.identity_store = identity_store or IdentityStore(identity_settings)
    app.add_exception_handler(AccessError, access_error)
    app.add_exception_handler(SQLAlchemyError, database_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ChatRequestError, _chat_error_response)
    app.add_middleware(AccountBoundary)
    app.add_api_route("/health", health_check, methods=["GET"], include_in_schema=False)
    app.include_router(account_router)
    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    app.include_router(rag_chat_router, prefix="/api/rag/chat", tags=["rag-chat"])
    app.include_router(nextcloud_router, prefix="/api/nextcloud", tags=["nextcloud"])
    app.include_router(integration_router)
    return app


app = create_app()
