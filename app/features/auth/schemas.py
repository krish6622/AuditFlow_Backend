"""Pydantic request/response models for the authentication feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole, UserStatus


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    # Email address OR phone number — lets field employees (who may not have an
    # email) sign in with their phone.
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """Public self-serve sign-up for this internal, single-tenant app.

    Only email + password are required. The new user joins the organization as
    an EMPLOYEE awaiting administrator approval — no organization is created and
    no admin access is granted. ``full_name`` is optional (defaulted from email).
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access-token lifetime in seconds


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr | None
    full_name: str
    phone: str | None
    designation: str | None
    role: UserRole
    status: UserStatus
    organization_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


class RegisterResponse(BaseModel):
    """Sign-up result. No tokens are issued — the account must be approved by an
    administrator before it can sign in."""

    message: str
    status: str


class ForgotPasswordResponse(BaseModel):
    message: str
    # Returned only in non-production so the flow is testable without email.
    reset_token: str | None = None
