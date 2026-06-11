"""Integration tests for the self-registration + admin-approval workflow.

Covers the business requirements:
  * new sign-ups are EMPLOYEE + PENDING_APPROVAL, never ADMIN, never auto-login;
  * sign-ups join the single existing organization (not a new one);
  * pending users cannot log in (and see the approval message);
  * admins can approve / reject pending accounts (and only admins can);
  * approved users can log in; rejected users cannot;
  * the dashboard and employee list surface pending accounts.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see ``conftest.py``); skipped if
unset/unreachable.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.features.auth.service import PENDING_APPROVAL_MESSAGE
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, UserRole, UserStatus
from app.models.organization import Organization
from app.models.user import User

NEW_EMAIL = "newbie@acme.example.com"


def _login(client, email: str, password: str = "Password123!"):
    return client.post("/api/v1/auth/login", json={"identifier": email, "password": password})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_auth(client) -> dict[str, str]:
    return _auth(_login(client, "admin@acme.example.com").json()["access_token"])


def _register(client, email: str = NEW_EMAIL, password: str = "Password123!"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "New Person"},
    )


# --------------------------------------------------------------------------- #
# Registration shape (requirements 1, 2, 3, 4)
# --------------------------------------------------------------------------- #
def test_register_creates_pending_employee_no_tokens(client, db_session, org_admin) -> None:
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # No tokens are issued — registration is not auto-login.
    assert "access_token" not in body and "refresh_token" not in body
    assert body["status"] == "pending_approval"
    assert "approval" in body["message"].lower()

    user = db_session.execute(select(User).where(User.email == NEW_EMAIL)).scalar_one()
    assert user.role == UserRole.EMPLOYEE          # never ADMIN (requirement 2)
    assert user.status == UserStatus.PENDING_APPROVAL
    assert user.is_active is False


def test_register_joins_existing_org_not_a_new_one(client, db_session, org_admin) -> None:
    # Single-tenant: the new user joins the one organization; no org is created.
    before = db_session.execute(select(func.count()).select_from(Organization)).scalar_one()
    _register(client)
    after = db_session.execute(select(func.count()).select_from(Organization)).scalar_one()
    assert after == before == 1

    user = db_session.execute(select(User).where(User.email == NEW_EMAIL)).scalar_one()
    assert user.organization_id == org_admin.organization_id


def test_register_duplicate_email_conflicts(client, org_admin) -> None:
    assert _register(client).status_code == 201
    dup = _register(client)
    assert dup.status_code == 409


# --------------------------------------------------------------------------- #
# Pending accounts cannot sign in (requirement 7)
# --------------------------------------------------------------------------- #
def test_pending_user_cannot_login(client, org_admin) -> None:
    _register(client)
    resp = _login(client, NEW_EMAIL)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == PENDING_APPROVAL_MESSAGE


# --------------------------------------------------------------------------- #
# Approval workflow (requirement 6)
# --------------------------------------------------------------------------- #
def test_admin_approves_then_user_can_login(client, db_session, org_admin) -> None:
    _register(client)
    user = db_session.execute(select(User).where(User.email == NEW_EMAIL)).scalar_one()

    resp = client.patch(
        f"/api/v1/employees/{user.id}/approve", headers=_admin_auth(client)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Now sign-in succeeds.
    assert _login(client, NEW_EMAIL).status_code == 200

    entry = db_session.execute(
        select(AuditLog).where(AuditLog.affected_user_id == user.id)
    ).scalar_one()
    assert entry.action == AuditAction.USER_APPROVED


def test_admin_rejects_then_user_still_blocked(client, db_session, org_admin) -> None:
    _register(client)
    user = db_session.execute(select(User).where(User.email == NEW_EMAIL)).scalar_one()

    resp = client.patch(
        f"/api/v1/employees/{user.id}/reject", headers=_admin_auth(client)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"

    # Rejected (now INACTIVE) → blocked, but no longer the "pending" message.
    login = _login(client, NEW_EMAIL)
    assert login.status_code == 401
    assert login.json()["error"]["message"] != PENDING_APPROVAL_MESSAGE

    entry = db_session.execute(
        select(AuditLog).where(AuditLog.affected_user_id == user.id)
    ).scalar_one()
    assert entry.action == AuditAction.USER_REJECTED


def test_approve_non_pending_is_conflict(client, db_session, org_admin, employee) -> None:
    # ``employee`` fixture is already ACTIVE — approving it is a 409.
    resp = client.patch(
        f"/api/v1/employees/{employee.id}/approve", headers=_admin_auth(client)
    )
    assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# Only admins may approve / reject (requirements 5, 8 — authorization preserved)
# --------------------------------------------------------------------------- #
def test_employee_cannot_approve(client, db_session, org_admin, employee) -> None:
    _register(client)
    target = db_session.execute(select(User).where(User.email == NEW_EMAIL)).scalar_one()
    token = _login(client, "employee@acme.example.com").json()["access_token"]
    resp = client.patch(f"/api/v1/employees/{target.id}/approve", headers=_auth(token))
    assert resp.status_code == 403


def test_unauthenticated_cannot_approve(client, org_admin, employee) -> None:
    assert client.patch(f"/api/v1/employees/{employee.id}/approve").status_code == 401


# --------------------------------------------------------------------------- #
# Pending accounts are surfaced to admins (requirement 5 — dashboard + list)
# --------------------------------------------------------------------------- #
def test_dashboard_summary_reports_pending(client, org_admin) -> None:
    _register(client)
    resp = client.get("/api/v1/dashboard/summary", headers=_admin_auth(client))
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["pending_approvals"] == 1
    assert len(body["pending_approvals"]) == 1
    assert body["pending_approvals"][0]["email"] == NEW_EMAIL


def test_employee_list_pending_filter(client, org_admin, employee) -> None:
    _register(client)
    resp = client.get("/api/v1/employees?status=pending", headers=_admin_auth(client))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["email"] == NEW_EMAIL
    assert rows[0]["status"] == "pending_approval"
