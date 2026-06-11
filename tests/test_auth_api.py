"""Integration tests for the authentication endpoints.

Requires ``TEST_DATABASE_URL`` (see conftest). Each test gets a fresh org+admin.
"""
from __future__ import annotations


def _login(client, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"identifier": email, "password": password})


def test_login_success(client, org_admin) -> None:
    resp = _login(client, "admin@acme.example.com", "Password123!")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password(client, org_admin) -> None:
    resp = _login(client, "admin@acme.example.com", "wrong")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_error"


def test_login_unknown_email(client, org_admin) -> None:
    resp = _login(client, "nobody@acme.example.com", "whatever")
    assert resp.status_code == 401


def test_me_requires_auth(client, org_admin) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_profile(client, org_admin) -> None:
    token = _login(client, "admin@acme.example.com", "Password123!").json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@acme.example.com"
    assert body["role"] == "admin"
    assert body["organization_id"] is not None


def test_refresh_rotates_token(client, org_admin) -> None:
    tokens = _login(client, "admin@acme.example.com", "Password123!").json()
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The old refresh token is now revoked and must be rejected.
    reused = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401


def test_logout_revokes_refresh_token(client, org_admin) -> None:
    tokens = _login(client, "admin@acme.example.com", "Password123!").json()
    assert client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 200
    # Refresh after logout fails.
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 401


def test_change_password_flow(client, org_admin) -> None:
    token = _login(client, "admin@acme.example.com", "Password123!").json()["access_token"]
    resp = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "Password123!", "new_password": "NewPassw0rd!"},
    )
    assert resp.status_code == 200
    # Old password no longer works; new one does.
    assert _login(client, "admin@acme.example.com", "Password123!").status_code == 401
    assert _login(client, "admin@acme.example.com", "NewPassw0rd!").status_code == 200


def test_forgot_then_reset_password(client, org_admin) -> None:
    forgot = client.post(
        "/api/v1/auth/forgot-password", json={"email": "admin@acme.example.com"}
    )
    assert forgot.status_code == 200
    reset_token = forgot.json()["reset_token"]  # exposed in non-production
    assert reset_token

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "Reset3dPass!"},
    )
    assert reset.status_code == 200
    assert _login(client, "admin@acme.example.com", "Reset3dPass!").status_code == 200


def test_forgot_password_unknown_email_is_uniform(client, org_admin) -> None:
    resp = client.post(
        "/api/v1/auth/forgot-password", json={"email": "ghost@acme.example.com"}
    )
    # Same 200 + message regardless of account existence (no enumeration).
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None


# --------------------------------------------------------------------------- #
# Registration by email and/or mobile number
# --------------------------------------------------------------------------- #
def test_register_with_phone_only(client, org_admin) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"phone": "9555000111", "password": "Password123!", "full_name": "Phone User"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["access_token"]
    # The new account can then sign in using the mobile number.
    assert _login(client, "9555000111", "Password123!").status_code == 200


def test_register_with_email_only(client, org_admin) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "byemail@acme.example.com", "password": "Password123!"},
    )
    assert resp.status_code == 201
    assert _login(client, "byemail@acme.example.com", "Password123!").status_code == 200


def test_register_requires_email_or_phone(client, org_admin) -> None:
    resp = client.post("/api/v1/auth/register", json={"password": "Password123!"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_register_duplicate_phone_conflicts(client, org_admin) -> None:
    body = {"phone": "9555000222", "password": "Password123!"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_login_by_phone(client, employee) -> None:
    # ``employee`` fixture signs in with its phone number (9000000001).
    resp = _login(client, "9000000001", "Password123!")
    assert resp.status_code == 200
    assert resp.json()["access_token"]
