"""Password hashing and JWT creation/verification.

- Passwords: hashed with bcrypt (per-password random salt, cost factor 12).
- Tokens: signed JWTs (HS256) with explicit ``type`` claim so an access token
  can never be replayed as a refresh token and vice-versa.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh", "password_reset"]

_BCRYPT_ROUNDS = 12
# bcrypt only consumes the first 72 bytes of the input.
_BCRYPT_MAX_BYTES = 72


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(plain_password: str) -> str:
    pw = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_token(
    *,
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Return ``(encoded_token, jti, expires_at)``."""
    jti = str(uuid.uuid4())
    expires_at = _now() + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": int(_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "elangovan-associates",
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_access_token(
    subject: str, *, extra_claims: dict[str, Any] | None = None
) -> tuple[str, str, datetime]:
    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str) -> tuple[str, str, datetime]:
    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_password_reset_token(subject: str) -> tuple[str, str, datetime]:
    return _create_token(
        subject=subject,
        token_type="password_reset",
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT, asserting it is of the expected type.

    Raises ``AuthenticationError`` on any problem (expired, bad signature,
    wrong type) so callers never have to handle PyJWT's exception zoo.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise AuthenticationError("Invalid token type")
    return payload
