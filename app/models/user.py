"""User model — organization admins and employees.

Tenancy rule: every user belongs to exactly one organization (``organization_id``
is NOT NULL). The role (``ADMIN`` / ``EMPLOYEE``) determines what they may do
within that organization; see ``app.core.rbac``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, UserStatus, pg_enum

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.token import PasswordResetToken, RefreshToken
    from app.models.work_order import WorkOrder


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Email is unique per tenant (when provided; employees may sign in by phone).
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    designation: Mapped[str | None] = mapped_column(String(120))

    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"),
        nullable=False,
    )
    # Lifecycle state. Self-registrations start PENDING_APPROVAL; admin-created
    # users are ACTIVE. ``is_active`` mirrors this (only ACTIVE is sign-in-able)
    # and remains the canonical flag the login/RBAC guards read.
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"),
        default=UserStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def is_pending(self) -> bool:
        return self.status == UserStatus.PENDING_APPROVAL

    # ---- Soft delete (employees are never physically removed) ----
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_employee_name: Mapped[str | None] = mapped_column(String(255))

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    # ---- Relationships ----
    organization: Mapped["Organization"] = relationship(back_populates="users")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    assigned_work_orders: Mapped[List["WorkOrder"]] = relationship(
        back_populates="assignee", foreign_keys="WorkOrder.assignee_id"
    )
