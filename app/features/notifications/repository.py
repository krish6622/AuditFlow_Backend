"""Data access for in-app notifications, scoped to a single recipient."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.enums import NotificationType, UserRole
from app.models.notification import Notification
from app.models.user import User


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- write (used by the work-order workflow; caller commits) ---- #
    def add(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str | None = None,
        work_order_id: uuid.UUID | None = None,
    ) -> Notification:
        entry = Notification(
            organization_id=organization_id,
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            work_order_id=work_order_id,
        )
        self.db.add(entry)
        return entry

    def active_admin_ids(
        self, *, organization_id: uuid.UUID, exclude: uuid.UUID | None = None
    ) -> list[uuid.UUID]:
        stmt = select(User.id).where(
            User.organization_id == organization_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
        if exclude is not None:
            stmt = stmt.where(User.id != exclude)
        return list(self.db.execute(stmt).scalars().all())

    # ---- read ---- #
    def list(
        self,
        *,
        user_id: uuid.UUID,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Notification], int]:
        filters = [Notification.user_id == user_id]
        if unread_only:
            filters.append(Notification.is_read.is_(False))
        total = self.db.execute(
            select(func.count()).select_from(Notification).where(*filters)
        ).scalar_one()
        rows = (
            self.db.execute(
                select(Notification)
                .where(*filters)
                .order_by(Notification.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def unread_count(self, *, user_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            ).scalar_one()
        )

    def get(self, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification | None:
        return self.db.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        ).scalar_one_or_none()

    def mark_all_read(self, *, user_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        return int(result.rowcount or 0)
