"""Data access for organization members (admins and employees), org-scoped.

The list/get surface returns every user in the organization — both ADMIN and
EMPLOYEE — so admins can be shown and demoted. Role/status changes still flow
through the service, which enforces the business rules (e.g. last-admin guard).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole, UserStatus, WorkOrderStatus
from app.models.user import User
from app.models.work_order import WorkOrder

# Employee-list ``status`` query values mapped to the lifecycle enum.
_STATUS_FILTERS = {
    "active": UserStatus.ACTIVE,
    "inactive": UserStatus.INACTIVE,
    "pending": UserStatus.PENDING_APPROVAL,
    "pending_approval": UserStatus.PENDING_APPROVAL,
}

# Statuses that make a work order "active" and block deletion of its assignee.
_ACTIVE_WO_STATUSES = (
    WorkOrderStatus.AWAITING_ASSIGNMENT,
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
)


class EmployeeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        organization_id: uuid.UUID,
        search: str | None = None,
        status: str | None = None,  # "active" | "inactive" | "pending"
        include_deleted: bool = False,
    ) -> list[User]:
        filters = [User.organization_id == organization_id]
        if not include_deleted:
            filters.append(User.deleted_at.is_(None))
        mapped_status = _STATUS_FILTERS.get(status) if status else None
        if mapped_status is not None:
            filters.append(User.status == mapped_status)
        if search:
            like = f"%{search.strip()}%"
            filters.append(
                or_(
                    User.full_name.ilike(like),
                    User.phone.ilike(like),
                    User.email.ilike(like),
                    User.designation.ilike(like),
                )
            )
        rows = self.db.execute(
            select(User).where(*filters).order_by(User.created_at.desc())
        ).scalars().all()
        return list(rows)

    def get(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> User | None:
        filters = [User.id == user_id, User.organization_id == organization_id]
        if not include_deleted:
            filters.append(User.deleted_at.is_(None))
        return self.db.execute(select(User).where(*filters)).scalar_one_or_none()

    def count_active_admins(self, *, organization_id: uuid.UUID) -> int:
        """Number of active, non-deleted ADMIN users (last-admin guard)."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        return self.db.execute(stmt).scalar_one()

    def count_admins(self, *, organization_id: uuid.UUID) -> int:
        """Number of non-deleted ADMIN users (delete last-admin guard)."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.ADMIN,
                User.deleted_at.is_(None),
            )
        )
        return self.db.execute(stmt).scalar_one()

    def count_pending(self, *, organization_id: uuid.UUID) -> int:
        """Number of non-deleted users awaiting approval."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.status == UserStatus.PENDING_APPROVAL,
                User.deleted_at.is_(None),
            )
        )
        return self.db.execute(stmt).scalar_one()

    def has_active_work_orders(self, *, user_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.assignee_id == user_id,
                WorkOrder.status.in_(_ACTIVE_WO_STATUSES),
            )
        )
        return self.db.execute(stmt).scalar_one() > 0

    def restamp_work_order_names(self, *, user_id: uuid.UUID, label: str) -> None:
        """Mark the (completed/closed) work orders of a deleted employee so old
        records still read e.g. 'Hari Prasath (Deleted)'."""
        self.db.execute(
            WorkOrder.__table__.update()
            .where(WorkOrder.assignee_id == user_id)
            .values(assigned_employee_name=label)
        )

    def email_taken(self, email: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.execute(stmt.limit(1)).first() is not None

    def phone_taken(self, phone: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(User.phone == phone.strip())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.execute(stmt.limit(1)).first() is not None

    def add(self, user: User) -> User:
        self.db.add(user)
        return user
