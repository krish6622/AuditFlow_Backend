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
    """Application roles. Drives RBAC (see ``app.core.rbac``).

    A two-role model: every user belongs to exactly one organization and is
    either its ADMIN (manages employees, work orders, invoices, org settings)
    or an EMPLOYEE (field worker scoped to their own assigned work).
    """

    ADMIN = "admin"          # organization administrator
    EMPLOYEE = "employee"    # field worker within an organization


class UserStatus(str, enum.Enum):
    """Account lifecycle state, independent of role.

    Self-registered users start ``PENDING_APPROVAL`` and cannot sign in until an
    admin approves them (-> ``ACTIVE``) or rejects them (-> ``INACTIVE``). Admins
    can later deactivate (``ACTIVE`` -> ``INACTIVE``) or reactivate. ``is_active``
    on the user row is kept in lockstep (only ``ACTIVE`` is sign-in-able).
    """

    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    INACTIVE = "inactive"


class AuditAction(str, enum.Enum):
    """Security-sensitive actions recorded in ``audit_logs``.

    Role changes carry ``old_role``/``new_role``; status changes leave them NULL.
    """

    ROLE_PROMOTED = "role_promoted"        # EMPLOYEE -> ADMIN
    ROLE_DEMOTED = "role_demoted"          # ADMIN -> EMPLOYEE
    STATUS_ACTIVATED = "status_activated"
    STATUS_DEACTIVATED = "status_deactivated"
    USER_APPROVED = "user_approved"        # PENDING_APPROVAL -> ACTIVE
    USER_REJECTED = "user_rejected"        # PENDING_APPROVAL -> INACTIVE
    USER_DELETED = "user_deleted"          # soft delete


class NotificationType(str, enum.Enum):
    """In-app notification categories tied to the work-order workflow."""

    WORKORDER_REQUESTED = "workorder_requested"   # new request → admins
    WORKORDER_ASSIGNED = "workorder_assigned"     # assigned → employee
    WORKORDER_COMPLETED = "workorder_completed"   # completed → admins
    WORKORDER_CLOSED = "workorder_closed"         # closed → requester


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class WorkOrderStatus(str, enum.Enum):
    """Lifecycle of an auditor-office work order.

    Flow: AWAITING_ASSIGNMENT (employee request) → ASSIGNED (admin assigns an
    employee + due date) → IN_PROGRESS → COMPLETED (employee) → CLOSED (admin
    reviews/invoices). CANCELLED is an admin escape hatch from any open state.
    """

    AWAITING_ASSIGNMENT = "awaiting_assignment"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


# Progress statuses an assigned employee can move an order through.
WORK_ORDER_USER_STATUSES = (
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.COMPLETED,
)


class WorkOrderPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkOrderCategory(str, enum.Enum):
    """Service categories for an auditor office. ``OTHERS`` pairs with a
    free-text ``category_other`` on the work order."""

    INCOME_TAX = "income_tax"
    GST = "gst"
    PROJECT_REPORT = "project_report"
    AUDIT = "audit"
    ROC = "roc"
    FINANCIAL_STATEMENT = "financial_statement"
    TDS = "tds"
    ACCOUNTING = "accounting"
    OTHERS = "others"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"
