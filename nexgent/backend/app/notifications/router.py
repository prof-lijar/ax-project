from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response

from app.notifications.schemas import (
    NotificationCapabilities, NotificationStatus, RequestKey, SlackNotification,
)
from app.notifications.service import NotificationService
from app.notifications.store import NotificationStore

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_service(request: Request):
    settings = request.app.state.notification_settings
    store = NotificationStore(request.app.state.identity_store.engine, settings.deployment)
    return NotificationService(store, settings)


def owner(request):
    if getattr(request.state, "notification_service", False):
        return "service:notifications"
    return "user:" + request.state.account.user_id


@router.get("/capabilities", response_model=NotificationCapabilities)
def capabilities(request: Request):
    settings = request.app.state.notification_settings
    return {"enabled": settings.enabled, "destinations": sorted(settings.channels) if settings.enabled else []}


@router.post("/slack", response_model=NotificationStatus, status_code=202)
def submit(request: Request, response: Response, body: SlackNotification,
           idempotency_key: Annotated[RequestKey, Header()],
           service=Depends(get_service)):
    result = service.submit(owner(request), body, idempotency_key)
    response.headers["Location"] = f"/api/notifications/{result['id']}"
    return result


@router.get("/{notification_id}", response_model=NotificationStatus)
def get_status(request: Request, notification_id: UUID, service=Depends(get_service)):
    return service.store.get(owner(request), str(notification_id))
