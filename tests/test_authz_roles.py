"""Integration tests for the ADMIN/EMPLOYEE authorization model.

Covers the role-change endpoint, the last-admin business rules, status changes,
the audit trail, and RBAC enforcement across all employee/audit routes.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see ``conftest.py``); skipped if
unset/unreachable.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, UserRole
from app.models.user import User

LAST_ADMIN_MSG = "At least one Admin must exist in the organization."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _login(client, email: str, password: str = "Password123!") -> str:
    resp = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_auth(client, org_admin) -> dict[str, str]:
    return _auth(_login(client, "admin@acme.example.com"))


# --------------------------------------------------------------------------- #
# RBAC: employees are locked out of every admin route (rules 4, 5)
# --------------------------------------------------------------------------- #
def test_employee_cannot_list_employees(client, employee) -> None:
    resp = client.get("/api/v1/employees", headers=_auth(_login(client, "employee@acme.example.com")))
    assert resp.status_code == 403


def test_employee_cannot_create_employee(client, employee) -> None:
    resp = client.post(
        "/api/v1/employees",
        json={"full_name": "X", "phone": "9111111111", "password": "Password123!"},
        headers=_auth(_login(client, "employee@acme.example.com")),
    )
    assert resp.status_code == 403


def test_employee_cannot_change_any_role(client, employee, org_admin) -> None:
    # Rule 5: an employee cannot change roles — not even targeting someone else,
    # and certainly not their own.
    token = _login(client, "employee@acme.example.com")
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/role",
        json={"role": "admin"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_employee_cannot_view_audit_logs(client, employee) -> None:
    resp = client.get("/api/v1/audit-logs", headers=_auth(_login(client, "employee@acme.example.com")))
    assert resp.status_code == 403


def test_unauthenticated_requests_are_401(client, org_admin) -> None:
    assert client.get("/api/v1/employees").status_code == 401
    assert client.get("/api/v1/audit-logs").status_code == 401


# --------------------------------------------------------------------------- #
# Promotion (rule 4) + audit (rule 7)
# --------------------------------------------------------------------------- #
def test_admin_promotes_employee_to_admin(client, db_session, org_admin, employee) -> None:
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/role",
        json={"role": "admin"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    db_session.expire_all()
    assert db_session.get(User, employee.id).role == UserRole.ADMIN

    entry = db_session.execute(
        select(AuditLog).where(AuditLog.affected_user_id == employee.id)
    ).scalar_one()
    assert entry.action == AuditAction.ROLE_PROMOTED
    assert entry.old_role == UserRole.EMPLOYEE
    assert entry.new_role == UserRole.ADMIN
    assert entry.performed_by_user_id == org_admin.id


def test_promote_is_idempotent_noop_without_audit(client, db_session, org_admin, second_admin) -> None:
    # second_admin is already ADMIN — promoting again changes nothing and logs nothing.
    resp = client.patch(
        f"/api/v1/employees/{second_admin.id}/role",
        json={"role": "admin"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    count = db_session.execute(select(AuditLog)).scalars().all()
    assert count == []


# --------------------------------------------------------------------------- #
# Demotion + last-admin guard (rules 1, 2, 3)
# --------------------------------------------------------------------------- #
def test_admin_demotes_another_admin_when_multiple_exist(
    client, db_session, org_admin, second_admin
) -> None:
    resp = client.patch(
        f"/api/v1/employees/{second_admin.id}/role",
        json={"role": "employee"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "employee"

    entry = db_session.execute(
        select(AuditLog).where(AuditLog.affected_user_id == second_admin.id)
    ).scalar_one()
    assert entry.action == AuditAction.ROLE_DEMOTED


def test_last_admin_cannot_be_demoted(client, db_session, org_admin) -> None:
    # org_admin is the only admin in the org.
    resp = client.patch(
        f"/api/v1/employees/{org_admin.id}/role",
        json={"role": "employee"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == LAST_ADMIN_MSG
    # Unchanged + no audit row written.
    db_session.expire_all()
    assert db_session.get(User, org_admin.id).role == UserRole.ADMIN
    assert db_session.execute(select(AuditLog)).scalars().all() == []


def test_last_admin_cannot_self_demote(client, org_admin) -> None:
    # Rule 2 — same guard, expressed as self-demotion of the only admin.
    resp = client.patch(
        f"/api/v1/employees/{org_admin.id}/role",
        json={"role": "employee"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 409


def test_admin_can_self_demote_when_another_admin_exists(
    client, db_session, org_admin, second_admin
) -> None:
    resp = client.patch(
        f"/api/v1/employees/{org_admin.id}/role",
        json={"role": "employee"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(User, org_admin.id).role == UserRole.EMPLOYEE


# --------------------------------------------------------------------------- #
# Status changes + last-admin guard (rule 3)
# --------------------------------------------------------------------------- #
def test_last_admin_cannot_be_deactivated(client, db_session, org_admin) -> None:
    resp = client.patch(
        f"/api/v1/employees/{org_admin.id}/status",
        json={"is_active": False},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == LAST_ADMIN_MSG
    db_session.expire_all()
    assert db_session.get(User, org_admin.id).is_active is True


def test_admin_can_be_deactivated_when_another_admin_exists(
    client, db_session, org_admin, second_admin
) -> None:
    resp = client.patch(
        f"/api/v1/employees/{second_admin.id}/status",
        json={"is_active": False},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    entry = db_session.execute(
        select(AuditLog).where(AuditLog.affected_user_id == second_admin.id)
    ).scalar_one()
    assert entry.action == AuditAction.STATUS_DEACTIVATED


def test_deactivate_employee_is_allowed(client, db_session, org_admin, employee) -> None:
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/status",
        json={"is_active": False},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# --------------------------------------------------------------------------- #
# Tenant isolation (rule 6)
# --------------------------------------------------------------------------- #
def test_admin_cannot_change_role_of_user_in_another_org(
    client, db_session, org_admin, other_org_admin, employee
) -> None:
    # Beta's admin tries to promote Acme's employee -> 404 (not even visible).
    token = _login(client, "admin@beta.example.com")
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/role",
        json={"role": "admin"},
        headers=_auth(token),
    )
    assert resp.status_code == 404
    db_session.expire_all()
    assert db_session.get(User, employee.id).role == UserRole.EMPLOYEE


def test_invalid_role_value_is_422(client, org_admin, employee) -> None:
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/role",
        json={"role": "manager"},
        headers=_admin_auth(client, org_admin),
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Employee list now surfaces admins too (so they can be demoted)
# --------------------------------------------------------------------------- #
def test_employee_list_includes_admins_and_employees(
    client, org_admin, employee, second_admin
) -> None:
    resp = client.get("/api/v1/employees", headers=_admin_auth(client, org_admin))
    assert resp.status_code == 200
    by_role = {u["role"] for u in resp.json()}
    assert by_role == {"admin", "employee"}
    assert len(resp.json()) == 3  # org_admin, second_admin, employee


# --------------------------------------------------------------------------- #
# Audit log endpoint (rule 7 read side) + org scoping
# --------------------------------------------------------------------------- #
def test_audit_log_lists_changes_with_names(client, org_admin, employee) -> None:
    auth = _admin_auth(client, org_admin)
    client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "admin"}, headers=auth)

    resp = client.get("/api/v1/audit-logs", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert {"items", "total", "page", "page_size"} <= body.keys()
    item = body["items"][0]
    assert item["action"] == "role_promoted"
    assert item["performed_by_name"] == "Acme Admin"
    assert item["affected_user_name"] == "Acme Employee"
    assert item["old_role"] == "employee" and item["new_role"] == "admin"


def test_audit_log_action_filter(client, org_admin, employee, second_admin) -> None:
    auth = _admin_auth(client, org_admin)
    client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "admin"}, headers=auth)
    client.patch(f"/api/v1/employees/{second_admin.id}/role", json={"role": "employee"}, headers=auth)

    promoted = client.get("/api/v1/audit-logs?action=role_promoted", headers=auth).json()
    assert promoted["total"] == 1
    assert all(i["action"] == "role_promoted" for i in promoted["items"])


def test_audit_log_is_scoped_to_caller_org(
    client, org_admin, employee, other_org_admin
) -> None:
    # Generate an entry in Acme.
    client.patch(
        f"/api/v1/employees/{employee.id}/role",
        json={"role": "admin"},
        headers=_admin_auth(client, org_admin),
    )
    # Beta's admin sees none of Acme's entries.
    beta = client.get("/api/v1/audit-logs", headers=_auth(_login(client, "admin@beta.example.com")))
    assert beta.status_code == 200
    assert beta.json()["total"] == 0


def test_audit_log_pagination(client, org_admin, employee, second_admin) -> None:
    auth = _admin_auth(client, org_admin)
    # Three changes => three entries.
    client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "admin"}, headers=auth)
    client.patch(f"/api/v1/employees/{employee.id}/role", json={"role": "employee"}, headers=auth)
    client.patch(f"/api/v1/employees/{second_admin.id}/status", json={"is_active": False}, headers=auth)

    page1 = client.get("/api/v1/audit-logs?page=1&page_size=2", headers=auth).json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    page2 = client.get("/api/v1/audit-logs?page=2&page_size=2", headers=auth).json()
    assert len(page2["items"]) == 1
