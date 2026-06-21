"""Audit log model — an append-only trail of security-sensitive user changes.

Every role promotion/demotion and activation/deactivation writes one row here,
scoped to the organization, capturing who acted, on whom, and the before/after
role. Actor and subject use ``ON DELETE SET NULL`` so history survives even if a
referenced user is later removed.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction, UserRole, pg_enum

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.organization import Organization
    from app.models.user import User


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    affected_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    # Customer-master changes reference the affected customer instead of a user.
    # ``SET NULL`` so a hard-deleted customer's trail survives; ``entity_name``
    # snapshots the name at action time so the log is readable regardless.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        index=True,
    )
    entity_name: Mapped[str | None] = mapped_column(String(255))

    action: Mapped[AuditAction] = mapped_column(
        pg_enum(AuditAction, "audit_action"), nullable=False
    )
    # Populated for role changes; NULL for status changes. Reuses the user_role
    # enum type (create_type=False in the migration — the type already exists).
    old_role: Mapped[UserRole | None] = mapped_column(
        pg_enum(UserRole, "user_role")
    )
    new_role: Mapped[UserRole | None] = mapped_column(
        pg_enum(UserRole, "user_role")
    )

    # ---- Relationships (read-side convenience for the audit log API) ----
    organization: Mapped["Organization"] = relationship()
    performed_by: Mapped["User | None"] = relationship(
        foreign_keys=[performed_by_user_id]
    )
    affected_user: Mapped["User | None"] = relationship(
        foreign_keys=[affected_user_id]
    )
    customer: Mapped["Customer | None"] = relationship(foreign_keys=[customer_id])
