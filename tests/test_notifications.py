"""Integration tests for the work-order workflow notifications + inbox API.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see conftest); skipped otherwise.
"""
from __future__ import annotations


def _login(client, email: str, password: str = "Password123!") -> str:
    resp = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_request(client, emp_token) -> dict:
    resp = client.post(
        "/api/v1/work-orders",
        json={
            "category": "gst",
            "customer_name": "Notify Co",
            "contact_number": "9876500000",
            "description": "GST filing for Q2",
            "urgency": "high",
        },
        headers=_auth(emp_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _inbox(client, token) -> dict:
    resp = client.get("/api/v1/notifications", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# Workflow hooks
# --------------------------------------------------------------------------- #
def test_employee_request_notifies_admins_not_self(
    client, org_admin, second_admin, employee
) -> None:
    emp = _login(client, "employee@acme.example.com")
    wo = _create_request(client, emp)

    for admin_email in ("admin@acme.example.com", "admin2@acme.example.com"):
        inbox = _inbox(client, _login(client, admin_email))
        assert inbox["unread"] >= 1
        top = inbox["items"][0]
        assert top["type"] == "workorder_requested"
        assert top["work_order_id"] == wo["id"]

    # The requester does not notify themselves.
    assert _inbox(client, emp)["total"] == 0


def test_assign_notifies_assignee(client, org_admin, employee) -> None:
    admin = _login(client, "admin@acme.example.com")
    emp = _login(client, "employee@acme.example.com")
    wo = _create_request(client, emp)

    resp = client.patch(
        f"/api/v1/work-orders/{wo['id']}/assign",
        json={"assignee_id": str(employee.id), "due_date": "2026-12-01"},
        headers=_auth(admin),
    )
    assert resp.status_code == 200, resp.text

    inbox = _inbox(client, emp)
    assert any(
        n["type"] == "workorder_assigned" and n["work_order_id"] == wo["id"]
        for n in inbox["items"]
    )


def test_complete_notifies_admins_and_close_notifies_requester(
    client, org_admin, second_admin, employee
) -> None:
    admin = _login(client, "admin@acme.example.com")
    emp = _login(client, "employee@acme.example.com")
    wo = _create_request(client, emp)
    wid = wo["id"]

    client.patch(
        f"/api/v1/work-orders/{wid}/assign",
        json={"assignee_id": str(employee.id)},
        headers=_auth(admin),
    )
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "in_progress"}, headers=_auth(emp))
    client.patch(f"/api/v1/work-orders/{wid}/status", json={"status": "completed"}, headers=_auth(emp))

    # Admins are told it's ready for review.
    admin_inbox = _inbox(client, admin)
    assert any(
        n["type"] == "workorder_completed" and n["work_order_id"] == wid
        for n in admin_inbox["items"]
    )

    # Admin closes → the original requester (employee) is notified.
    resp = client.patch(f"/api/v1/work-orders/{wid}/close", headers=_auth(admin))
    assert resp.status_code == 200, resp.text
    emp_inbox = _inbox(client, emp)
    assert any(
        n["type"] == "workorder_closed" and n["work_order_id"] == wid
        for n in emp_inbox["items"]
    )


# --------------------------------------------------------------------------- #
# Inbox API
# --------------------------------------------------------------------------- #
def test_unread_count_and_mark_read(client, org_admin, employee) -> None:
    admin = _login(client, "admin@acme.example.com")
    emp = _login(client, "employee@acme.example.com")
    _create_request(client, emp)

    count = client.get("/api/v1/notifications/unread-count", headers=_auth(admin)).json()
    assert count["unread"] >= 1

    first = _inbox(client, admin)["items"][0]
    marked = client.patch(f"/api/v1/notifications/{first['id']}/read", headers=_auth(admin))
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    # Unread dropped by one.
    assert (
        client.get("/api/v1/notifications/unread-count", headers=_auth(admin)).json()["unread"]
        == count["unread"] - 1
    )


def test_mark_all_read(client, org_admin, employee) -> None:
    admin = _login(client, "admin@acme.example.com")
    emp = _login(client, "employee@acme.example.com")
    _create_request(client, emp)
    _create_request(client, emp)

    res = client.post("/api/v1/notifications/read-all", headers=_auth(admin))
    assert res.status_code == 200
    assert res.json()["updated"] >= 2
    assert client.get("/api/v1/notifications/unread-count", headers=_auth(admin)).json()["unread"] == 0


def test_notifications_are_private_to_recipient(client, org_admin, employee) -> None:
    admin = _login(client, "admin@acme.example.com")
    emp = _login(client, "employee@acme.example.com")
    _create_request(client, emp)

    # The admin's notification is not visible to the employee.
    admin_note = _inbox(client, admin)["items"][0]
    resp = client.patch(f"/api/v1/notifications/{admin_note['id']}/read", headers=_auth(emp))
    assert resp.status_code == 404
