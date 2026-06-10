"""Unit tests for the RBAC permission matrix (no database needed)."""
from __future__ import annotations

from app.core import rbac
from app.models.enums import UserRole


def test_super_admin_manages_orgs_only() -> None:
    assert rbac.has_permission(UserRole.SUPER_ADMIN, rbac.ORG_MANAGE)
    assert rbac.has_permission(UserRole.SUPER_ADMIN, rbac.SYSTEM_STATS_VIEW)
    # Super admin is a platform role and must NOT have tenant data permissions.
    assert not rbac.has_permission(UserRole.SUPER_ADMIN, rbac.CUSTOMER_MANAGE)
    assert not rbac.has_permission(UserRole.SUPER_ADMIN, rbac.WORKORDER_MANAGE)


def test_org_admin_manages_tenant_data() -> None:
    for perm in (
        rbac.EMPLOYEE_MANAGE,
        rbac.CUSTOMER_MANAGE,
        rbac.WORKORDER_MANAGE,
        rbac.INVOICE_MANAGE,
        rbac.REPORT_VIEW,
    ):
        assert rbac.has_permission(UserRole.ORG_ADMIN, perm)
    # Org admins cannot manage the platform.
    assert not rbac.has_permission(UserRole.ORG_ADMIN, rbac.ORG_MANAGE)


def test_employee_is_restricted_to_assigned_work() -> None:
    assert rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_VIEW_ASSIGNED)
    assert rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_UPDATE_STATUS)
    # An employee can't create work orders, manage staff, or see all orders.
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_MANAGE)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.WORKORDER_VIEW_ALL)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.EMPLOYEE_MANAGE)
    assert not rbac.has_permission(UserRole.EMPLOYEE, rbac.INVOICE_MANAGE)


def test_permissions_for_returns_frozenset() -> None:
    perms = rbac.permissions_for(UserRole.ORG_ADMIN)
    assert isinstance(perms, frozenset)
    assert rbac.CUSTOMER_VIEW in perms
