"""Unit tests for password hashing and JWT handling (no database needed)."""
from __future__ import annotations

import time

import pytest

from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("S3cret!pass")
    assert hashed != "S3cret!pass"
    assert verify_password("S3cret!pass", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_verify_handles_garbage_hash() -> None:
    assert verify_password("x", "not-a-real-hash") is False


def test_access_token_roundtrip() -> None:
    token, jti, _ = create_access_token("user-123", extra_claims={"role": "employee"})
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["jti"] == jti
    assert payload["role"] == "employee"


def test_token_type_is_enforced() -> None:
    refresh, _, _ = create_refresh_token("user-123")
    # A refresh token must not be accepted where an access token is expected.
    with pytest.raises(AuthenticationError):
        decode_token(refresh, expected_type="access")


def test_password_reset_token_type() -> None:
    token, _, _ = create_password_reset_token("user-123")
    payload = decode_token(token, expected_type="password_reset")
    assert payload["type"] == "password_reset"


def test_tampered_token_rejected() -> None:
    token, _, _ = create_access_token("user-123")
    with pytest.raises(AuthenticationError):
        decode_token(token + "tampered", expected_type="access")


def test_jti_is_unique_per_token() -> None:
    _, jti_a, _ = create_access_token("user-1")
    time.sleep(0.001)
    _, jti_b, _ = create_access_token("user-1")
    assert jti_a != jti_b
