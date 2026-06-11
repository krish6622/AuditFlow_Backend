"""Authentication API routes (``/api/v1/auth``)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.features.auth import schemas
from app.features.auth.service import AuthService
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post(
    "/register",
    response_model=schemas.RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: schemas.RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.RegisterResponse:
    """Public sign-up: creates an EMPLOYEE awaiting administrator approval.

    No tokens are returned — the account cannot sign in until an admin approves
    it. (This is an internal, single-tenant app, not a multi-tenant SaaS.)"""
    return service.register(data)


@router.post("/login", response_model=schemas.TokenResponse)
def login(
    data: schemas.LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.TokenResponse:
    """Authenticate with email + password; returns an access/refresh token pair."""
    return service.login(data)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(
    data: schemas.RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.TokenResponse:
    """Exchange a valid refresh token for a new token pair (rotation)."""
    return service.refresh(data)


@router.post("/logout", response_model=schemas.MessageResponse)
def logout(
    data: schemas.LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.MessageResponse:
    """Revoke the supplied refresh token. Idempotent."""
    service.logout(data)
    return schemas.MessageResponse(message="Logged out successfully")


@router.post("/forgot-password", response_model=schemas.ForgotPasswordResponse)
def forgot_password(
    data: schemas.ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.ForgotPasswordResponse:
    """Begin the password-reset flow. Always returns a uniform message."""
    return service.forgot_password(data)


@router.post(
    "/reset-password",
    response_model=schemas.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def reset_password(
    data: schemas.ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> schemas.MessageResponse:
    """Complete a password reset using the token from ``forgot-password``."""
    service.reset_password(data)
    return schemas.MessageResponse(message="Password has been reset")


@router.post("/change-password", response_model=schemas.MessageResponse)
def change_password(
    data: schemas.ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    service: AuthService = Depends(get_auth_service),
) -> schemas.MessageResponse:
    """Change the authenticated user's password; logs out all other sessions."""
    service.change_password(current_user, data)
    return schemas.MessageResponse(message="Password changed successfully")


@router.get("/me", response_model=schemas.UserProfile)
def me(current_user: User = Depends(get_current_active_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user
