"""User model — covers super admins, organization admins, and employees.

Tenancy rule: ``organization_id`` is NULL only for ``SUPER_ADMIN`` (platform
scope). Every other role MUST belong to exactly one organization. This is
enforced by a CHECK constraint so the database itself rejects inconsistent rows.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, pg_enum

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.token import PasswordResetToken, RefreshToken
    from app.models.work_order import WorkOrder


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Email is unique per tenant; super admins (NULL org) are globally unique
        # via the partial index created in the migration.
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        CheckConstraint(
            "(role = 'super_admin' AND organization_id IS NULL) "
            "OR (role <> 'super_admin' AND organization_id IS NOT NULL)",
            name="ck_users_org_role_consistency",
        ),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---- Relationships ----
    organization: Mapped["Organization | None"] = relationship(back_populates="users")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    assigned_work_orders: Mapped[List["WorkOrder"]] = relationship(
        back_populates="assignee", foreign_keys="WorkOrder.assignee_id"
    )
