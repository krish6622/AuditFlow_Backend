"""Integration tests for employee activate / deactivate / soft-delete.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see conftest); skipped otherwise.
"""
from __future__ import annotations

ADMIN = "admin@acme.example.com"
EMP = "employee@acme.example.com"


def _login(client, email: str, password: str = "Password123!") -> str:
    resp = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assign_work_order(client, admin_token, assignee_id: str) -> None:
    """Admin creates a work order already assigned to the employee (→ ASSIGNED)."""
    resp = client.post(
        "/api/v1/work-orders",
        json={
            "category": "gst",
            "customer_name": "Acme Co",
            "contact_number": "9876500000",
            "description": "GST filing",
            "urgency": "medium",
            "assignee_id": assignee_id,
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------- #
def test_admin_can_deactivate_and_activate(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    r = client.patch(f"/api/v1/employees/{employee.id}/deactivate", headers=_auth(admin))
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = client.patch(f"/api/v1/employees/{employee.id}/activate", headers=_auth(admin))
    assert r.status_code == 200 and r.json()["is_active"] is True


def test_admin_can_delete_employee_without_active_work_orders(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    r = client.request("DELETE", f"/api/v1/employees/{employee.id}", headers=_auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None


def test_delete_blocked_with_active_work_orders(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    _assign_work_order(client, admin, str(employee.id))
    r = client.request("DELETE", f"/api/v1/employees/{employee.id}", headers=_auth(admin))
    assert r.status_code == 409
    assert "active work orders" in r.json()["error"]["message"].lower()


def test_cannot_delete_last_admin(client, org_admin) -> None:
    # org_admin is the only admin → deleting them must be blocked.
    admin = _login(client, ADMIN)
    r = client.request("DELETE", f"/api/v1/employees/{org_admin.id}", headers=_auth(admin))
    assert r.status_code == 409
    assert r.json()["error"]["message"] == "At least one Admin must remain in the organization."


def test_self_delete_blocked_when_not_last_admin(client, org_admin, second_admin) -> None:
    # Two admins exist, so the last-admin guard passes and the self-guard fires.
    admin = _login(client, ADMIN)
    r = client.request("DELETE", f"/api/v1/employees/{org_admin.id}", headers=_auth(admin))
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "You cannot delete your own account."


def test_admin_can_delete_other_admin_when_multiple(client, org_admin, second_admin) -> None:
    admin = _login(client, ADMIN)
    r = client.request("DELETE", f"/api/v1/employees/{second_admin.id}", headers=_auth(admin))
    assert r.status_code == 200 and r.json()["deleted_at"] is not None


def test_deleted_employee_cannot_log_in(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    client.request("DELETE", f"/api/v1/employees/{employee.id}", headers=_auth(admin))
    resp = client.post(
        "/api/v1/auth/login", json={"identifier": EMP, "password": "Password123!"}
    )
    assert resp.status_code == 401


def test_deleted_excluded_from_list_but_shown_with_flag(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    client.request("DELETE", f"/api/v1/employees/{employee.id}", headers=_auth(admin))

    normal = client.get("/api/v1/employees", headers=_auth(admin)).json()
    assert all(e["id"] != str(employee.id) for e in normal)

    with_deleted = client.get("/api/v1/employees?include_deleted=true", headers=_auth(admin)).json()
    assert any(e["id"] == str(employee.id) for e in with_deleted)


def test_status_filter(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    client.patch(f"/api/v1/employees/{employee.id}/deactivate", headers=_auth(admin))
    inactive = client.get("/api/v1/employees?status=inactive", headers=_auth(admin)).json()
    assert any(e["id"] == str(employee.id) for e in inactive)
    active = client.get("/api/v1/employees?status=active", headers=_auth(admin)).json()
    assert all(e["id"] != str(employee.id) for e in active)
