"""Notifications API (``/api/v1/notifications``) — the caller's own inbox."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.features.notifications import schemas
from app.features.notifications.service import NotificationService
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


@router.get("", response_model=schemas.NotificationListResponse)
def list_notifications(
    current_user: User = Depends(get_current_active_user),
    service: NotificationService = Depends(get_service),
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> schemas.NotificationListResponse:
    return service.list(
        current_user.id, unread_only=unread_only, page=page, page_size=page_size
    )


@router.get("/unread-count", response_model=schemas.UnreadCountResponse)
def unread_count(
    current_user: User = Depends(get_current_active_user),
    service: NotificationService = Depends(get_service),
) -> schemas.UnreadCountResponse:
    return schemas.UnreadCountResponse(unread=service.unread_count(current_user.id))


@router.post("/read-all", response_model=schemas.MarkAllReadResponse)
def mark_all_read(
    current_user: User = Depends(get_current_active_user),
    service: NotificationService = Depends(get_service),
) -> schemas.MarkAllReadResponse:
    return schemas.MarkAllReadResponse(updated=service.mark_all_read(current_user.id))


@router.patch("/{notification_id}/read", response_model=schemas.NotificationRead)
def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: NotificationService = Depends(get_service),
) -> schemas.NotificationRead:
    return schemas.NotificationRead.model_validate(
        service.mark_read(current_user.id, notification_id)
    )
