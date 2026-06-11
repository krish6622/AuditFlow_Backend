"""Pydantic models for the notifications API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str | None
    work_order_id: uuid.UUID | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    unread: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread: int


class MarkAllReadResponse(BaseModel):
    updated: int
