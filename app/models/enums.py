"""Enumerations shared across models and the API layer.

These are stored as native PostgreSQL ENUM types. Adding a value later is an
explicit Alembic migration (``ALTER TYPE ... ADD VALUE``), which keeps the set
of valid states under version control.
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Native PostgreSQL ENUM that persists the member *value* (e.g.
    ``super_admin``), not the member *name* (``SUPER_ADMIN``).

    SQLAlchemy's default stores the name, which would not match the lowercase
    values declared in the migration's ``CREATE TYPE``. ``values_callable``
    aligns the two so inserts/reads round-trip correctly.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [member.value for member in obj],
    )


class UserRole(str, enum.Enum):
    """Application roles. Drives RBAC (see ``app.core.rbac``)."""

    SUPER_ADMIN = "super_admin"   # platform owner; not tied to an organization
    ORG_ADMIN = "org_admin"       # owner/admin of a single organization
    EMPLOYEE = "employee"         # field worker within an organization


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class WorkOrderStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Statuses surfaced in the Work Orders module UI (Pending / In Progress / Completed).
WORK_ORDER_USER_STATUSES = (
    WorkOrderStatus.PENDING,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.COMPLETED,
)


class WorkOrderPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"
