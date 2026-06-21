"""Pydantic models for the Work Orders module."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    WORK_ORDER_USER_STATUSES,
    WorkOrderCategory,
    WorkOrderPriority,
    WorkOrderStatus,
)

_ALLOWED_STATUSES = {s.value for s in WORK_ORDER_USER_STATUSES}


def _validate_status(v: WorkOrderStatus) -> WorkOrderStatus:
    if v.value not in _ALLOWED_STATUSES:
        raise ValueError(
            f"status must be one of: {', '.join(sorted(_ALLOWED_STATUSES))}"
        )
    return v


def _require_other_when_others(
    category: WorkOrderCategory | None, category_other: str | None
) -> None:
    """When category is OTHERS a free-text description is mandatory."""
    if category == WorkOrderCategory.OTHERS and not (category_other or "").strip():
        raise ValueError("Please describe the category when 'Others' is selected")


class WorkOrderCreate(BaseModel):
    category: WorkOrderCategory
    category_other: str | None = Field(default=None, max_length=120)
    # Link to the customer master (set by the customer lookup). When provided,
    # customer_name / contact_number are auto-populated from this record.
    customer_id: uuid.UUID | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    contact_number: str = Field(min_length=1, max_length=40, description="Required")
    description: str = Field(min_length=1, description="Work description")
    assignee_id: uuid.UUID | None = None  # employee to assign
    assigned_employee_name: str | None = Field(default=None, max_length=255)
    urgency: WorkOrderPriority = WorkOrderPriority.MEDIUM
    order_date: date | None = None  # defaults to today server-side
    due_date: date | None = None  # optional
    notes: str | None = None
    # New orders default to AWAITING_ASSIGNMENT; the service governs what each
    # role may actually set (employees never choose status).
    status: WorkOrderStatus = WorkOrderStatus.AWAITING_ASSIGNMENT

    @model_validator(mode="after")
    def _check_category(self) -> "WorkOrderCreate":
        _require_other_when_others(self.category, self.category_other)
        return self


class WorkOrderUpdate(BaseModel):
    """All fields optional — only provided fields are changed (PATCH semantics)."""

    category: WorkOrderCategory | None = None
    category_other: str | None = Field(default=None, max_length=120)
    customer_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_number: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, min_length=1)
    assignee_id: uuid.UUID | None = None
    assigned_employee_name: str | None = Field(default=None, max_length=255)
    urgency: WorkOrderPriority | None = None
    order_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    # Transition rules are enforced in the service (see Phase 3); any valid
    # enum value is accepted at the schema layer.
    status: WorkOrderStatus | None = None


class WorkOrderStatusUpdate(BaseModel):
    """Employee status update with an optional completion/progress note."""

    status: WorkOrderStatus
    note: str | None = Field(default=None, max_length=2000)

    _check_status = field_validator("status")(_validate_status)


class WorkOrderAssign(BaseModel):
    """Admin assignment: pick an employee and (optionally) set a due date."""

    assignee_id: uuid.UUID
    due_date: date | None = None


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    category: WorkOrderCategory | None
    category_other: str | None
    customer_id: uuid.UUID | None
    customer_name: str | None
    contact_number: str | None
    assignee_id: uuid.UUID | None
    assigned_employee_name: str | None
    requested_by_id: uuid.UUID | None
    description: str | None
    urgency: WorkOrderPriority = Field(validation_alias="priority")
    order_date: date | None
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
