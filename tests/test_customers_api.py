"""Integration tests for the Customer module API.

Requires a PostgreSQL ``TEST_DATABASE_URL`` (see conftest); skipped otherwise.
Covers CRUD, RBAC (admin manage / employee read-only / admin-only delete),
customer_code generation, search & filters, stats, audit logging, and
cross-tenant isolation.
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


def _make(client, token, **overrides) -> dict:
    payload = {
        "customer_type": "gst",
        "client_name": "Ramesh Traders",
        "mobile_number": "9876500001",
        "gst_number": "33ABCDE1234F1Z5",
        "pan_number": "ABCDE1234F",
        "city": "Chennai",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/customers", json=payload, headers=_auth(token))
    return resp


# --------------------------------------------------------------------------- #
# Create + customer_code
# --------------------------------------------------------------------------- #
def test_admin_creates_customer_with_sequential_code(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    r1 = _make(client, admin, client_name="First Co", gst_number="33AAAAA0000A1Z5")
    assert r1.status_code == 201, r1.text
    body = r1.json()
    assert body["customer_code"] == "CUS-0001"
    assert body["status"] == "ACTIVE"
    assert body["customer_type"] == "gst"

    r2 = _make(client, admin, client_name="Second Co", gst_number="33BBBBB0000B1Z5", mobile_number="9999999999")
    assert r2.status_code == 201
    assert r2.json()["customer_code"] == "CUS-0002"


def test_create_records_audit(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    logs = client.get(f"/api/v1/customers/{cid}/audit-logs", headers=_auth(admin))
    assert logs.status_code == 200
    actions = [e["action"] for e in logs.json()]
    assert "customer_created" in actions


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
def test_employee_can_view_but_not_create(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    _make(client, admin)
    emp = _login(client, EMP)

    # read allowed
    assert client.get("/api/v1/customers", headers=_auth(emp)).status_code == 200
    assert client.get("/api/v1/customers/lookup", headers=_auth(emp)).status_code == 200
    # write denied
    assert _make(client, emp, client_name="Nope").status_code == 403


def test_employee_cannot_delete_or_update(client, org_admin, employee) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    emp = _login(client, EMP)
    assert client.put(
        f"/api/v1/customers/{cid}", json={"client_name": "Hacked"}, headers=_auth(emp)
    ).status_code == 403
    assert client.request(
        "DELETE", f"/api/v1/customers/{cid}", headers=_auth(emp)
    ).status_code == 403


# --------------------------------------------------------------------------- #
# Update / activate / deactivate / delete
# --------------------------------------------------------------------------- #
def test_admin_updates_customer(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    r = client.put(
        f"/api/v1/customers/{cid}",
        json={"business_name": "Ramesh Traders Pvt Ltd", "email": "ramesh@example.com"},
        headers=_auth(admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["business_name"] == "Ramesh Traders Pvt Ltd"
    assert r.json()["email"] == "ramesh@example.com"


def test_deactivate_and_activate(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    d = client.patch(f"/api/v1/customers/{cid}/deactivate", headers=_auth(admin))
    assert d.status_code == 200 and d.json()["is_active"] is False
    assert d.json()["status"] == "INACTIVE"
    a = client.patch(f"/api/v1/customers/{cid}/activate", headers=_auth(admin))
    assert a.status_code == 200 and a.json()["is_active"] is True


def test_admin_deletes_customer(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    r = client.request("DELETE", f"/api/v1/customers/{cid}", headers=_auth(admin))
    assert r.status_code == 204, r.text
    assert client.get(f"/api/v1/customers/{cid}", headers=_auth(admin)).status_code == 404


def test_delete_blocked_with_work_order(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    # Link a work order to this customer.
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "category": "gst",
            "customer_id": cid,
            "customer_name": "Ramesh Traders",
            "contact_number": "9876500001",
            "description": "GST filing",
            "urgency": "medium",
        },
        headers=_auth(admin),
    )
    assert wo.status_code == 201, wo.text
    assert wo.json()["customer_id"] == cid
    r = client.request("DELETE", f"/api/v1/customers/{cid}", headers=_auth(admin))
    assert r.status_code == 409
    assert "work order" in r.json()["error"]["message"].lower()


# --------------------------------------------------------------------------- #
# Search / filters / stats
# --------------------------------------------------------------------------- #
def test_search_and_filters(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    _make(client, admin, client_name="Alpha GST", customer_type="gst",
          gst_number="33GGGGG0000G1Z5", pan_number="GGGGG1111G", mobile_number="9000000001", city="Chennai")
    _make(client, admin, client_name="Beta IT", customer_type="income_tax",
          gst_number=None, pan_number="BBBBB2222B", mobile_number="9000000002", city="Madurai")

    # search by PAN
    r = client.get("/api/v1/customers?search=GGGGG1111G", headers=_auth(admin))
    assert [c["client_name"] for c in r.json()] == ["Alpha GST"]
    # filter by type
    r = client.get("/api/v1/customers?customer_type=income_tax", headers=_auth(admin))
    assert [c["client_name"] for c in r.json()] == ["Beta IT"]
    # filter by city
    r = client.get("/api/v1/customers?city=Madurai", headers=_auth(admin))
    assert [c["client_name"] for c in r.json()] == ["Beta IT"]


def test_stats(client, org_admin) -> None:
    admin = _login(client, ADMIN)
    _make(client, admin, client_name="G1", customer_type="gst", gst_number="33G10000000G1Z5")
    _make(client, admin, client_name="I1", customer_type="income_tax", gst_number=None, pan_number="IIIII1111I")
    cid = _make(client, admin, client_name="I2", customer_type="income_tax", gst_number=None, pan_number="IIIII2222I").json()["id"]
    client.patch(f"/api/v1/customers/{cid}/deactivate", headers=_auth(admin))

    s = client.get("/api/v1/customers/stats", headers=_auth(admin)).json()
    assert s["total"] == 3
    assert s["gst"] == 1
    assert s["income_tax"] == 2
    assert s["inactive"] == 1
    assert s["active"] == 2


# --------------------------------------------------------------------------- #
# Cross-tenant isolation
# --------------------------------------------------------------------------- #
def test_cross_tenant_isolation(client, org_admin, other_org_admin) -> None:
    admin = _login(client, ADMIN)
    cid = _make(client, admin).json()["id"]
    other = _login(client, "admin@beta.example.com")
    # Other org cannot see or fetch this customer.
    assert client.get("/api/v1/customers", headers=_auth(other)).json() == []
    assert client.get(f"/api/v1/customers/{cid}", headers=_auth(other)).status_code == 404
