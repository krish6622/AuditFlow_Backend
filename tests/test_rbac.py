"""Unit tests for the RBAC permission matrix (no database needed)."""
from __future__ import annotations

from app.core import rbac
from app.models.enums import UserRole


def test_admin_manages_the_whole_organization() -> None:
    for perm in (
        rbac.ORG_MANAGE,
        rbac.EMPLOYEE_MANAGE,
        rbac.EMPLOYEE_VIEW,
        rbac.AUDIT_VIEW,
        rbac.CUSTOMER_MANAGE,
        rbac.WORKORDER_MANAGE,
        rbac.WORKORDER_VIEW_ALL,
        rbac.INVOICE_MANAGE,
        rbac.REPORT_VIEW,
    ):
        assert rbac.has_permission(UserRole.ADMIN, perm)


def test_employee_is_restricted_to_assigned_work() -> None:
    assert rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_VIEW_ASSIGNED)
    assert rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_UPDATE_STATUS)
    # An employee can't create work orders, manage staff, see all orders,
    # generate invoices, or read the audit trail.
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_MANAGE)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_VIEW_ALL)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.EMPLOYEE_MANAGE)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.INVOICE_MANAGE)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.AUDIT_VIEW)


def test_permissions_for_returns_frozenset() -> None:
    perms = rbac.permissions_for(UserRole.ADMIN)
    assert isinstance(perms, frozenset)
    assert rbac.CUSTOMER_VIEW in perms
