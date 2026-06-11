"""Integration tests for the auditor-office work-order workflow.

Covers employee request creation (field stripping + RBAC), admin assignment,
the guarded status transitions, close/cancel, and the requester/assignee queries.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see conftest); skipped otherwise.
"""
from __future__ import annotations


def _login(client, email: str, password: str = "Password123!") -> str:
    resp = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _request(client, token, **overrides) -> dict:
    body = {
        "category": "gst",
        "customer_name": "Workflow Co",
        "description": "GST filing",
        "urgency": "high",
        **overrides,
    }
    resp = client.post("/api/v1/work-orders", json=body, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


ADMIN = "admin@acme.example.com"
EMP = "employee@acme.example.com"
EMP2 = "employee2@acme.example.com"


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #
def test_employee_request_defaults_to_awaiting_and_strips_fields(client, org_admin, employee) -> None:
    emp = _login(client, EMP)
    wo = _request(
        client,
        emp,
        assignee_id=str(employee.id),  # should be ignored
        due_date="2026-09-01",          # should be ignored
        status="completed",             # should be ignored
    )
    assert wo["status"] == "awaiting_assignment"
    assert wo["assignee_id"] is None
    assert wo["due_date"] is None
    assert wo["requested_by_id"] == str(employee.id)


def test_admin_create_with_assignee_is_assigned(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    wo = _request(client, admin, assignee_id=str(employee.id), due_date="2026-10-01")
    assert wo["status"] == "assigned"
    assert wo["assignee_id"] == str(employee.id)
    assert wo["due_date"] == "2026-10-01"


# --------------------------------------------------------------------------- #
# RBAC — employees can't manage
# --------------------------------------------------------------------------- #
def test_employee_cannot_edit_delete_assign_close_cancel(client, org_admin, employee) -> None:
    emp = _login(client, EMP)
    wo = _request(client, emp)
    wid = wo["id"]
    assert client.put(f"/api/v1/work-orders/{wid}", json={"customer_name": "x"}, headers=_auth(emp)).status_code == 403
    assert client.delete(f"/api/v1/work-orders/{wid}", headers=_auth(emp)).status_code == 403
    assert client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(emp)).status_code == 403
    assert client.patch(f"/api/v1/work-orders/{wid}/close", headers=_auth(emp)).status_code == 403
    assert client.patch(f"/api/v1/work-orders/{wid}/cancel", headers=_auth(emp)).status_code == 403


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #
def test_assign_sets_status_due_and_supports_reassign(
    client, org_admin, employee, employee_two
) -> None:
    admin = _login(client, ADMIN)
    wo = _request(client, _login(client, EMP))
    wid = wo["id"]

    r = client.patch(
        f"/api/v1/work-orders/{wid}/assign",
        json={"assignee_id": str(employee.id), "due_date": "2026-12-01"},
        headers=_auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "assigned"
    assert r.json()["assignee_id"] == str(employee.id)
    assert r.json()["due_date"] == "2026-12-01"

    # Reassign to another employee while still ASSIGNED.
    r = client.patch(
        f"/api/v1/work-orders/{wid}/assign",
        json={"assignee_id": str(employee_two.id)},
        headers=_auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["assignee_id"] == str(employee_two.id)


def test_cannot_assign_a_completed_order(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    emp = _login(client, EMP)
    wid = _request(client, emp)["id"]
    client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(admin))
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "in_progress"}, headers=_auth(emp))
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "completed"}, headers=_auth(emp))
    r = client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(admin))
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Progress transitions
# --------------------------------------------------------------------------- #
def test_progress_transitions_and_skip_blocked(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    emp = _login(client, EMP)
    wid = _request(client, emp)["id"]
    client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(admin))

    # Cannot skip assigned -> completed.
    assert client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "completed"}, headers=_auth(emp)).status_code == 422
    # Forward one step at a time.
    assert client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "in_progress"}, headers=_auth(emp)).json()["status"] == "in_progress"
    assert client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "completed"}, headers=_auth(emp)).json()["status"] == "completed"


def test_non_owner_employee_cannot_progress(client, org_admin, employee, employee_two) -> None:
    admin = _login(client, ADMIN)
    emp = _login(client, EMP)
    other = _login(client, EMP2)
    wid = _request(client, emp)["id"]
    client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(admin))
    # employee_two is not the assignee.
    assert client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "in_progress"}, headers=_auth(other)).status_code == 403


# --------------------------------------------------------------------------- #
# Close / cancel
# --------------------------------------------------------------------------- #
def test_close_only_from_completed(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    emp = _login(client, EMP)
    wid = _request(client, emp)["id"]
    # Not completed yet → 422.
    assert client.patch(f"/api/v1/work-orders/{wid}/close", headers=_auth(admin)).status_code == 422

    client.patch(f"/api/v1/work-orders/{wid}/assign", json={"assignee_id": str(employee.id)}, headers=_auth(admin))
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "in_progress"}, headers=_auth(emp))
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "completed"}, headers=_auth(emp))
    assert client.patch(f"/api/v1/work-orders/{wid}/close", headers=_auth(admin)).json()["status"] == "closed"


def test_cancel_open_then_blocked_when_terminal(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    emp = _login(client, EMP)
    wid = _request(client, emp)["id"]
    assert client.patch(f"/api/v1/work-orders/{wid}/cancel", headers=_auth(admin)).json()["status"] == "cancelled"
    # Cancelling again (terminal) is rejected.
    assert client.patch(f"/api/v1/work-orders/{wid}/cancel", headers=_auth(admin)).status_code == 422


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def test_my_requests_vs_assigned(client, org_admin, employee, employee_two) -> None:
    admin = _login(client, ADMIN)
    requester = _login(client, EMP)
    wo = _request(client, requester)  # raised by `employee`
    # admin assigns it to employee_two
    client.patch(f"/api/v1/work-orders/{wo['id']}/assign", json={"assignee_id": str(employee_two.id)}, headers=_auth(admin))

    # requester sees it under my-requests, not under /mine (not assigned to them).
    reqs = client.get("/api/v1/work-orders/my-requests", headers=_auth(requester)).json()
    assert any(i["id"] == wo["id"] for i in reqs["items"])
    mine = client.get("/api/v1/work-orders/mine", headers=_auth(requester)).json()
    assert all(i["id"] != wo["id"] for i in mine["items"])

    # employee_two sees it under /mine (assigned).
    other_mine = client.get("/api/v1/work-orders/mine", headers=_auth(_login(client, EMP2))).json()
    assert any(i["id"] == wo["id"] for i in other_mine["items"])


def test_dashboard_reports_awaiting_assignment(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    _request(client, _login(client, EMP))
    summary = client.get("/api/v1/dashboard/summary", headers=_auth(admin)).json()
    assert summary["totals"]["awaiting_assignment"] >= 1
    assert any(w["status"] == "awaiting_assignment" for w in summary["awaiting_assignment"])
