"""Role-Based Access Control.

Permissions are coarse-grained capability strings (``resource:action``). Each
role maps to a fixed permission set. Routes declare what they need with the
``require_permissions`` dependency (see ``app.core.dependencies``).

Keeping the matrix here — in one place — means authorization rules are auditable
and unit-testable independently of any endpoint.
"""
from __future__ import annotations

from app.models.enums import UserRole


class Permission(str):
    """Capability identifiers (``resource:action``)."""


# ---- Organizations ----
ORG_MANAGE = "org:manage"            # manage the organization's own settings

# ---- Employees ----
EMPLOYEE_MANAGE = "employee:manage"  # add/edit/activate/deactivate/assign roles
EMPLOYEE_VIEW = "employee:view"

# ---- Audit log ----
AUDIT_VIEW = "audit:view"            # read the organization's audit trail

# ---- Customers ----
CUSTOMER_MANAGE = "customer:manage"
CUSTOMER_VIEW = "customer:view"

# ---- Work orders ----
WORKORDER_MANAGE = "workorder:manage"        # assign/edit/close/cancel/delete
WORKORDER_CREATE_REQUEST = "workorder:create_request"  # raise a new work request
WORKORDER_VIEW_ALL = "workorder:view_all"    # see every order in the org
WORKORDER_VIEW_ASSIGNED = "workorder:view_assigned"  # see only own assignments
WORKORDER_UPDATE_STATUS = "workorder:update_status"  # progress/notes/photos/complete

# ---- Invoices ----
INVOICE_MANAGE = "invoice:manage"
INVOICE_VIEW = "invoice:view"

# ---- Reports ----
REPORT_VIEW = "report:view"


_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    # ADMIN runs the organization: staff, customers, work orders, invoices,
    # the audit trail, and org settings.
    UserRole.ADMIN: frozenset(
        {
            ORG_MANAGE,
            EMPLOYEE_MANAGE,
            EMPLOYEE_VIEW,
            AUDIT_VIEW,
            CUSTOMER_MANAGE,
            CUSTOMER_VIEW,
            WORKORDER_MANAGE,
            WORKORDER_CREATE_REQUEST,
            WORKORDER_VIEW_ALL,
            INVOICE_MANAGE,
            INVOICE_VIEW,
            REPORT_VIEW,
        }
    ),
    # EMPLOYEE can raise requests and progress their own assigned work.
    UserRole.EMPLOYEE: frozenset(
        {
            WORKORDER_CREATE_REQUEST,
            WORKORDER_VIEW_ASSIGNED,
            WORKORDER_UPDATE_STATUS,
        }
    ),
}


def permissions_for(role: UserRole) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in permissions_for(role)
