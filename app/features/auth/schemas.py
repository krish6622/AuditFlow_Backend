"""Pydantic request/response models for the authentication feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import UserRole


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

    The user signs up with an **email and/or a mobile number** (at least one is
    required — either can later be used to sign in) plus a password. The new user
    joins the organization as an EMPLOYEE; no organization is created and no admin
    access is granted. ``full_name`` is optional (defaulted from the identifier).
    """

    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _require_identifier(self) -> "RegisterRequest":
        has_phone = bool(self.phone and self.phone.strip())
        if not self.email and not has_phone:
            raise ValueError("Provide an email address or a mobile number")
        if has_phone and len(self.phone.strip()) < 4:
            raise ValueError("Mobile number is too short")
        return self


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
    organization_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordResponse(BaseModel):
    message: str
    # Returned only in non-production so the flow is testable without email.
    reset_token: str | None = None
