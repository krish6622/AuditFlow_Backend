"""Reusable FastAPI dependencies for auth, RBAC, and tenant scoping.

The dependency chain is:

    get_db ─▶ get_current_user ─▶ get_current_active_user
                                        │
                       require_permissions(...) / require_roles(...)

``get_current_user`` resolves the bearer access token to a ``User`` row. The
``require_*`` factories layer authorization on top. Tenant scoping is provided
by ``CurrentTenant`` so feature code can never "forget" to filter by org.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.rbac import has_permission
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Invalid Authorization header")
    return token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer(authorization)
    payload = decode_token(token, expected_type="access")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid token subject") from exc

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User no longer exists")
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise AuthenticationError("User account is deactivated")
    # A deactivated organization locks out all its members (super admins exempt).
    if (
        current_user.role != UserRole.SUPER_ADMIN
        and current_user.organization is not None
        and not current_user.organization.is_active
    ):
        raise AuthenticationError("Organization is deactivated")
    return current_user


def require_roles(*roles: UserRole):
    """Dependency factory: allow only the given roles."""

    allowed = set(roles)

    def _checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed:
            raise PermissionDeniedError()
        return current_user

    return _checker


def require_permissions(*permissions: str):
    """Dependency factory: require every listed permission for the caller's role."""

    required = set(permissions)

    def _checker(current_user: User = Depends(get_current_active_user)) -> User:
        if not all(has_permission(current_user.role, perm) for perm in required):
            raise PermissionDeniedError()
        return current_user

    return _checker


class CurrentTenant:
    """Resolved tenant context for the request.

    For super admins ``organization_id`` is ``None``; tenant-scoped features
    must reject super admins (or operate platform-wide) explicitly.
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self.organization_id: uuid.UUID | None = user.organization_id
        self.role: UserRole = user.role

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN


def get_current_tenant(
    current_user: User = Depends(get_current_active_user),
) -> CurrentTenant:
    return CurrentTenant(current_user)
