"""Data access for employees (users with role ``employee``), org-scoped."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User


class EmployeeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self, *, organization_id: uuid.UUID, search: str | None = None
    ) -> list[User]:
        filters = [
            User.organization_id == organization_id,
            User.role == UserRole.EMPLOYEE,
        ]
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

    def get(self, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.role == UserRole.EMPLOYEE,
        )
        return self.db.execute(stmt).scalar_one_or_none()

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
