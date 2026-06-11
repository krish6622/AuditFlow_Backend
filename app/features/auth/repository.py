"""Data-access layer for authentication.

Pure persistence concerns only — no business rules, no HTTP. The service layer
orchestrates these calls inside a single request-scoped session/transaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionStatus, UserRole, UserStatus
from app.models.organization import Organization
from app.models.token import PasswordResetToken, RefreshToken
from app.models.user import User


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Users ----
    def get_user_by_email(self, email: str) -> User | None:
        # ``.first()`` (not ``scalar_one_or_none``) so a stray duplicate email can
        # never crash login; registration enforces global uniqueness up front.
        stmt = (
            select(User)
            .where(func.lower(User.email) == email.lower())
            .order_by(User.created_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def get_user_by_login(self, identifier: str) -> User | None:
        """Resolve a login identifier that may be an email or a phone number."""
        ident = identifier.strip()
        stmt = (
            select(User)
            .where(
                (func.lower(User.email) == ident.lower())
                | (User.phone == ident)
            )
            .order_by(User.is_active.desc(), User.created_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def email_exists(self, email: str) -> bool:
        stmt = select(User.id).where(func.lower(User.email) == email.lower()).limit(1)
        return self.db.execute(stmt).first() is not None

    def slug_exists(self, slug: str) -> bool:
        stmt = select(Organization.id).where(Organization.slug == slug).limit(1)
        return self.db.execute(stmt).first() is not None

    # ---- Sign-up (single-tenant: everyone joins the one organization) ----
    def get_default_organization(self) -> Organization | None:
        """The organization self-registrations join.

        This is an internal, single-tenant app: new employees join the
        organization run by the business. We resolve that as the org of the
        founding (earliest-created) admin — deterministic, and robust to any
        legacy orgs left over from earlier multi-org behaviour. Falls back to the
        earliest org if no admin exists yet.
        """
        by_admin = (
            select(Organization)
            .join(User, User.organization_id == Organization.id)
            .where(User.role == UserRole.ADMIN, User.deleted_at.is_(None))
            .order_by(User.created_at.asc())
            .limit(1)
        )
        org = self.db.execute(by_admin).scalars().first()
        if org is not None:
            return org
        earliest = select(Organization).order_by(Organization.created_at.asc()).limit(1)
        return self.db.execute(earliest).scalars().first()

    def create_organization(self, *, name: str, slug: str) -> Organization:
        org = Organization(
            name=name,
            slug=slug,
            is_active=True,
            subscription_status=SubscriptionStatus.TRIAL,
        )
        self.db.add(org)
        self.db.flush()  # assign org.id for the FK below
        return org

    def create_user(
        self,
        *,
        organization_id: uuid.UUID,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        user = User(
            organization_id=organization_id,
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            status=status,
            is_active=(status == UserStatus.ACTIVE),
        )
        self.db.add(user)
        self.db.flush()
        return user

    # ---- Refresh tokens ----
    def add_refresh_token(
        self, *, user_id: uuid.UUID, jti: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
        self.db.add(token)
        return token

    def get_refresh_token(self, jti: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        return self.db.execute(stmt).scalar_one_or_none()

    def revoke_refresh_token(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(timezone.utc)

    def revoke_all_user_refresh_tokens(self, user_id: uuid.UUID) -> None:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        for token in self.db.execute(stmt).scalars():
            token.revoked_at = datetime.now(timezone.utc)

    # ---- Password reset tokens ----
    def add_password_reset_token(
        self, *, user_id: uuid.UUID, jti: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(user_id=user_id, jti=jti, expires_at=expires_at)
        self.db.add(token)
        return token

    def get_password_reset_token(self, jti: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(PasswordResetToken.jti == jti)
        return self.db.execute(stmt).scalar_one_or_none()

    def mark_password_reset_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(timezone.utc)
