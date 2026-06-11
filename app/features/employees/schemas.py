"""Pydantic models for employee management (admin-facing)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=4, max_length=40)
    email: EmailStr | None = None
    designation: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    """All fields optional. ``password`` is changed only when provided."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=4, max_length=40)
    email: EmailStr | None = None
    designation: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class EmployeeStatusUpdate(BaseModel):
    is_active: bool


class EmployeeRoleUpdate(BaseModel):
    """Promote (EMPLOYEE -> ADMIN) or demote (ADMIN -> EMPLOYEE)."""

    role: UserRole


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone: str | None
    email: EmailStr | None
    designation: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
