"""Read-side service for a user's notification inbox."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.features.notifications import schemas
from app.features.notifications.repository import NotificationRepository
from app.models.notification import Notification


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = NotificationRepository(db)

    def list(
        self, user_id: uuid.UUID, *, unread_only: bool, page: int, page_size: int
    ) -> schemas.NotificationListResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items, total = self.repo.list(
            user_id=user_id, unread_only=unread_only, page=page, page_size=page_size
        )
        return schemas.NotificationListResponse(
            items=[schemas.NotificationRead.model_validate(i) for i in items],
            total=total,
            unread=self.repo.unread_count(user_id=user_id),
            page=page,
            page_size=page_size,
        )

    def unread_count(self, user_id: uuid.UUID) -> int:
        return self.repo.unread_count(user_id=user_id)

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        entry = self.repo.get(notification_id=notification_id, user_id=user_id)
        if entry is None:
            raise NotFoundError("Notification not found")
        if not entry.is_read:
            entry.is_read = True
            self.db.commit()
            self.db.refresh(entry)
        return entry

    def mark_all_read(self, user_id: uuid.UUID) -> int:
        updated = self.repo.mark_all_read(user_id=user_id)
        self.db.commit()
        return updated
