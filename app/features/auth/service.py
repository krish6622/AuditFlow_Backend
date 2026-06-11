"""Authentication business logic.

Implements: login, refresh (with rotation), logout, forgot/reset password, and
change password. Security choices worth noting:

* Login and forgot-password give **uniform responses** regardless of whether the
  email exists, to avoid account enumeration.
* Refresh tokens are **rotated**: using one revokes it and issues a new pair.
  A revoked/expired refresh token is rejected.
* Changing or resetting a password **revokes all existing refresh tokens**, so
  every other session is logged out.
"""
from __future__ import annotations

from datetime import datetime, timezone

import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.enums import UserRole
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.features.auth import schemas
from app.features.auth.repository import AuthRepository
from app.models.user import User

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    # ------------------------------------------------------------------ #
    # Token issuance
    # ------------------------------------------------------------------ #
    def _issue_tokens(self, user: User) -> schemas.TokenResponse:
        access_token, _, _ = create_access_token(
            str(user.id),
            extra_claims={
                "role": user.role.value,
                "org": str(user.organization_id) if user.organization_id else None,
            },
        )
        refresh_token, jti, expires_at = create_refresh_token(str(user.id))
        self.repo.add_refresh_token(user_id=user.id, jti=jti, expires_at=expires_at)
        return schemas.TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ------------------------------------------------------------------ #
    # Register (public self-serve sign-up)
    # ------------------------------------------------------------------ #
    def register(self, data: schemas.RegisterRequest) -> schemas.TokenResponse:
        email = data.email.lower().strip()
        if self.repo.email_exists(email):
            raise ConflictError("An account with this email already exists")

        full_name = (data.full_name or "").strip() or _name_from_email(email)
        org_name = (data.organization_name or "").strip() or f"{full_name}'s Organization"
        slug = self._unique_slug(org_name)

        org = self.repo.create_organization(name=org_name, slug=slug)
        user = self.repo.create_user(
            organization_id=org.id,
            email=email,
            hashed_password=hash_password(data.password),
            full_name=full_name,
            role=UserRole.ADMIN,
        )

        tokens = self._issue_tokens(user)
        self.db.commit()
        logger.info("New organization '%s' registered by %s", org_name, email)
        return tokens

    def _unique_slug(self, name: str) -> str:
        base = _slugify(name) or "org"
        slug = base
        suffix = 2
        while self.repo.slug_exists(slug):
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def login(self, data: schemas.LoginRequest) -> schemas.TokenResponse:
        user = self.repo.get_user_by_login(data.identifier)
        # Always run a hash comparison to keep timing uniform for unknown emails.
        password_ok = (
            verify_password(data.password, user.hashed_password) if user else
            verify_password(data.password, _DUMMY_HASH)
        )
        if not user or not password_ok:
            raise AuthenticationError("Incorrect email or password")
        if not user.is_active:
            raise AuthenticationError("User account is deactivated")
        if (
            user.organization is not None
            and not user.organization.is_active
        ):
            raise AuthenticationError("Organization is deactivated")

        tokens = self._issue_tokens(user)
        self.db.commit()
        logger.info("User %s logged in", user.email)
        return tokens

    # ------------------------------------------------------------------ #
    # Refresh (rotation)
    # ------------------------------------------------------------------ #
    def refresh(self, data: schemas.RefreshRequest) -> schemas.TokenResponse:
        payload = decode_token(data.refresh_token, expected_type="refresh")
        jti = payload["jti"]

        stored = self.repo.get_refresh_token(jti)
        if stored is None or stored.is_revoked:
            raise AuthenticationError("Refresh token is no longer valid")
        if stored.expires_at < datetime.now(timezone.utc):
            raise AuthenticationError("Refresh token has expired")

        user = self.repo.get_user_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User is no longer active")

        # Rotate: revoke the presented token, issue a fresh pair.
        self.repo.revoke_refresh_token(stored)
        tokens = self._issue_tokens(user)
        self.db.commit()
        return tokens

    # ------------------------------------------------------------------ #
    # Logout
    # ------------------------------------------------------------------ #
    def logout(self, data: schemas.LogoutRequest) -> None:
        try:
            payload = decode_token(data.refresh_token, expected_type="refresh")
        except AuthenticationError:
            # Already invalid/expired — treat logout as idempotent success.
            return
        stored = self.repo.get_refresh_token(payload["jti"])
        if stored and not stored.is_revoked:
            self.repo.revoke_refresh_token(stored)
            self.db.commit()

    # ------------------------------------------------------------------ #
    # Forgot / reset password
    # ------------------------------------------------------------------ #
    def forgot_password(
        self, data: schemas.ForgotPasswordRequest
    ) -> schemas.ForgotPasswordResponse:
        user = self.repo.get_user_by_email(data.email)
        reset_token: str | None = None
        if user and user.is_active:
            token, jti, expires_at = create_password_reset_token(str(user.id))
            self.repo.add_password_reset_token(
                user_id=user.id, jti=jti, expires_at=expires_at
            )
            self.db.commit()
            reset_token = token
            # In production this token would be emailed, not returned.
            logger.info("Password reset requested for %s", user.email)

        message = "If an account exists for that email, a reset link has been sent."
        return schemas.ForgotPasswordResponse(
            message=message,
            reset_token=None if settings.is_production else reset_token,
        )

    def reset_password(self, data: schemas.ResetPasswordRequest) -> None:
        payload = decode_token(data.token, expected_type="password_reset")
        stored = self.repo.get_password_reset_token(payload["jti"])
        if stored is None or stored.is_used:
            raise AuthenticationError("Reset token is invalid or already used")
        if stored.expires_at < datetime.now(timezone.utc):
            raise AuthenticationError("Reset token has expired")

        user = self.repo.get_user_by_id(stored.user_id)
        if user is None:
            raise NotFoundError("User not found")

        user.hashed_password = hash_password(data.new_password)
        self.repo.mark_password_reset_used(stored)
        # Invalidate every active session for this user.
        self.repo.revoke_all_user_refresh_tokens(user.id)
        self.db.commit()
        logger.info("Password reset completed for %s", user.email)

    # ------------------------------------------------------------------ #
    # Change password (authenticated)
    # ------------------------------------------------------------------ #
    def change_password(
        self, user: User, data: schemas.ChangePasswordRequest
    ) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")
        if data.current_password == data.new_password:
            raise ValidationError("New password must differ from the current password")

        user.hashed_password = hash_password(data.new_password)
        self.repo.revoke_all_user_refresh_tokens(user.id)
        self.db.commit()
        logger.info("Password changed for %s", user.email)


def _slugify(value: str) -> str:
    """ASCII, lowercase, hyphen-separated slug (max 120 chars)."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:120]


def _name_from_email(email: str) -> str:
    """Derive a human-ish display name from the local part of an email."""
    local = email.split("@", 1)[0]
    cleaned = re.sub(r"[._-]+", " ", local).strip()
    return cleaned.title() or "New User"


# Guard against user enumeration via login timing: when the email is unknown we
# still run a real bcrypt verification against this throwaway hash so the
# response time matches the "user exists, wrong password" path.
_DUMMY_HASH = hash_password("elangovan-timing-guard-not-a-real-password")
