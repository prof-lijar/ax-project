import logging
import re
import secrets
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, StringConstraints
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from app.identity.security import csrf_token
from app.identity.store import AccessError

logger = logging.getLogger(__name__)
router = APIRouter()
Username = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$"),
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)]
Password = Annotated[SecretStr, Field(min_length=4, max_length=12)]
Ids = Annotated[list[UUID], Field(max_length=500)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=256)]


class UserInput(Input):
    username: Username
    name: Name
    email: Email = ""
    password: Password
    role_ids: Ids = Field(default_factory=list)
    group_ids: Ids = Field(default_factory=list)


class UserUpdate(Input):
    name: Name
    email: Email = ""
    is_active: bool
    role_ids: Ids
    group_ids: Ids


class PasswordInput(Input):
    password: Password


class GroupInput(Input):
    name: Label
    description: Description = ""
    role_ids: Ids = Field(default_factory=list)


class RoleInput(Input):
    name: Label
    description: Description = ""
    permission_ids: Ids = Field(default_factory=list)


class PermissionInput(Input):
    key: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_.:-]{1,99}$")]
    description: Description = ""


def error_response(status, code):
    return JSONResponse({"error": {"code": code}}, status_code=status,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


async def access_error(_request, error: AccessError):
    return error_response(error.status, error.code)


async def database_error(_request, _error: SQLAlchemyError):
    logger.error("Account database unavailable")
    return error_response(503, "account_unavailable")


async def validation_error(_request, _error: RequestValidationError):
    # Do not reflect password inputs in FastAPI's default validation details.
    return error_response(422, "invalid_input")


class AccountBoundary(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health" and request.method in {"GET", "HEAD"}:
            return await call_next(request)
        if not hasattr(request.app.state, "identity_settings"):
            return error_response(503, "account_unavailable")
        settings = request.app.state.identity_settings
        path = request.url.path
        # Machine credentials grant access only to the notification API. Browser
        # sessions continue through the existing Origin/CSRF checks.
        machine_route = (
            (request.method == "POST" and path == "/api/notifications/slack")
            or (request.method == "GET" and path == "/api/notifications/capabilities")
            or (request.method == "GET" and re.fullmatch(r"/api/notifications/[0-9a-fA-F-]{36}", path))
        )
        machine = False
        authorization = request.headers.get("authorization", "")
        if machine_route and authorization:
            configured = request.app.state.notification_settings.service_token.get_secret_value()
            scheme, _, token = authorization.partition(" ")
            if (scheme.lower() != "bearer" or not configured or len(token) > 512
                    or not secrets.compare_digest(token.encode(), configured.encode())):
                return error_response(401, "invalid_notification_token")
            machine = True
            request.state.notification_service = True
        if not machine and path not in {"/health", "/auth/login"}:
            try:
                account = await run_in_threadpool(
                    request.app.state.identity_store.authenticate,
                    request.cookies.get(settings.cookie_name),
                )
            except Exception:
                logger.error("Account lookup unavailable")
                return error_response(503, "account_unavailable")
            if account is None:
                return error_response(401, "authentication_required")
            request.state.account = account
        if not machine and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != settings.public_url:
                return error_response(403, "origin_not_allowed")
            if path != "/auth/login":
                expected = csrf_token(request.cookies.get(settings.cookie_name, ""))
                if not secrets.compare_digest(request.headers.get("x-csrf-token", "").encode(), expected.encode()):
                    return error_response(403, "csrf_failed")
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def require_permission(key: str):
    """Reusable FastAPI dependency for future feature-specific permissions."""
    def check(request: Request):
        if key not in request.state.account.permissions:
            raise AccessError(403, "permission_denied")
        return request.state.account
    return check


require_admin = require_permission("access.manage")


@router.post("/auth/login")
def login(request: Request, body: LoginInput):
    settings = request.app.state.identity_settings
    token = request.app.state.identity_store.login(body.username, body.password.get_secret_value())
    if token is None:
        return error_response(401, "invalid_credentials")
    response = JSONResponse({"authenticated": True})
    response.set_cookie(settings.cookie_name, token, max_age=settings.login_seconds,
                        secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    return response


@router.post("/auth/logout")
def logout(request: Request):
    settings = request.app.state.identity_settings
    request.app.state.identity_store.logout(request.state.account)
    response = JSONResponse({"signed_out": True})
    response.delete_cookie(settings.cookie_name, path="/", secure=settings.secure_cookies)
    return response


@router.get("/api/me")
def me(request: Request):
    account = request.state.account
    settings = request.app.state.identity_settings
    return {"id": account.user_id, "username": account.username, "name": account.display_name,
            "email": account.email, "roles": account.roles, "permissions": account.permissions,
            "is_admin": "access.manage" in account.permissions,
            "csrf_token": csrf_token(request.cookies[settings.cookie_name])}


@router.get("/api/admin/access")
def catalog(request: Request, actor=Depends(require_admin)):
    return request.app.state.identity_store.catalog(actor)


@router.post("/api/admin/users", status_code=201)
def create_user(request: Request, body: UserInput, actor=Depends(require_admin)):
    values = body.model_dump(mode="json", exclude={"password"})
    return request.app.state.identity_store.create_user(actor, **values, password=body.password.get_secret_value())


@router.put("/api/admin/users/{user_id}")
def update_user(request: Request, user_id: UUID, body: UserUpdate, actor=Depends(require_admin)):
    values = body.model_dump(mode="json")
    values["display_name"] = values.pop("name")
    return request.app.state.identity_store.update_user(actor, str(user_id), values)


@router.put("/api/admin/users/{user_id}/password")
def reset_password(request: Request, user_id: UUID, body: PasswordInput, actor=Depends(require_admin)):
    request.app.state.identity_store.reset_password(actor, str(user_id), body.password.get_secret_value())
    return {"updated": True}


@router.post("/api/admin/groups", status_code=201)
def create_group(request: Request, body: GroupInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "groups", None, body.model_dump(mode="json"))


@router.put("/api/admin/groups/{item_id}")
def update_group(request: Request, item_id: UUID, body: GroupInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "groups", str(item_id), body.model_dump(mode="json"))


@router.post("/api/admin/roles", status_code=201)
def create_role(request: Request, body: RoleInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "roles", None, body.model_dump(mode="json"))


@router.put("/api/admin/roles/{item_id}")
def update_role(request: Request, item_id: UUID, body: RoleInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "roles", str(item_id), body.model_dump(mode="json"))


@router.post("/api/admin/permissions", status_code=201)
def create_permission(request: Request, body: PermissionInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "permissions", None, body.model_dump())


@router.put("/api/admin/permissions/{item_id}")
def update_permission(request: Request, item_id: UUID, body: PermissionInput, actor=Depends(require_admin)):
    return request.app.state.identity_store.save_item(actor, "permissions", str(item_id), body.model_dump())


@router.delete("/api/admin/{kind}/{item_id}")
def delete_item(request: Request, kind: Literal["groups", "roles", "permissions"],
                item_id: UUID, actor=Depends(require_admin)):
    request.app.state.identity_store.delete_item(actor, kind, str(item_id))
    return {"deleted": True}
