"""Pydantic models for the Work Orders module."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import WORK_ORDER_USER_STATUSES, WorkOrderStatus

_ALLOWED_STATUSES = {s.value for s in WORK_ORDER_USER_STATUSES}


def _validate_status(v: WorkOrderStatus) -> WorkOrderStatus:
    if v.value not in _ALLOWED_STATUSES:
        raise ValueError(
            f"status must be one of: {', '.join(sorted(_ALLOWED_STATUSES))}"
        )
    return v


class WorkOrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, description="Work description")
    assignee_id: uuid.UUID | None = None  # employee to assign
    assigned_employee_name: str | None = Field(default=None, max_length=255)
    amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    due_date: date | None = None
    notes: str | None = None
    status: WorkOrderStatus = WorkOrderStatus.PENDING

    _check_status = field_validator("status")(_validate_status)


class WorkOrderUpdate(BaseModel):
    """All fields optional — only provided fields are changed (PATCH semantics)."""

    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    assignee_id: uuid.UUID | None = None
    assigned_employee_name: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    due_date: date | None = None
    notes: str | None = None
    status: WorkOrderStatus | None = None

    @field_validator("status")
    @classmethod
    def _status_allowed(cls, v: WorkOrderStatus | None) -> WorkOrderStatus | None:
        return _validate_status(v) if v is not None else v


class WorkOrderStatusUpdate(BaseModel):
    """Employee status update with an optional completion/progress note."""

    status: WorkOrderStatus
    note: str | None = Field(default=None, max_length=2000)

    _check_status = field_validator("status")(_validate_status)


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    customer_name: str | None
    assignee_id: uuid.UUID | None
    assigned_employee_name: str | None
    description: str | None
    amount: Decimal
    due_date: date | None
    notes: str | None
    status: WorkOrderStatus
    created_at: datetime
    updated_at: datetime


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRead]
    total: int
    page: int
    page_size: int
