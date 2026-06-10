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
ORG_MANAGE = "org:manage"            # create/update/delete any organization (platform)
ORG_VIEW_OWN = "org:view_own"        # view/update the caller's own organization
SYSTEM_STATS_VIEW = "system:stats"   # platform-wide statistics

# ---- Employees ----
EMPLOYEE_MANAGE = "employee:manage"  # add/edit/activate/deactivate/assign roles
EMPLOYEE_VIEW = "employee:view"

# ---- Customers ----
CUSTOMER_MANAGE = "customer:manage"
CUSTOMER_VIEW = "customer:view"

# ---- Work orders ----
WORKORDER_MANAGE = "workorder:manage"        # create/assign/cancel
WORKORDER_VIEW_ALL = "workorder:view_all"    # see every order in the org
WORKORDER_VIEW_ASSIGNED = "workorder:view_assigned"  # see only own assignments
WORKORDER_UPDATE_STATUS = "workorder:update_status"  # progress/notes/photos/complete

# ---- Invoices ----
INVOICE_MANAGE = "invoice:manage"
INVOICE_VIEW = "invoice:view"

# ---- Reports ----
REPORT_VIEW = "report:view"


_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.SUPER_ADMIN: frozenset(
        {ORG_MANAGE, SYSTEM_STATS_VIEW}
    ),
    UserRole.ORG_ADMIN: frozenset(
        {
            ORG_VIEW_OWN,
            EMPLOYEE_MANAGE,
            EMPLOYEE_VIEW,
            CUSTOMER_MANAGE,
            CUSTOMER_VIEW,
            WORKORDER_MANAGE,
            WORKORDER_VIEW_ALL,
            INVOICE_MANAGE,
            INVOICE_VIEW,
            REPORT_VIEW,
        }
    ),
    UserRole.EMPLOYEE: frozenset(
        {
            ORG_VIEW_OWN,
            WORKORDER_VIEW_ASSIGNED,
            WORKORDER_UPDATE_STATUS,
        }
    ),
}


def permissions_for(role: UserRole) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in permissions_for(role)
